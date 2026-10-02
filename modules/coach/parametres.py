"""Paramètres du coach : les 13 UE du DCG, et où sont rangés tes cours."""

import re

from core import config

DOSSIER = config.DONNEES / "coach"
COURS = DOSSIER / "cours"  # tes cours : un dossier par UE (ils restent sur ton Mac)
BASE = DOSSIER / "coach.db"  # questions, réponses et progrès
# Jours avant de revoir une question, selon sa « boîte » : 1 = ratée, elle revient dès ta prochaine séance de l'UE.
INTERVALLES = {1: 0, 2: 2, 3: 4, 4: 8, 5: 16}
MIN_QUESTIONS, MAX_QUESTIONS, PAR_DEFAUT = 3, 10, 5

UE = [  # le programme du DCG
    "UE1 Fondamentaux du droit",
    "UE2 Droit des sociétés et des groupements d'affaires",
    "UE3 Droit social",
    "UE4 Droit fiscal",
    "UE5 Économie contemporaine",
    "UE6 Finance d'entreprise",
    "UE7 Management",
    "UE8 Systèmes d'information de gestion",
    "UE9 Comptabilité",
    "UE10 Comptabilité approfondie",
    "UE11 Contrôle de gestion",
    "UE12 Anglais des affaires",
    "UE13 Communication professionnelle",
]


def ue_de(nom: str) -> str | None:
    """« DCG UE11 Contrôle de gestion », « ue 11 », « UE11-cours.pdf » → « UE11 Contrôle de gestion »."""
    m = re.search(r"\bUE\s*0?(\d{1,2})(?!\d)", nom, re.I)
    return UE[int(m[1]) - 1] if m and 1 <= int(m[1]) <= len(UE) else None


def nombre(texte: str | None) -> int:
    """Le nombre de questions demandé, ramené entre 3 et 10 (5 si ce n'est pas un nombre)."""
    m = re.search(r"\d+", texte or "")
    return max(MIN_QUESTIONS, min(MAX_QUESTIONS, int(m[0]))) if m else PAR_DEFAUT
