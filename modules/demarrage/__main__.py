"""python -m modules.demarrage <commande> → la commande « demarrage » (scan, mesurer, rapport, doctor…)."""

import sys

if __name__ == "__main__":
    from modules.demarrage.cli import main

    sys.exit(main(sys.argv[1:]))
