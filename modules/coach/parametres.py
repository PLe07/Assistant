"""Paramètres du coach (réglables dans reglages.json → modules.coach)."""

import re

from core import config

DOSSIER = config.DONNEES / "coach"
COURS = DOSSIER / "cours"  # tes cours : un dossier par matière (ils restent sur ton Mac)
BASE = DOSSIER / "coach.db"  # questions, réponses et progrès
INTERVALLES = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}  # jours avant de revoir une question, selon sa « boîte »
HEURE_LIMITE = "22:00"  # après, la série du jour n'est plus préparée toute seule
REESSAI = 30 * 60  # Claude indisponible à l'heure prévue : nouvel essai 30 min plus tard


def reglage(cle: str, defaut=None):
    return config.charger()["modules"].get("coach", {}).get(cle, defaut)


def heure() -> str:
    h = reglage("heure", "18:30")
    return h if isinstance(h, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", h) else "18:30"


def nombre() -> int:
    n = reglage("questions", 3)
    return n if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 10 else 3


def sans_support() -> list[str]:
    """Matières sans cours fourni : Claude interroge sur le programme général (questions « à vérifier »)."""
    liste = reglage("matieres_sans_support", ["Certification AMF"])
    return [x.strip() for x in liste if isinstance(x, str) and x.strip()] if isinstance(liste, list) else []
