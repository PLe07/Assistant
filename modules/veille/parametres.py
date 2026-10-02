"""Paramètres de la veille. Les sources se règlent dans reglages.json (« veille » → « sources »)."""

import re

from core import config

DOSSIER = config.DONNEES / "veille"
BASE = DOSSIER / "veille.db"  # les articles déjà vus (pour ne te montrer que les nouveautés)
PAGE = DOSSIER / "veille.html"  # la page de ta dernière veille, avec les liens cliquables

FRAICHEUR_JOURS = 30  # un article publié il y a plus longtemps n'est pas une nouveauté
GARDER_JOURS = 90  # les articles vus sont oubliés au bout de 90 jours
ENVOYES_MAX = 60  # au plus 60 titres envoyés à Claude par veille (les plus récents)
RETENUS_MAX = 8
DELAI_SECONDES = 20  # par site
TAILLE_MAX = 5_000_000  # un flux plus gros n'est pas lu (ce n'est pas un flux normal)

# Écartés sur ton Mac, sans demander à Claude : sans rapport avec le patrimoine ni le DCG.
HORS_SUJET = re.compile(
    r"\b(nomination|nommé|offres? d'emploi|recrutement|concours de la fonction|carte (d'identité|grise)|passeport"
    r"|permis de (conduire|chasser|pêche)|vaccin|météo|canicule|vigilance|élections?|vote par procuration"
    r"|jeux olympiques|vacances scolaires|soldes|heure d'été|heure d'hiver)\b", re.I)


def sources() -> list[dict]:
    """[{« nom », « adresse »}, …] d'après reglages.json."""
    return config.charger()["veille"]["sources"]
