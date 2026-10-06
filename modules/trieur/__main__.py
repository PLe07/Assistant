"""python -m modules.trieur            → la surveillance en fond (lancée par le superviseur de l'Assistant)
python -m modules.trieur <commande> → la commande « trieur » (ajouter, statut, coffre, doctor…)"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from modules.trieur.cli import main

        sys.exit(main(sys.argv[1:]))
    from core.module import executer
    from modules.trieur.module import boucle

    executer("trieur", boucle)
