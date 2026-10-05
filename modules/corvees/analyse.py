"""L'analyse du soir, dans un programme à part, lancé par le démon :  python -m modules.corvees.analyse <instant>

Le démon reste léger (sa mémoire ne dépasse pas les 120 Mo prévus, même avec un mois chargé), ses capteurs
continuent pendant l'analyse, et toute la mémoire de l'analyse est rendue au système dès qu'elle est finie.
Les réglages arrivent du démon (en JSON, sur l'entrée) ; les messages repartent vers son journal.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from modules.corvees import config, daemon, privacy, suite


def principal(argv: list[str], entree: TextIO | None = None, sortie: TextIO | None = None) -> int:
    entree = entree or sys.stdin
    sortie = sortie or sys.stdout
    maintenant = float(argv[0])
    texte = entree.read()
    reglages: dict[str, Any] = json.loads(texte) if texte.strip() else config.charger()[0]

    def dire(message: str) -> None:
        print(privacy.caviarder(message), file=sortie, flush=True)

    base = daemon.ouvrir(reglages)
    try:
        candidats = daemon.analyser_base(base, reglages, maintenant, dire)
    finally:
        base.fermer()
    suite.traiter(reglages, candidats, maintenant, dire)
    return 0


if __name__ == "__main__":  # pragma: no cover - lancé par le démon (testé à travers lui)
    sys.exit(principal(sys.argv[1:]))
