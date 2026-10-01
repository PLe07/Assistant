"""Notifications macOS natives, avec un garde anti-spam.

Avant chaque notification, le garde vérifie : pause, heures silencieuses, doublon
(même message dans les 6 dernières heures) et limite par heure selon le niveau de
proactivité. Une notification bloquée n'est pas perdue : elle est notée dans l'état.
"""

import hashlib
import subprocess
import sys
import time
from datetime import datetime

from core import config, etat
from core.journal import journal

LIMITE_PAR_HEURE = {0: 0, 1: 1, 2: 3, 3: 6}
FENETRE_DOUBLON = 6 * 3600

log = journal("notifications")


def _empreinte(module: str, titre: str, message: str) -> str:
    return hashlib.sha1(f"{module}|{titre}|{message}".encode()).hexdigest()


def en_heures_silencieuses(reglages: dict, maintenant: datetime | None = None) -> bool:
    maintenant = maintenant or datetime.now()
    debut, fin = reglages["heures_silencieuses"]["debut"], reglages["heures_silencieuses"]["fin"]
    actuelle = maintenant.strftime("%H:%M")
    if debut == fin:
        return False
    if debut < fin:  # ex. 13:00 → 14:00
        return debut <= actuelle < fin
    return actuelle >= debut or actuelle < fin  # passe minuit, ex. 22:30 → 07:30


def _afficher(titre: str, message: str) -> bool:
    """Notification macOS via osascript. Le texte passe en argument : aucun risque
    qu'un caractère spécial (guillemet…) casse ou détourne la commande."""
    if sys.platform != "darwin":
        log.warning("Notification non affichée (pas sur un Mac) : %s · %s", titre, message)
        return False
    script = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
              "-e", "end run"]
    try:
        r = subprocess.run(["osascript", *script, titre, message], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.error("Notification impossible : %s", e)
        return False
    if r.returncode != 0:
        log.error("Notification refusée par macOS : %s", r.stderr.strip())
        return False
    return True


def notifier(titre: str, message: str, module: str = "assistant", urgent: bool = False, test: bool = False) -> tuple[bool, str]:
    """Envoie une notification si le garde l'autorise. Renvoie (affichée ?, raison si bloquée).

    urgent : passe outre la limite par heure et les heures silencieuses (jamais la pause).
    test   : notification demandée à la main pour essayer, passe outre tout sauf la pause.
    """
    reglages = config.charger()
    empreinte = _empreinte(module, titre, message)
    maintenant = time.time()
    raison = ""
    if reglages["pause_globale"]:
        raison = "pause"
    elif not test and not urgent and en_heures_silencieuses(reglages):
        raison = "heures silencieuses"
    elif not test and etat.deja_envoyee(empreinte, maintenant - FENETRE_DOUBLON):
        raison = "doublon"
    elif not test and not urgent:
        limite = LIMITE_PAR_HEURE[reglages["niveau_proactivite"]]
        if etat.notifications_envoyees_depuis(maintenant - 3600) >= limite:
            raison = f"limite de {limite}/h (niveau {reglages['niveau_proactivite']})"

    affichee = not raison and _afficher(titre, message)
    if not raison and not affichee:
        raison = "échec de l'affichage"
    etat.noter_notification(module, titre, message, empreinte, affichee, raison)
    if affichee:
        log.info("Notification [%s] %s · %s", module, titre, message)
    else:
        log.info("Notification retenue (%s) [%s] %s", raison, module, titre)
    return affichee, raison
