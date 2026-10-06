"""La liste blanche du réseau (§0.6) : le seul chemin vers Internet.

Hôtes permis, et seulement ceux-là :
- l'API Anthropic (avis de l'IA) ;
- Have I Been Pwned (liste publique des fuites) ;
- rdap.org et les serveurs RDAP qu'il désigne (date de création d'un nom de domaine) ;
- les flux publics de liens piégés : OpenPhish (communauté) et URLhaus (abuse.ch), téléchargés en entier ;
- les sites officiels qui servent à vérifier les numéros utiles et les réflexes ;
- Gmail en IMAP.

Deux protections :
1. `telecharger()` refuse toute adresse hors liste, y compris après une redirection ;
2. `installer_garde()` (lancée par la CLI et le démon) refuse toute résolution de nom hors liste, quel que soit
   le code qui la demande (bibliothèque comprise).

Interdit absolu : ouvrir un lien trouvé dans un message. Le détecteur n'appelle jamais ce module avec un lien
de message ; seul le **nom de domaine** part vers RDAP.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.client import HTTPMessage
from typing import Any

AGENT = "Bouclier/1.0 (outil personnel de securite, macOS ; contact : utilisateur local)"

HOTES_EXACTS = frozenset(
    {
        "api.anthropic.com",
        "haveibeenpwned.com",
        "rdap.org",
        "openphish.com",
        "urlhaus.abuse.ch",
        "imap.gmail.com",
    }
)

# Sites officiels pour vérifier les numéros utiles et les réflexes (n°20 et n°22) : le domaine et ses sous-domaines.
DOMAINES_OFFICIELS = (
    "gouv.fr",  # cybermalveillance.gouv.fr, interieur.gouv.fr, service-public.gouv.fr, masecurite.interieur.gouv.fr…
    "service-public.fr",
    "gouvernement.fr",
    "chu-bordeaux.fr",
    "centres-antipoison.net",
    "ars.sante.fr",  # agences régionales de santé (pharmacies de garde)
)

# Hors processus (installation seulement) : les paquets Python.
HOTES_INSTALLATION = ("pypi.org", "files.pythonhosted.org")

_rdap_designes: set[str] = set()
_verrou = threading.Lock()


class HoteInterdit(Exception):
    """Une connexion vers un hôte hors de la liste blanche a été demandée (et refusée)."""


def _normaliser(hote: str) -> str:
    return hote.strip().rstrip(".").lower()


def est_officiel(hote: str) -> bool:
    h = _normaliser(hote)
    return any(h == d or h.endswith("." + d) for d in DOMAINES_OFFICIELS)


def est_local(hote: str) -> bool:
    h = _normaliser(hote)
    if h in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def hote_autorise(hote: str) -> bool:
    h = _normaliser(hote)
    if h in HOTES_EXACTS or est_officiel(h):
        return True
    with _verrou:
        return h in _rdap_designes


def designer_serveur_rdap(url_redirection: str, domaine_demande: str) -> str:
    """rdap.org renvoie vers le serveur RDAP du registre : il n'est permis que pour cette redirection-là,
    en HTTPS, et seulement si l'adresse demande bien ce domaine (…/domain/<domaine>)."""
    morceaux = urllib.parse.urlsplit(url_redirection)
    hote = _normaliser(morceaux.hostname or "")
    chemin = urllib.parse.unquote(morceaux.path).lower().rstrip("/")
    if morceaux.scheme != "https" or not hote or not chemin.endswith("/domain/" + domaine_demande.lower()):
        raise HoteInterdit(f"redirection RDAP refusée : {morceaux.scheme}://{hote}")
    try:
        ipaddress.ip_address(hote)
        raise HoteInterdit("redirection RDAP vers une adresse IP refusée")
    except ValueError:
        pass
    with _verrou:
        _rdap_designes.add(hote)
    return hote


def verifier_url(url: str) -> str:
    morceaux = urllib.parse.urlsplit(url)
    if morceaux.scheme != "https":
        raise HoteInterdit(f"seul HTTPS est permis ({morceaux.scheme or 'sans protocole'})")
    hote = _normaliser(morceaux.hostname or "")
    if not hote_autorise(hote):
        raise HoteInterdit(f"hôte hors liste blanche : {hote or '(vide)'}")
    return hote


@dataclass
class Reponse:
    statut: int
    corps: bytes
    url_finale: str
    entetes: dict[str, str] = field(default_factory=dict)

    def texte(self) -> str:
        return self.corps.decode("utf-8", "replace")


class _Redirections(urllib.request.HTTPRedirectHandler):
    """Chaque redirection est revérifiée ; rdap.org peut désigner un serveur de registre (et lui seul)."""

    def __init__(self, domaine_rdap: str | None) -> None:
        super().__init__()
        self.domaine_rdap = domaine_rdap

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: HTTPMessage, newurl: str
    ) -> urllib.request.Request | None:
        origine = _normaliser(urllib.parse.urlsplit(req.full_url).hostname or "")
        if self.domaine_rdap and origine == "rdap.org":
            designer_serveur_rdap(newurl, self.domaine_rdap)
        verifier_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ErreurReseau(Exception):
    """Hôte injoignable, délai dépassé, réponse trop grande : le module appelant passe en mode dégradé."""


def telecharger(
    url: str,
    *,
    delai: float = 20.0,
    max_octets: int = 60_000_000,
    entetes: dict[str, str] | None = None,
    domaine_rdap: str | None = None,
) -> Reponse:
    """GET en HTTPS vers un hôte permis. Lève HoteInterdit (jamais contacté) ou ErreurReseau."""
    verifier_url(url)
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT, **(entetes or {})})
    ouvreur = urllib.request.build_opener(_Redirections(domaine_rdap))
    try:
        with ouvreur.open(requete, timeout=delai) as r:
            corps = r.read(max_octets + 1)
            if len(corps) > max_octets:
                raise ErreurReseau(f"réponse trop grande (> {max_octets} octets)")
            return Reponse(r.status, corps, r.geturl(), {k.lower(): v for k, v in r.headers.items()})
    except urllib.error.HTTPError as e:
        corps = e.read(65536) if e.fp else b""
        return Reponse(e.code, corps, url, {k.lower(): v for k, v in (e.headers or {}).items()})
    except HoteInterdit:
        raise
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as e:
        raise ErreurReseau(f"{urllib.parse.urlsplit(url).hostname} injoignable : {e.__class__.__name__}") from e


# --- Garde du processus : toute résolution de nom passe par ici -------------------------------------------------

_getaddrinfo_origine = socket.getaddrinfo
_garde_installee = False


def _getaddrinfo_garde(host: Any, *args: Any, **kwargs: Any) -> Any:
    nom = host.decode() if isinstance(host, bytes) else (host or "")
    if nom and not est_local(nom) and not hote_autorise(nom):
        raise HoteInterdit(f"connexion refusée vers {nom} (hors liste blanche)")
    return _getaddrinfo_origine(host, *args, **kwargs)


def installer_garde() -> None:
    """Refuse toute connexion par nom hors liste blanche, pour tout le processus (idempotent)."""
    global _garde_installee
    if not _garde_installee:
        socket.getaddrinfo = _getaddrinfo_garde
        _garde_installee = True
