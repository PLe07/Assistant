"""Le scan quotidien de la surveillance, dans un processus à part (D-46) : `python -m modules.demarrage.scan_fils`.

Il scanne, enregistre en base comme `demarrage scan`, puis écrit sur sa dernière ligne, en JSON, les identifiants
vus pour la première fois et s'il s'agissait du tout premier scan. Le démon relit l'inventaire en base.
"""

from __future__ import annotations

import json
import sys

from modules.demarrage import config, travail
from modules.demarrage.systeme import Mac


def main() -> int:
    reglages, _ = config.charger()
    base = travail.ouvrir_base(reglages)
    try:
        inventaire, nouveaux, premier = travail.scanner(Mac(), base, reglages)
    finally:
        base.fermer()
    print(json.dumps({"nouveaux": nouveaux, "premier": premier, "fiches": len(inventaire.fiches)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
