"""Les durées et les heures dites en français (texte déjà normalisé : minuscules, sans accents, nombres en chiffres).

- « 10 minutes », « 1 h 30 », « 1 heure et demie », « une demi heure », « un quart d heure », « trois quarts d heure »,
  « 2 minutes 30 », « 90 secondes », « 1 minute et 30 secondes », « 10 » (minutes) → secondes ;
- « a 18 h », « a 18 h 30 », « a 18 heures 15 », « a midi », « a minuit » → (heure, minute).
Une durée doit être entre 1 seconde et 24 heures ; sinon None (« Je n'ai pas compris la durée »).
"""

from __future__ import annotations

import re

DUREE_MAX_S = 24 * 3600

_UNITE = {
    "s": 1, "sec": 1, "seconde": 1, "secondes": 1,
    "min": 60, "mn": 60, "minute": 60, "minutes": 60,
    "h": 3600, "heure": 3600, "heures": 3600,
}  # fmt: skip
_FRACTIONS = [
    (re.compile(r"^(?:une |1 )?demi(?:e)? (?:heure|h)$"), 1800),
    (re.compile(r"^(?:une |1 )?demi(?:e)? minute$"), 30),
    (re.compile(r"^(?:un |1 )?quart d (?:heure|h)$"), 900),
    (re.compile(r"^3 quarts? d (?:heure|h)$"), 2700),
]
_MORCEAU = re.compile(r"(\d+(?:\.\d+)?)\s*(secondes?|sec|s|minutes?|min|mn|heures?|h)\b")


def duree(texte: str) -> int | None:
    """Une durée en secondes, ou None si ce n'en est pas une (ou hors bornes)."""
    t = " ".join(texte.split())
    t = re.sub(r"^(?:de|d|pour|dans|sur|a|en)\s+", "", t)
    t = re.sub(r"\s+(?:s il te plait|stp|svp|merci|minuteur|timer)$", "", t)
    for motif, secondes in _FRACTIONS:
        if motif.match(t):
            return secondes
    total = 0.0
    reste = t
    trouve = False
    derniere_unite = 0
    while reste:
        m = _MORCEAU.match(reste)
        if m:
            unite = _UNITE[m.group(2)]
            total += float(m.group(1)) * unite
            derniere_unite = unite
            trouve = True
            reste = reste[m.end() :].strip()
            reste = re.sub(r"^et\s+", "", reste)
            continue
        if trouve and re.fullmatch(r"(?:et )?(?:demie?|la moitie)", reste):
            total += derniere_unite / 2  # « 1 heure et demie », « 2 minutes et demie »
            reste = ""
            break
        if trouve and derniere_unite == 3600 and re.fullmatch(r"(?:et )?(?:(?:1|un) )?quart|(?:et )?3 quarts?", reste):
            total += 2700 if reste.startswith(("3", "et 3")) else 900  # « 1 heure et quart », « … et trois quarts »
            reste = ""
            break
        if trouve and re.fullmatch(r"\d{1,2}", reste) and derniere_unite in (3600, 60):
            total += int(reste) * (60 if derniere_unite == 3600 else 1)  # « 1 h 30 », « 2 minutes 30 »
            reste = ""
            break
        if not trouve and re.fullmatch(r"\d{1,3}", reste):
            total = int(reste) * 60  # « minuteur 10 » : des minutes
            trouve = True
            reste = ""
            break
        return None
    if not trouve:
        return None
    secondes = round(total)
    return secondes if 1 <= secondes <= DUREE_MAX_S else None


_HEURE = re.compile(
    r"^(?:a\s+)?(\d{1,2})\s*(?:h|heures?)(?:\s*(\d{1,2}))?(?:\s*(?:minutes?|du matin|du soir|de l apres midi))?$"
)


def heure(texte: str) -> tuple[int, int] | None:
    """(heure, minute) d'une heure dite (« à 18 h 30 », « à midi ») ; None sinon."""
    t = " ".join(texte.split())
    if re.fullmatch(r"(?:a\s+)?midi(?:\s+et\s+demie?)?", t):
        return (12, 30) if "demi" in t else (12, 0)
    if re.fullmatch(r"(?:a\s+)?minuit(?:\s+et\s+demie?)?", t):
        return (0, 30) if "demi" in t else (0, 0)
    m = _HEURE.match(t)
    if not m:
        m2 = re.fullmatch(r"(?:a\s+)?(\d{1,2})\s*(?:h|heures?)\s+et\s+demie?", t)
        if not m2:
            return None
        h, mi = int(m2.group(1)), 30
    else:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if "du soir" in t or "de l apres midi" in t:
            h = h + 12 if h < 12 else h
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return h, mi
    return None


def dire_duree(secondes: int) -> str:
    """« 10 minutes », « 1 h 30 », « 45 secondes » : pour la bulle et la réponse parlée."""
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    if h:
        return f"{h} h {m:02d}" if m else f"{h} heure" + ("s" if h > 1 else "")
    if m:
        texte = f"{m} minute" + ("s" if m > 1 else "")
        return texte + (f" {s:02d}" if s else "")
    return f"{s} seconde" + ("s" if s > 1 else "")
