"""Ce dont chaque module a besoin pour tourner proprement sous le superviseur.

Un module est un fichier modules/<nom>.py qui définit une fonction `boucle(ctx)` et se
termine par :

    if __name__ == "__main__":
        executer("<nom>", boucle)

Le superviseur le lance comme un programme séparé : s'il plante, rien d'autre ne tombe.
"""

import signal
import sys
import threading
import traceback

from core import config, etat
from core.journal import journal


class Contexte:
    """Ce que le cœur met à disposition d'un module."""

    def __init__(self, nom: str):
        self.nom = nom
        self.log = journal(nom)
        self.arret = threading.Event()  # mis à True quand le superviseur demande l'arrêt
        self.etat = etat

    def reglage(self, cle: str, defaut=None):
        """Un réglage de ce module, relu à chaque appel (modifiable à chaud)."""
        return config.charger()["modules"].get(self.nom, {}).get(cle, defaut)

    def notifier(self, titre: str, message: str, urgent: bool = False):
        from core.notifications import notifier

        return notifier(titre, message, module=self.nom, urgent=urgent)

    def demander_a_claude(self, message: str, **options):
        from core.cerveau import demander

        return demander(message, module=self.nom, **options)

    def attendre(self, secondes: float) -> bool:
        """Attend sans bloquer l'arrêt. Renvoie True si on doit s'arrêter."""
        return self.arret.wait(secondes)


def executer(nom: str, boucle) -> None:
    ctx = Contexte(nom)
    signal.signal(signal.SIGTERM, lambda *_: ctx.arret.set())
    signal.signal(signal.SIGINT, lambda *_: ctx.arret.set())
    ctx.log.info("Démarré")
    try:
        boucle(ctx)
    except Exception as e:  # le superviseur le relancera ; on laisse une trace claire
        ctx.log.error("Plantage : %s\n%s", e, traceback.format_exc().rstrip())
        print(f"Plantage : {e}", file=sys.stderr)  # dernière ligne lue par le superviseur
        sys.exit(1)
    ctx.log.info("Arrêté proprement")
