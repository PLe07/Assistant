"""Le Trieur, en raccourci :  python trieur.py <commande>   (même chose que python -m modules.trieur)."""

import sys

from modules.trieur.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
