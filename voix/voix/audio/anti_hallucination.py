"""Le filtre anti-hallucination de Whisper (§4.2) : une sortie douteuse devient « rien entendu », jamais une action.

Rejeté :
- les phrases que Whisper invente sur du silence ou du bruit (« Sous-titres réalisés par… », « Merci d'avoir
  regardé », « Abonnez-vous »…), entières ou collées en fin de phrase (on les retire alors) ;
- une transcription alors que le détecteur de voix n'a pas entendu de parole ;
- les répétitions anormales (« ouvre ouvre ouvre ouvre… », une même suite de mots trois fois), et plus de mots que
  la parole ne permet d'en dire ;
- un texte sans lettres, ou écrit dans un autre alphabet.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CONNUES = [
    r"sous[- ]?titr\w*(?: (?:r[ée]alis[ée]s?|fait|faits|cr[ée]{1,2}s?) par)?.*",
    r"(?:merci|merci beaucoup) d'avoir regard[ée]\w*.*",
    r"merci de (?:votre|ton) (?:attention|[ée]coute).*",
    r"merci (?:à tous|pour votre attention).*",
    r"abonnez[- ]vous.*",
    r"n'h[ée]sitez pas à (?:vous abonner|liker|commenter|partager).*",
    r"(?:pour )?plus d'informations?,? (?:rendez-vous|visitez).*",
    r"(?:soci[ée]t[ée] )?radio[- ]canada.*",
    r".*amara\.org.*",
    r"(?:\[|\()?(?:musique|applaudissements|rires|silence|bruit|inaudible)(?:\]|\))?",
    r"♪+.*",
    r"(?:à|a) (?:bientôt|la prochaine|demain)(?: pour (?:une|un) (?:nouvelle?|autre) (?:vidéo|épisode))?",
    r"au revoir(?: et à bientôt)?",
    r"c'est la fin de (?:la|cette) vid[ée]o.*",
    r"traduit par.*",
    r"transcription (?:par|r[ée]alis[ée]e par).*",
]
_CONNUES = re.compile(r"^(?:" + "|".join(CONNUES) + r")$", re.IGNORECASE)
# Collées après une vraie phrase : « ouvre Safari. Sous-titres réalisés par la communauté d'Amara.org »
_QUEUES = re.compile(r"[.!?…]\s+(?:" + "|".join(CONNUES[:9]) + r")$", re.IGNORECASE)
MOTS_PAR_SECONDE_MAX = 6.0
# Un « non » dit vite ne dure que 0,13 s de parole détectée : seuil juste sous les 96 ms qui déclenchent l'écoute.
PAROLE_MIN_S = 0.09


@dataclass(frozen=True)
class Verdict:
    texte: str | None  # None : rejeté
    raison: str = ""


def _propre(texte: str) -> str:
    t = unicodedata.normalize("NFC", texte).replace("’", "'")
    return re.sub(r"\s+", " ", t).strip(' \t\n-–—"«»')


def _lettres_latines(texte: str) -> bool:
    lettres = [c for c in texte if c.isalpha()]
    if not lettres:
        return False
    latines = sum(1 for c in lettres if "LATIN" in unicodedata.name(c, ""))
    return latines / len(lettres) >= 0.9


def _repetition(mots: list[str]) -> bool:
    """Une suite de 1 à 4 mots répétée trois fois de suite ou plus."""
    for n in range(1, 5):
        for i in range(0, len(mots) - 3 * n + 1):
            bloc = mots[i : i + n]
            if mots[i + n : i + 2 * n] == bloc and mots[i + 2 * n : i + 3 * n] == bloc:
                return True
    return False


def filtrer(texte: str, parole_s: float) -> Verdict:
    """Le texte à comprendre, ou None avec la raison du rejet. `parole_s` : la parole entendue par le détecteur."""
    t = _propre(texte)
    if parole_s < PAROLE_MIN_S:
        return Verdict(None, "aucune parole entendue")
    if not t or not _lettres_latines(t):
        return Verdict(None, "rien de lisible")
    m = _QUEUES.search(t)
    if m:
        t = t[: m.start() + 1].strip()  # la vraie phrase, sans la fin inventée
    if _CONNUES.match(t.rstrip(".!?… ").strip()):
        return Verdict(None, "phrase inventée connue")
    mots = re.findall(r"[\w']+", t.lower())
    if not mots:
        return Verdict(None, "rien de lisible")
    if _repetition(mots):
        return Verdict(None, "répétition anormale")
    if len(mots) > MOTS_PAR_SECONDE_MAX * parole_s + 4:
        return Verdict(None, "trop de mots pour la parole entendue")
    return Verdict(t)
