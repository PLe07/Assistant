"""Module de test « battement » : prouve que le superviseur lance, surveille et relance.

Il écrit une ligne dans le journal toutes les N secondes (reglages.json →
modules.battement.toutes_les_secondes). Il ne touche à rien d'autre.
`python assistant.py test-plantage` lui demande de planter une fois, pour vérifier
que le superviseur le relance tout seul.
"""

import time

from core.module import executer

CLE_PLANTAGE = "battement_planter"


def boucle(ctx) -> None:
    n, prochain = 0, 0.0
    while not ctx.attendre(1):
        if ctx.etat.lire(CLE_PLANTAGE):
            ctx.etat.effacer(CLE_PLANTAGE)
            raise RuntimeError("plantage simulé à ta demande (test du superviseur)")
        if time.time() >= prochain:
            n += 1
            ctx.log.info("Battement n°%d : tout va bien", n)
            prochain = time.time() + max(1, int(ctx.reglage("toutes_les_secondes", 60)))


if __name__ == "__main__":
    executer("battement", boucle)
