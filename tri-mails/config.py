"""Réglages du tri : tout ce qu'on peut ajuster sans toucher à la logique."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DOSSIER = Path(__file__).resolve().parent
load_dotenv(DOSSIER / ".env")

# --- Les 5 bacs -------------------------------------------------------------


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

# --- Gmail ------------------------------------------------------------------

GMAIL_ATTENDU = os.getenv("GMAIL_ATTENDU", "")  # garde-fou : seule boîte autorisée
LONGUEUR_EXTRAIT = 1500  # caractères du corps envoyés à Claude, au maximum

# --- Claude (via l'abonnement, avec Claude Code) -----------------------------

MODELE = os.getenv("MODELE", "sonnet")  # "sonnet" (recommandé) ou "opus"
EFFORT = "low"  # réflexion courte : suffisant pour trier, économise le quota
TAILLE_LOT = 10  # mails envoyés ensemble dans un même appel
DELAI_CLAUDE_SECONDES = 180

FICHIER_PROMPT = DOSSIER / "prompt_classification.md"
FICHIER_REGLES_PERSO = DOSSIER / "regles_perso.txt"  # local, jamais sur GitHub

# --- Pré-tri gratuit (sans appeler Claude) ----------------------------------
# Un expéditeur cité dans regles_perso.txt passe toujours par Claude.

REGLE_R1_PROMOTIONS = True  # Promotions + lien de désinscription → poubelle
REGLE_R2_RESEAUX_SOCIAUX = True  # Réseaux sociaux + expéditeur no-reply → info_auto
