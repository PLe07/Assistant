"""Paramètres du module « oreilles » (réglables dans reglages.json → modules.oreilles)."""

from core import config

DOSSIER = config.DONNEES / "oreilles"
MODELES = DOSSIER / "modeles"  # modèle de transcription, téléchargé une fois
FICHIER_DECLENCHEURS = DOSSIER / "declencheurs.txt"  # tes phrases-déclencheurs en plus (une par ligne)

TAUX = 16000  # échantillons par seconde (ce qu'attend la transcription)
BLOC = 512  # 32 ms de son par bloc

# Seuils de confiance, vérifications par heure et durées de vie des aides : core/aides.py
SILENCE_NUMERIQUE_ALERTE = 10  # secondes sans aucun son = micro refusé par macOS (ou bloqué)
REOUVERTURE_APRES = 30  # micro muet : on le rouvre (veille du Mac, micro débranché ou changé…)
ALERTE_APRES = 60  # micro toujours muet après ces essais : notification


def reglage(cle: str, defaut=None):
    return config.charger()["modules"].get("oreilles", {}).get(cle, defaut)

