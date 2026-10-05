"""La forme normalisée des événements : ce qui varie d'une fois à l'autre (dates, numéros, empreintes, parties
variables des noms) devient « * », pour que la même action donne toujours le même « token ».

Les heures sont celles de Paris (Europe/Paris), changement d'heure compris.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    ZONE: ZoneInfo | None = ZoneInfo("Europe/Paris")
except Exception:  # base des fuseaux absente : l'heure locale du Mac (identique en France)
    ZONE = None

# --- Le temps ----------------------------------------------------------------------------------------------


def local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, ZONE) if ZONE else datetime.fromtimestamp(ts)


# L'analyse pose ces questions des centaines de milliers de fois : le décalage horaire est gardé par quart d'heure
# (un changement d'heure tombe toujours sur un quart d'heure pile), et le nom du jour par jour.
_QUART = 900


@lru_cache(maxsize=65536)
def _decalage(quart: int) -> int:
    """Le décalage de l'heure de Paris (en secondes) pendant ce quart d'heure."""
    decalage = local(quart * _QUART).utcoffset()
    return int(decalage.total_seconds()) if decalage is not None else 0


def _jour_numero(ts: float) -> int:
    """Le numéro du jour (heure de Paris) depuis le 1er janvier 1970."""
    return int((ts + _decalage(int(ts // _QUART))) // 86400)


@lru_cache(maxsize=4096)
def _nom_du_jour(numero: int) -> str:
    return (date(1970, 1, 1) + timedelta(days=numero)).isoformat()


def jour_de(ts: float) -> str:
    return _nom_du_jour(_jour_numero(ts))


def minute_du_jour(ts: float) -> int:
    return int((ts + _decalage(int(ts // _QUART))) % 86400) // 60


def jour_semaine(ts: float) -> int:
    """0 = lundi … 6 = dimanche."""
    return (_jour_numero(ts) + 3) % 7  # le 1er janvier 1970 était un jeudi


def semaine(ts: float) -> str:
    annee, numero, _ = local(ts).isocalendar()
    return f"{annee}-S{numero:02d}"


def mois_de(ts: float) -> str:
    return local(ts).strftime("%Y-%m")


def debut_du_jour(ts: float) -> float:
    """Minuit (heure de Paris) du jour de ts : juste, même les jours de changement d'heure."""
    d = local(ts)
    minuit = datetime(d.year, d.month, d.day, tzinfo=ZONE) if ZONE else datetime(d.year, d.month, d.day)
    return minuit.timestamp()


def instant_du_jour(ts: float, heure: str) -> float:
    """L'instant « HH:MM » (heure de Paris) du même jour que ts."""
    h, m = (int(x) for x in heure.split(":"))
    d = local(ts)
    cible = datetime(d.year, d.month, d.day, h, m, tzinfo=ZONE) if ZONE else datetime(d.year, d.month, d.day, h, m)
    return cible.timestamp()


def veille(ts: float) -> float:
    return (local(ts) - timedelta(days=1)).timestamp()


# --- Les noms de fichiers ----------------------------------------------------------------------------------

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_DATE = re.compile(r"\d{4}[-_.]\d{1,2}[-_.]\d{1,2}|\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4}")
_HEURE = re.compile(r"\d{1,2}[h:.]\d{2}(?:[:.]\d{2})?")
_HEXA = re.compile(r"(?<![A-Za-z0-9])(?=[0-9a-fA-F]*\d)(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{7,}(?![A-Za-z0-9])")
_NOMBRE = re.compile(r"\d+")
_COPIE = re.compile(r"(?i)(?:\s*\(\d+\)|\s+(?:copie|copy)(?:\s*\d+)?)$")
_ETOILES = re.compile(r"\*(?:[\s._\-:,]*\*)+")


def _variables(texte: str) -> str:
    t = _UUID.sub("*", texte)
    t = _DATE.sub("*", t)
    t = _HEURE.sub("*", t)
    t = _HEXA.sub("*", t)
    t = _NOMBRE.sub("*", t)
    return _ETOILES.sub("*", t)


def extension(nom: str) -> str:
    suffixe = Path(nom).suffix
    return suffixe[1:].lower() if suffixe and len(suffixe) <= 6 else ""


def motif_nom(nom: str) -> str:
    """« Facture_2026-10-03.pdf » → « Facture_* » (sans l'extension, donnée à part)."""
    tige = Path(nom).stem if extension(nom) else nom
    tige = _COPIE.sub("", tige.strip())
    motif = _variables(tige).strip()
    return motif or "*"


def lieu(chemin: str | Path, maison: str | Path | None = None) -> str:
    """Un dossier en clair et généralisé : « ~/Documents/Factures/2026 » → « Documents/Factures/* »."""
    maison = Path(maison) if maison else Path.home()
    p = Path(chemin).expanduser()
    try:
        parties = list(p.relative_to(maison).parts)
        prefixe = ""
    except ValueError:
        parties = [x for x in p.parts if x != "/"]
        prefixe = "/"
    parties = [_variables(x) for x in parties[:4]]
    return (prefixe + "/".join(parties)) or "~"


# --- Les adresses web ---------------------------------------------------------------------------------------


def url_normalisee(url: str, segments: int = 1) -> str:
    """« https://mail.google.com/mail/u/0/#inbox » → « mail.google.com/mail ». Jamais de paramètres."""
    sans_schema = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", url.strip(), flags=re.I)
    sans_schema = re.split(r"[?#]", sans_schema, maxsplit=1)[0]
    hote, _, chemin = sans_schema.partition("/")
    hote = hote.rsplit("@", 1)[-1].split(":")[0].lower()
    if hote.startswith("www."):
        hote = hote[4:]
    gardes: list[str] = []
    for morceau in chemin.split("/"):
        if not morceau:
            continue
        if len(gardes) >= segments:
            break
        generalise = _variables(morceau)
        if generalise == "*" or len(morceau) > 40:
            break
        gardes.append(generalise)
    return "/".join([hote, *gardes])


# --- Les commandes ------------------------------------------------------------------------------------------

_SEPARATEURS = re.compile(r"\s*(&&|\|\||;)\s*")


def commande_normalisee(commande: str, maison: str | None = None) -> str:
    maison = maison or str(Path.home())
    c = " ".join(commande.replace("\\\n", " ").split())
    c = c.replace(maison, "~")
    c = re.sub(r"'[^']*'", "'*'", c)  # un texte entre guillemets (message de commit…) varie à chaque fois
    c = re.sub(r'"[^"]*"', '"*"', c)
    c = _UUID.sub("*", c)
    c = _HEXA.sub("*", c)
    c = re.sub(r"(?<![\w.~/\-])\d{3,}(?![\w])", "*", c)  # un nombre isolé (identifiant, port…), pas « python3 »
    return c


def sous_commandes(commande: str) -> list[str]:
    """« cd x && git pull ; make » → ["cd x", "git pull", "make"] (les guillemets sont respectés)."""
    morceaux, actuel, guillemet = [], [], ""
    i = 0
    while i < len(commande):
        c = commande[i]
        if guillemet:
            actuel.append(c)
            if c == guillemet:
                guillemet = ""
        elif c in "'\"":
            guillemet = c
            actuel.append(c)
        elif commande.startswith(("&&", "||"), i) or c == ";":
            morceaux.append("".join(actuel).strip())
            actuel = []
            i += 1 if c == ";" else 2
            continue
        else:
            actuel.append(c)
        i += 1
    morceaux.append("".join(actuel).strip())
    return [m for m in morceaux if m]


# --- Les tokens ---------------------------------------------------------------------------------------------


def tok_app(nom: str) -> str:
    return f"app:{nom}"


def tok_fenetre(appli: str, titre: str) -> str:
    return f"fen:{appli}:{_variables(titre)[:80]}"


def tok_url(url: str) -> str:
    return f"url:{url_normalisee(url)}"


def tok_deplacement(de: str, vers: str, nom: str, maison: str | None = None) -> str:
    return f"fmove:{lieu(de, maison)}→{lieu(vers, maison)} [{extension(nom)}, {motif_nom(nom)}]"


def tok_renommage(dossier: str, avant: str, apres: str, maison: str | None = None) -> str:
    return f"fren:{lieu(dossier, maison)} [{extension(apres)}, {motif_nom(avant)}→{motif_nom(apres)}]"


def tok_creation(dossier: str, nom: str, maison: str | None = None) -> str:
    return f"fcreate:{lieu(dossier, maison)} [{extension(nom)}, {motif_nom(nom)}]"


def tok_conversion(dossier: str, source: str, cible: str, maison: str | None = None) -> str:
    return f"fconv:{lieu(dossier, maison)} [{extension(source)}→{extension(cible)}, {motif_nom(cible)}]"


def tok_suppression(dossier: str, nom: str, maison: str | None = None) -> str:
    return f"fdel:{lieu(dossier, maison)} [{extension(nom)}, {motif_nom(nom)}]"


def tok_commande(commande: str, maison: str | None = None) -> str:
    return f"cmd:{commande_normalisee(commande, maison)}"


def tok_pont(source: str, destination: str) -> str:
    return f"clip:{source}→{destination}"
