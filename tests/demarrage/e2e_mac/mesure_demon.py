"""§9.6 — le démon réel pendant N secondes (10 minutes par défaut) : processeur moyen et mémoire maximale.

    cd ~/Assistant && .venv/bin/python tests/demarrage/e2e_mac/mesure_demon.py 600

Il lance sa propre surveillance (python -m modules.demarrage) dans un dossier de données temporaire, après un scan
de préparation (le cache codesign est chaud, comme en régime normal). Le processeur compte AUSSI les commandes
lancées par le démon (ps, launchctl, pmset, top) : resource.getrusage(RUSAGE_CHILDREN) les additionne quand le démon
s'arrête. Budgets du §4 : CPU moyen < 0,3 %, RAM < 40 Mo.
"""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
BUDGET_CPU_PCT, BUDGET_RAM_MO = 0.3, 40.0


def rss_ko(pid: int) -> int | None:
    sortie = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return int(sortie) if sortie.isdigit() else None


def mesurer(duree: float, pas: float = 5.0) -> dict[str, float]:
    sys.path.insert(0, str(RACINE))
    with tempfile.TemporaryDirectory(prefix="nettoyeur-mesure-") as dossier:
        env = {**os.environ, "DEMARRAGE_DOSSIER": dossier, "PYTHONUNBUFFERED": "1"}
        subprocess.run([sys.executable, "demarrage.py", "scan"], cwd=RACINE, env=env, check=True,
                       stdout=subprocess.DEVNULL)  # fmt: skip
        avant = resource.getrusage(resource.RUSAGE_CHILDREN)
        demon = subprocess.Popen([sys.executable, "-m", "modules.demarrage"], cwd=RACINE, env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
        debut, rss_max = time.monotonic(), 0
        try:
            while time.monotonic() - debut < duree:
                time.sleep(pas)
                if demon.poll() is not None:
                    raise SystemExit(f"Le démon s'est arrêté (code {demon.returncode}).")
                rss_max = max(rss_max, rss_ko(demon.pid) or 0)
        finally:
            ecoule = time.monotonic() - debut
            demon.send_signal(signal.SIGTERM)
            demon.wait(30)
        apres = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (apres.ru_utime + apres.ru_stime) - (avant.ru_utime + avant.ru_stime)
    return {"duree_s": round(ecoule), "cpu_s": round(cpu, 2), "cpu_moyen_pct": round(100 * cpu / ecoule, 3),
            "ram_max_mo": round(rss_max / 1024, 1)}  # fmt: skip


if __name__ == "__main__":
    r = mesurer(float(sys.argv[1]) if len(sys.argv) > 1 else 600)
    print(r)
    ok = r["cpu_moyen_pct"] < BUDGET_CPU_PCT and r["ram_max_mo"] < BUDGET_RAM_MO
    print("✅ dans les budgets" if ok else f"❌ hors budget (CPU < {BUDGET_CPU_PCT} %, RAM < {BUDGET_RAM_MO} Mo)")
    sys.exit(0 if ok else 1)
