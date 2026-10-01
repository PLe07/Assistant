"""Lire un flux RSS (ou Atom) : la liste des nouveautés qu'un site publie pour les logiciels.

Tout se fait sur ton Mac, avec les outils inclus dans Python. L'Assistant ne fait que LIRE ces sites
publics : il n'y envoie rien de toi (seulement « Assistant-veille » comme nom de lecteur).
Si l'adresse donnée est une page web et pas un flux, il cherche le flux annoncé par cette page.
"""

import html
import re
import ssl
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from modules.veille import parametres as p

AGENT = "Assistant-veille/1.0 (lecteur RSS personnel)"
_LIEN_FLUX = re.compile(r"<link\b[^>]*type=[\"']application/(?:rss|atom)\+xml[\"'][^>]*>", re.I)
_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
_BALISE = re.compile(r"<[^>]+>")
# Dates à la française : « 01/10/2026 », « 1 octobre 2026 », « mer., 01 oct. 2026 10:00:00 +0200 »…
_DATE_FR = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_DATE_MOIS = re.compile(r"\b(\d{1,2})(?:er)?\s+([^\W\d_]{3,9})\.?\s+(\d{4})\b")
_MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre",
         "decembre"]


class SourceIllisible(Exception):
    """Le site ne répond pas, ou ce n'est pas un flux : le message dit pourquoi, simplement."""


def _contexte_ssl() -> ssl.SSLContext:
    try:  # la liste des certificats de confiance la plus à jour (installée avec le module mails)
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def telecharger(adresse: str) -> bytes:
    if not adresse.lower().startswith(("https://", "http://")):
        raise SourceIllisible("l'adresse doit commencer par https://")
    requete = urllib.request.Request(adresse, headers={"User-Agent": AGENT, "Accept": "application/rss+xml, "
                                                       "application/atom+xml, application/xml, text/xml, text/html"})
    try:
        with urllib.request.urlopen(requete, timeout=p.DELAI_SECONDES, context=_contexte_ssl()) as r:
            contenu = r.read(p.TAILLE_MAX + 1)
    except urllib.error.HTTPError as e:
        raise SourceIllisible(f"le site répond « erreur {e.code} » (adresse changée ?)")
    except urllib.error.URLError as e:
        raison = getattr(e, "reason", e)
        if isinstance(raison, ssl.SSLError):
            raise SourceIllisible(f"connexion sécurisée impossible ({raison})")
        raise SourceIllisible(f"site injoignable ({raison} ; internet coupé ?)")
    except (TimeoutError, OSError) as e:
        raise SourceIllisible(f"site injoignable ({e})")
    if len(contenu) > p.TAILLE_MAX:
        raise SourceIllisible("réponse trop grosse pour un flux")
    return contenu


def nettoyer(texte: str | None, n: int = 300) -> str:
    """Le texte sans balises HTML, sur une ligne, coupé à n caractères."""
    t = " ".join(html.unescape(_BALISE.sub(" ", html.unescape(texte or ""))).split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn").lower()


def _date_fr(texte: str) -> datetime | None:
    m = _DATE_FR.search(texte)
    if m:
        jour, mois, annee = int(m[1]), int(m[2]), int(m[3])
    else:
        m = _DATE_MOIS.search(texte)
        mot = _sans_accents(m[2]) if m else ""
        mois = next((i + 1 for i, nom in enumerate(_MOIS) if nom.startswith(mot) or mot.startswith(nom[:4])), 0)
        if not m or not mois:
            return None
        jour, annee = int(m[1]), int(m[3])
    try:
        return datetime(annee, mois, jour)
    except ValueError:
        return None


def _date(texte: str | None) -> float | None:
    texte = (texte or "").strip()
    if not texte:
        return None
    try:
        d = parsedate_to_datetime(texte)  # RSS : « Tue, 30 Sep 2026 10:00:00 +0200 »
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(texte.replace("Z", "+00:00"))  # Atom : « 2026-09-30T10:00:00Z »
        except ValueError:
            d = _date_fr(texte)
            if d is None:
                return None
            return d.timestamp()  # une date sans heure : minuit, heure de ton Mac
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _local(balise: str) -> str:
    return balise.rsplit("}", 1)[-1].lower()


def _enfant(element, *noms: str):
    for e in element:
        if _local(e.tag) in noms:
            return e
    return None


def _texte_de(element, *noms: str) -> str:
    e = _enfant(element, *noms)
    return "".join(e.itertext()) if e is not None else ""


def _lien_atom(entree) -> str:
    liens = [e for e in entree if _local(e.tag) == "link"]
    for e in liens:
        if e.get("rel", "alternate") == "alternate" and e.get("href"):
            return e.get("href")
    return liens[0].get("href", "") if liens else ""


def analyser(contenu: bytes, adresse: str) -> list[dict]:
    """Les articles d'un flux RSS 2.0, RSS 1.0 ou Atom : [{cle, titre, lien, resume, publie}, …].
    Lève SourceIllisible si ce n'est pas un flux."""
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError:
        raise SourceIllisible("ce n'est pas un flux RSS")
    articles = []
    nature = _local(racine.tag)
    if nature == "feed":  # Atom
        for e in racine:
            if _local(e.tag) != "entry":
                continue
            lien = urljoin(adresse, _lien_atom(e).strip())
            brute = _texte_de(e, "published", "updated")
            articles.append({"cle": _texte_de(e, "id").strip() or lien, "titre": _texte_de(e, "title"), "lien": lien,
                             "resume": _texte_de(e, "summary", "content"), "publie": _date(brute), "date_brute": brute})
    elif nature in ("rss", "rdf"):
        canal = _enfant(racine, "channel")
        # RSS 2.0 : les articles sont dans le canal ; RSS 1.0 (« rdf ») : à côté du canal.
        parent = canal if nature == "rss" and canal is not None else racine
        for e in [x for x in parent if _local(x.tag) == "item"]:
            lien = urljoin(adresse, _texte_de(e, "link").strip())
            brute = _texte_de(e, "pubdate", "date", "published")
            articles.append({"cle": _texte_de(e, "guid").strip() or lien, "titre": _texte_de(e, "title"), "lien": lien,
                             "resume": _texte_de(e, "description", "encoded", "summary"), "publie": _date(brute),
                             "date_brute": " ".join(brute.split())[:60]})
    else:
        raise SourceIllisible("ce n'est pas un flux RSS")
    propres = []
    for a in articles:
        titre = nettoyer(a["titre"], 200)
        if not titre or not a["lien"].lower().startswith(("https://", "http://")):
            continue  # un article sans titre, ou dont le lien n'est pas une page web, est ignoré
        propres.append({**a, "titre": titre, "resume": nettoyer(a["resume"]), "cle": a["cle"][:500]})
    return propres


def flux_annonce(page: bytes, adresse: str) -> str | None:
    """Une page web annonce souvent son flux (<link type="application/rss+xml" href="…">)."""
    texte = page[:300_000].decode("utf-8", "replace")
    for balise in _LIEN_FLUX.findall(texte):
        href = _HREF.search(balise)
        if href:
            return urljoin(adresse, html.unescape(href[1]))
    return None


def lire_source(adresse: str) -> tuple[list[dict], str]:
    """(articles, adresse du flux réellement lu)."""
    contenu = telecharger(adresse)
    try:
        return analyser(contenu, adresse), adresse
    except SourceIllisible:
        flux = flux_annonce(contenu, adresse)
        if not flux or flux == adresse:
            raise SourceIllisible("ce n'est pas un flux RSS, et la page n'en annonce aucun (adresse changée ?)")
        return analyser(telecharger(flux), flux), flux
