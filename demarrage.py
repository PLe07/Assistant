"""Le Nettoyeur de démarrage, en raccourci :  python demarrage.py <commande>
(même chose que python -m modules.demarrage)."""

import sys

from modules.demarrage.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
