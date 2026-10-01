"""Paramètres du module « mails ».

Les réglages modifiables sont dans reglages.json → modules.mails.
Tes données (jetons Gmail, mémoire, règles perso) sont dans donnees/mails/ : jamais sur GitHub.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from core import config

CODE = Path(__file__).resolve().parent
DOSSIER = config.DONNEES / "mails"

CREDENTIALS = DOSSIER / "credentials.json"  # carte d'identité de l'appli (Google Cloud)
TOKEN = DOSSIER / "token.json"  # jeton d'accès Gmail
MEMOIRE = DOSSIER / "memoire.db"  # mails déjà traités
FICHIER_REGLES_PERSO = DOSSIER / "regles_perso.txt"
FICHIER_JAMAIS_ARCHIVER = DOSSIER / "jamais_archiver.txt"
FICHIER_PROMPT = CODE / "prompt_classification.md"
VERROU = DOSSIER / ".verrou"

GMAIL_ATTENDU = os.getenv("GMAIL_ATTENDU", "")  # garde-fou : seule boîte autorisée (dans .env)

LONGUEUR_EXTRAIT = 1500  # caractères du corps envoyés à Claude, au maximum
TAILLE_LOT = 10  # mails envoyés ensemble dans un même appel
MAX_PAR_PASSAGE = 50  # au-delà, la suite est traitée au passage suivant
TENTATIVES_MAX = 3  # mail que Claude n'arrive pas à classer : laissé tel quel après 3 essais


@dataclass(frozen=True)
class Bac:
    code: str  # code renvoyé par Claude
    etiquette: str  # nom de l'étiquette dans Gmail
    archiver: bool  # True = sortir de la boîte de réception (jamais supprimer)
    fond: str  # couleur de l'étiquette (palette imposée par Gmail)
    texte: str


BACS = {
    b.code: b
    for b in (
        Bac("important_repondre", "🔴 Important-Répondre", False, "#fb4c2f", "#ffffff"),
        Bac("action_deadline", "⏰ Action-Deadline", False, "#ffad47", "#000000"),
        Bac("a_lire", "🟡 À-lire", False, "#fad165", "#000000"),
        Bac("info_auto", "🟢 Info-Auto", True, "#16a766", "#ffffff"),
        Bac("poubelle", "⚫ Poubelle", True, "#434343", "#ffffff"),
    )
}


def reglage(cle: str, defaut=None):
    """Un réglage de reglages.json → modules.mails, relu à chaque appel."""
    return config.charger()["modules"].get("mails", {}).get(cle, defaut)


def preparer_dossier() -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    os.chmod(DOSSIER, 0o700)  # accessible à toi seul
