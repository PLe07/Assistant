"""Le détecteur de corvées, en raccourci :  python corvees.py <commande>  (même chose que python -m modules.corvees)."""

import sys

from modules.corvees.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
