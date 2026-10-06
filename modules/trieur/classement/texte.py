"""Le texte, mis à plat pour comparer : minuscules, sans accents (l'OCR les perd souvent), espaces simples."""

from __future__ import annotations

import re
import unicodedata

_ESPACES = re.compile(r"[ \t    ]+")
_COLONNE = re.compile(r"[ \t    ]{2,}")
_ESPACE = re.compile(r"(?<! )[ \t    ](?! )")


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def normaliser(texte: str, colonnes: bool = False) -> str:
    """« Facture n° 12 — Réglé » → « facture n° 12 - regle » (ligne par ligne : les retours sont gardés).
    colonnes=True : deux espaces ou plus restent deux espaces, la frontière entre deux colonnes (« Qté  249,99 »
    ne doit pas devenir « 1 249,99 »)."""
    t = sans_accents(texte.replace("’", "'").replace("‘", "'").replace("—", "-").replace("–", "-")).lower()
    t = t.replace("œ", "oe").replace("æ", "ae")
    if colonnes:
        return "\n".join(_ESPACE.sub(" ", _COLONNE.sub("  ", ligne)).strip() for ligne in t.splitlines())
    return "\n".join(_ESPACES.sub(" ", ligne).strip() for ligne in t.splitlines())


def espaces_simples(texte: str) -> str:
    return _ESPACES.sub(" ", texte).strip()
