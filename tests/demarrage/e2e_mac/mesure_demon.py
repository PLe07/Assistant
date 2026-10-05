"""§9.6 — le démon réel pendant N secondes (10 minutes par défaut) : processeur moyen et mémoire maximale.

    cd ~/Assistant && .venv/bin/python tests/demarrage/e2e_mac/mesure_demon.py 600

Il lance sa propre surveillance (python -m modules.demarrage) dans un dossier de données temporaire, après un scan
de préparation (le cache codesign est chaud, comme en régime normal). Le processeur compte AUSSI les commandes
lancées par le démon (ps, launchctl, pmset, top) : resource.getrusage(RUSAGE_CHILDREN) les additionne quand le démon
s'arrête. Budgets du §4 : CPU moyen < 0,3 %, RAM < 40 Mo.

Il affiche aussi le détail par commande (noté par le démon, D-42) : en cas de dépassement, on sait laquelle coûte.

Le démon refait son scan quotidien au début de la mesure (D-46) : la mémoire maximale le compte donc. Ce scan
tourne dans un processus fils ; son processeur est compté à part et ramené à la journée (un scan par jour), car
le budget de processeur vise la surveillance en régime normal, pas un scan qui n'a lieu qu'une fois par jour.
"""

from __future__ import annotations

import json
import os
import resource
import signal
import sqlite3
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
        with sqlite3.connect(Path(dossier) / "demarrage.db") as db:  # le scan quotidien est « dû » : il le refera
            db.execute("UPDATE etat SET valeur = '0' WHERE cle = 'dernier_scan'")
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
        couts = couts_notes(Path(dossier) / "demarrage.db")
    cpu = (apres.ru_utime + apres.ru_stime) - (avant.ru_utime + avant.ru_stime)
    scan = couts.get(Path(sys.executable).name, {}).get("processeur_s", 0.0)  # le scan quotidien (processus fils)
    regime = 100 * (cpu - scan) / ecoule + 100 * scan / 86400  # un scan par jour, ramené à la seconde
    return {"duree_s": round(ecoule), "cpu_s": round(cpu, 2), "cpu_moyen_pct": round(100 * cpu / ecoule, 3),
            "scan_cpu_s": round(scan, 2), "cpu_regime_pct": round(regime, 3), "ram_max_mo": round(rss_max / 1024, 1),
            "commandes": couts}  # fmt: skip


def couts_notes(base: Path) -> dict[str, dict[str, float]]:
    try:
        with sqlite3.connect(base) as db:
            ligne = db.execute("SELECT valeur FROM etat WHERE cle = 'couts_commandes'").fetchone()
    except sqlite3.Error:
        return {}
    return json.loads(ligne[0]) if ligne else {}


def afficher(r: dict) -> None:
    commandes = r.pop("commandes", {})
    print(r)
    enfants = sum(c.get("processeur_s", 0.0) for c in commandes.values())
    print(f"   dont Python lui-même ≈ {max(0.0, r['cpu_s'] - enfants):.2f} s, et les commandes qu'il lance :")
    for nom, c in commandes.items():
        if "appels" in c:
            print(
                f"   · {nom} : {c['appels']} fois, {c['processeur_s']:.2f} s de processeur, {c['reel_s']:.1f} s en tout"
            )
        else:
            print(f"   · {nom} : {c.get('memoire_mo', 0)} Mo")


if __name__ == "__main__":
    r = mesurer(float(sys.argv[1]) if len(sys.argv) > 1 else 600)
    afficher(r)
    print(f"   régime normal (scan quotidien ramené à la journée) : {r['cpu_regime_pct']} % de processeur")
    ok = r["cpu_regime_pct"] < BUDGET_CPU_PCT and r["ram_max_mo"] < BUDGET_RAM_MO
    print("✅ dans les budgets" if ok else f"❌ hors budget (CPU < {BUDGET_CPU_PCT} %, RAM < {BUDGET_RAM_MO} Mo)")
    sys.exit(0 if ok else 1)
