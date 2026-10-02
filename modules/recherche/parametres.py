"""Paramètres de la recherche sourcée."""

from core import config

DOSSIER = config.DONNEES / "recherche"
HISTORIQUE = DOSSIER / "historique.json"  # tes 20 dernières recherches (pour la page avec les liens)
PAGE = DOSSIER / "recherche.html"
GARDER = 20

OUTILS = ["WebSearch", "WebFetch"]  # les SEULS outils permis à Claude pour cet appel
TOURS_MAX = 12  # allers-retours au plus (chercher, lire une page…) : borne le temps et le coût
DELAI_SECONDES = 240
MOTS_MAX = 80  # « courte, 5 lignes »
SOURCES_MAX = 5
DELAI_LIEN = 8  # secondes pour vérifier qu'un lien existe
