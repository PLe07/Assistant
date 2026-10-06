"""Outils de texte communs au détecteur : forme normalisée (minuscules, sans accents) et nombres."""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'", "´": "'", "«": '"', "»": '"', " ": " ",
                              " ": " ", " ": " "})  # fmt: skip


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, apostrophes et espaces uniformes : la forme sur laquelle les règles cherchent."""
    t = unicodedata.normalize("NFKC", texte).translate(_APOSTROPHES)
    t = sans_accents(t).lower()
    return re.sub(r"[ \t]+", " ", t)


MONTANT = re.compile(r"(\d{1,3}(?:[ .]\d{3})*(?:[,.]\d{1,2})?)\s?(?:€|eur\b|euros?\b)", re.IGNORECASE)


def montants(texte: str) -> list[str]:
    """Les montants en euros, tels qu'écrits (« 1,99 € »)."""
    return [m.group(0).strip() for m in MONTANT.finditer(texte)]


TELEPHONE = re.compile(
    r"(?<![\d/=])(?:(?:\+|00)\s?33\s?\(?0?\)?\s?|0)([1-9])(?:[\s.\-]?\d{2}){4}(?!\d)"
    r"|(?<![\d/=])(?:\+|00)\s?(?!33)[1-9]\d{1,2}(?:[\s.\-]?\d{2,4}){3,5}(?!\d)"
)


def telephones(texte: str) -> list[str]:
    return [re.sub(r"\s+", " ", m.group(0)).strip() for m in TELEPHONE.finditer(texte)]


def chiffres(numero: str) -> str:
    c = re.sub(r"\D", "", numero)
    if c.startswith("0033"):
        return "0" + c[4:]
    if c.startswith("33") and len(c) == 11:
        return "0" + c[2:]
    return c


def est_surtaxe(numero: str) -> bool:
    """Numéros à valeur ajoutée les plus chers : 089x (et 0899)."""
    return chiffres(numero).startswith("089")
