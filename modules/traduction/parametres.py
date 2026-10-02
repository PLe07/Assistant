"""Paramètres du module « traduction » (réglables dans reglages.json → modules.traduction)."""

from core import config
from modules.yeux import parametres as yeux
from modules.yeux.capture import TERMINAUX

DOSSIER = config.DONNEES / "traduction"
MODELE = DOSSIER / "modele"  # le modèle de traduction français → anglais, téléchargé une fois (~100 Mo)
URL_MODELE = "https://argos-net.com/v1/translate-fr_en-1_9.argosmodel"  # Argos Translate (libre, hors ligne)
ATTENTE = 0.15  # secondes laissées à l'appli pour afficher le point avant de lire la phrase
# Le mode clavier (applis qui cachent leur texte à macOS) : on attend que tu t'arrêtes de taper avant d'y toucher.
PAUSE = 0.35  # secondes sans touche
PAUSE_MAX = 30  # au-delà, la phrase est laissée (le point suivant la reprendra)
APPLIS_CLAVIER = ["Pages", "Keynote"]


def reglage(cle: str, defaut=None):
    return config.charger()["modules"].get("traduction", {}).get(cle, defaut)


def _liste(cle: str) -> list[str]:
    v = reglage(cle, [])
    return [str(x) for x in v if str(x).strip()] if isinstance(v, list) else []


def mots_min() -> int:
    v = reglage("mots_min", 3)
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else 3


def applis_exclues() -> list[str]:
    """Les mêmes que les yeux (mots de passe, messageries, l'icône), les Terminaux, et ta liste en plus."""
    return yeux.applis_exclues() + list(TERMINAUX) + _liste("applis_exclues")


def titres_exclus() -> list[str]:
    """Les mêmes que les yeux (banques, impôts, santé, navigation privée…), et ta liste en plus."""
    return yeux.titres_exclus() + _liste("titres_exclus")


def applis_clavier() -> list[str]:
    """Les applis qui cachent leur texte à macOS : il y est lu en le sélectionnant et le copiant, l'anglais est
    collé à la place (ton presse-papiers est remis comme avant). Pages et Keynote, et ta liste en plus."""
    return APPLIS_CLAVIER + _liste("applis_clavier")
