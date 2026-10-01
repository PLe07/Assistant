"""Paramètres du module « yeux » (réglables dans reglages.json → modules.yeux)."""

from core import config

DOSSIER = config.DONNEES / "yeux"
FICHIER_DECLENCHEURS = DOSSIER / "declencheurs.txt"  # tes mots-déclencheurs en plus (un par ligne)

ABSENT_APRES = 5 * 60  # sans clavier ni souris depuis 5 min : tu n'es pas là, on ne regarde pas
EXTRAIT_MAX = 1500  # caractères au plus envoyés à Claude
OUBLI_SIGNAL = 90  # un signal disparu plus de 90 s (tu as changé de fenêtre) repart de zéro
REPOS_SIGNAL = 30 * 60  # un même signal ne redéclenche pas avant 30 min

# Combien de temps un signal doit rester à l'écran avant qu'on se dise que tu bloques (secondes)
DELAIS = {"erreur": 180, "formulaire": 300, "question": 180, "perso": 0}

# Toujours exclues, en plus de ta liste (reglages.json → modules.yeux.applis_exclues / titres_exclus).
# Une appli est reconnue par son nom ou son identifiant ; un site par le titre de la fenêtre.
APPLIS_EXCLUES = [
    "Mots de passe", "Passwords", "Trousseaux d'accès", "Keychain Access", "1Password", "Bitwarden",
    "Dashlane", "KeePassXC", "LastPass", "Messages", "WhatsApp", "Signal", "Telegram", "Messenger",
    "com.apple.Passwords", "com.apple.keychainaccess", "com.apple.MobileSMS",
    "Python",  # l'icône de l'assistant elle-même (ses fenêtres d'aide)
]
# Pas regardées, non par discrétion mais parce que c'est inutile : tu y parles déjà à Claude directement
# (sinon nos échanges, pleins de mots comme « erreur », déclenchent des vérifications pour rien).
APPLIS_IGNOREES = ["Claude", "com.anthropic.claudefordesktop"]
TITRES_EXCLUS = [
    "banque", "bank", "revolut", "boursorama", "bnp", "société générale", "societe generale", "crédit agricole",
    "credit agricole", "crédit mutuel", "credit mutuel", "caisse d'épargne", "caisse d'epargne", "lcl", "cic",
    "banque postale", "fortuneo", "hello bank", "n26", "qonto", "paypal", "lydia", "impots.gouv", "impôts",
    "ameli", "doctolib", "navigation privée", "private browsing", "mot de passe", "password",
]


def reglage(cle: str, defaut=None):
    return config.charger()["modules"].get("yeux", {}).get(cle, defaut)


def intervalle() -> int:
    v = reglage("toutes_les_secondes", 30)
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 10 else 30


def mode() -> str:
    """« journal » (ce qui aurait déclenché est seulement noté) ou « reel ». En cas de doute : journal."""
    return "reel" if reglage("mode", "journal") == "reel" else "journal"


def _liste(cle: str) -> list[str]:
    v = reglage(cle, [])
    return [str(x) for x in v if str(x).strip()] if isinstance(v, list) else []


def applis_exclues() -> list[str]:
    return APPLIS_EXCLUES + _liste("applis_exclues")


def titres_exclus() -> list[str]:
    return TITRES_EXCLUS + _liste("titres_exclus")
