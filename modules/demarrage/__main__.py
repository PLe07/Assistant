"""python -m modules.demarrage            → la surveillance en fond (lancée par le superviseur de l'Assistant)
python -m modules.demarrage <commande> → la commande « demarrage » (scan, mesurer, rapport, doctor…)"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from modules.demarrage.cli import main

        sys.exit(main(sys.argv[1:]))
    from core.module import executer
    from modules.demarrage.module import boucle

    executer("demarrage", boucle)
