"""Un signal : un indice, son poids, et sa phrase d'explication en français simple."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Signal:
    code: str
    poids: int
    phrase: str
    critique: bool = False  # empêche tout verdict sous « Très suspect » (§3.3)
    technique: bool = True  # False : tiré du texte, il ne peut jamais faire baisser le score


class Niveau(Enum):
    AUCUN_SIGNE = 0
    PRUDENCE = 1
    TRES_SUSPECT = 2
    ARNAQUE = 3

    @property
    def pastille(self) -> str:
        return {0: "⚪", 1: "🟡", 2: "🟠", 3: "🔴"}[self.value]

    @property
    def libelle(self) -> str:
        return {0: "Pas de signe d'arnaque détecté", 1: "Prudence", 2: "Très suspect", 3: "Arnaque"}[self.value]

    @property
    def code(self) -> str:
        return {0: "pas_de_signe", 1: "prudence", 2: "tres_suspect", 3: "arnaque"}[self.value]

    @classmethod
    def depuis_code(cls, code: str) -> Niveau:
        for n in cls:
            if n.code == code:
                return n
        raise ValueError(code)


SEUIL_PRUDENCE = 20
SEUIL_TRES_SUSPECT = 45
SEUIL_ARNAQUE = 70


def niveau_du_score(score: int) -> Niveau:
    if score >= SEUIL_ARNAQUE:
        return Niveau.ARNAQUE
    if score >= SEUIL_TRES_SUSPECT:
        return Niveau.TRES_SUSPECT
    if score >= SEUIL_PRUDENCE:
        return Niveau.PRUDENCE
    return Niveau.AUCUN_SIGNE
