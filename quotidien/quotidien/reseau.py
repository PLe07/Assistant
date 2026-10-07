"""La liste blanche du réseau (§0.6) : le seul chemin vers Internet.

Hôtes permis, et seulement ceux-là :
- l'API Anthropic (photo du frigo, message d'anniversaire, envie formulée librement) ;
- Open-Meteo : `api.open-meteo.com` (prévisions) et `geocoding-api.open-meteo.com` (retrouver une ville), gratuits et
  sans clé.

Deux protections :
1. `telecharger()` refuse toute adresse hors liste, y compris après une redirection, et tout ce qui n'est pas HTTPS ;
2. `installer_garde()` (lancée par la CLI et le démon) refuse toute résolution de nom hors liste, quel que soit le
   code qui la demande (bibliothèque comprise).

Les paquets Python (PyPI) ne passent que par `install.sh`, hors de ce processus.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.client import HTTPMessage
from typing import Any

AGENT = "Quotidien/1.0 (outil personnel, macOS)"

HOTES_PERMIS = frozenset({"api.anthropic.com", "api.open-meteo.com", "geocoding-api.open-meteo.com"})

# Hors processus (installation seulement) : les paquets Python.
HOTES_INSTALLATION = ("pypi.org", "files.pythonhosted.org")


class HoteInterdit(Exception):
    """Une connexion vers un hôte hors de la liste blanche a été demandée (et refusée)."""


class ErreurReseau(Exception):
    """Hôte injoignable, délai dépassé, réponse trop grande : le module appelant passe en mode dégradé."""


def _normaliser(hote: str) -> str:
    return hote.strip().rstrip(".").lower()


def est_local(hote: str) -> bool:
    h = _normaliser(hote)
    if h in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def hote_autorise(hote: str) -> bool:
    return _normaliser(hote) in HOTES_PERMIS


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
    """Chaque redirection est revérifiée : une redirection hors liste est refusée avant d'être suivie."""

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: HTTPMessage, newurl: str
    ) -> urllib.request.Request | None:
        verifier_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def telecharger(url: str, *, delai: float = 20.0, max_octets: int = 5_000_000) -> Reponse:
    """GET en HTTPS vers un hôte permis. Lève HoteInterdit (jamais contacté) ou ErreurReseau."""
    verifier_url(url)
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    ouvreur = urllib.request.build_opener(_Redirections())
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
