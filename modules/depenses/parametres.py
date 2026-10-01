"""Paramètres du traqueur de dépenses (reglages.json → modules.depenses : actif, mode, dossier)."""

from pathlib import Path

from core import config

DOSSIER = config.DONNEES / "depenses"
TABLEUR = DOSSIER / "depenses.csv"  # s'ouvre dans Numbers ou Excel
PHOTOS = DOSSIER / "recus"  # une COPIE de chaque reçu ajouté, rangée par mois
DEJA_VUS = DOSSIER / "deja_vus.json"  # empreinte de chaque photo déjà traitée (pour ne jamais la compter 2 fois)

EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".pdf"}
CATEGORIES = ["Alimentation", "Restaurants", "Transport", "Logement", "Études", "Santé", "Loisirs", "Shopping",
              "Abonnements", "Autre"]
PAIEMENTS = ["carte", "espèces", "autre", "inconnu"]
COLONNES = ["Date", "Commerçant", "Montant TTC (€)", "TVA (€)", "Catégorie", "Paiement", "Photo", "Ajoutée le"]
MONTANT_MAX = 20_000  # au-delà, c'est sûrement une erreur de lecture
STABLE_SECONDES = 3  # une photo encore en cours de copie (AirDrop…) attend son tour
ESSAIS_MAX = 3  # une photo que Claude n'arrive pas à lire n'est plus retentée (jusqu'au redémarrage)


def reglage(cle: str, defaut=None):
    return config.charger()["modules"].get("depenses", {}).get(cle, defaut)


def mode() -> str:
    """« test » (rien n'est écrit : une notification dit ce qui l'aurait été) ou « reel »."""
    return "reel" if reglage("mode", "test") == "reel" else "test"


def dossier_recus() -> Path:
    """Le dossier surveillé, où tu déposes tes photos de reçus (par défaut ~/Reçus)."""
    return Path(str(reglage("dossier", "~/Reçus") or "~/Reçus")).expanduser()
