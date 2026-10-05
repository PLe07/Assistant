"""python -m modules.corvees            → le démon (lancé par le superviseur de l'Assistant)
python -m modules.corvees <commande> → la commande « corvees » (rapport, accept, pause…)"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from modules.corvees.cli import main

        sys.exit(main(sys.argv[1:]))
    from core.module import executer
    from modules.corvees.daemon import boucle

    executer("corvees", boucle)
