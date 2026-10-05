"""La commande démarre vite : elle n'importe rien de lourd."""

import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]


def test_import_de_la_cli_rapide():
    debut = time.perf_counter()
    r = subprocess.run(
        [sys.executable, "-c", "import modules.demarrage.cli"], cwd=RACINE, capture_output=True, text=True
    )
    duree = time.perf_counter() - debut
    assert r.returncode == 0, r.stderr
    assert duree < 2.0, f"{duree:.2f} s"
