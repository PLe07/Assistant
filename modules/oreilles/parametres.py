"""Paramètres du module « oreilles » (réglables dans reglages.json → modules.oreilles)."""

from core import config

DOSSIER = config.DONNEES / "oreilles"
MODELES = DOSSIER / "modeles"  # modèle de transcription, téléchargé une fois
FICHIER_DECLENCHEURS = DOSSIER / "declencheurs.txt"  # tes phrases-déclencheurs en plus (une par ligne)

TAUX = 16000  # échantillons par seconde (ce qu'attend la transcription)
BLOC = 512  # 32 ms de son par bloc

# Selon le niveau de proactivité (reglages.json → niveau_proactivite)
SEUIL_CONFIANCE = {0: None, 1: 90, 2: 80, 3: 70}  # confiance minimale de Claude pour te proposer une aide
VERIFICATIONS_PAR_HEURE = {0: 0, 1: 2, 2: 4, 3: 8}  # appels « puis-je aider ? » au maximum par heure
SEUIL_MOT_APPEL = 50  # « Assistant, … » : tu t'adresses à lui, on est moins exigeant

DUREE_VIE_EXTRAIT = 30 * 60  # l'extrait (en mémoire vive uniquement) est oublié après 30 min
DUREE_VIE_AIDE = 2 * 3600  # une aide proposée disparaît du menu après 2 h
SILENCE_NUMERIQUE_ALERTE = 10  # secondes de zéros absolus = micro refusé par macOS


def reglage(cle: str, defaut=None):
    return config.charger()["modules"].get("oreilles", {}).get(cle, defaut)


def niveau() -> int:
    return config.charger()["niveau_proactivite"]
