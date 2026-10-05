"""Mesure le démon réel (§9.5) : CPU moyen, mémoire maximale, taille de la base, pendant N secondes.

    python tests/corvees/perf/mesure_demon.py 600          # 10 minutes (le démon doit tourner)

Le CPU moyen est calculé sur le temps processeur consommé (ps -o time), pas sur un instantané. Budgets : CPU
moyen < 1 %, mémoire < 120 Mo, base < 200 Mo.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def pid_du_demon() -> int | None:
    # « python -m modules.corvees » sans argument : le démon (avec un argument, c'est la commande)
    sortie = subprocess.run(["pgrep", "-f", "--", r"modules\.corvees$"], capture_output=True, text=True)
    pids = [int(p) for p in sortie.stdout.split()]
    return pids[0] if pids else None


def secondes(temps: str) -> float:
    """« 01:02:03 », « 02:03 », « 1-02:03:04 » ou « 0:01.23 » (macOS) → secondes."""
    jours = 0
    if "-" in temps:
        j, temps = temps.split("-", 1)
        jours = int(j)
    parties = [float(x) for x in temps.strip().split(":")]
    total = 0.0
    for x in parties:
        total = total * 60 + x
    return jours * 86400 + total


def releve(pid: int) -> tuple[float, int] | None:
    """(temps CPU en secondes, mémoire résidente en Ko)."""
    sortie = subprocess.run(["ps", "-o", "time=,rss=", "-p", str(pid)], capture_output=True, text=True).stdout.split()
    return (secondes(sortie[0]), int(sortie[1])) if len(sortie) == 2 else None


def mesurer(duree: float, pas: float = 5.0, base: Path | None = None) -> dict[str, float]:
    pid = pid_du_demon()
    if pid is None:
        raise SystemExit("Le démon ne tourne pas (python assistant.py activer corvees, puis attends 2 s).")
    debut = time.monotonic()
    premier = releve(pid)
    if premier is None:
        raise SystemExit("Le démon s'est arrêté.")
    rss_max = premier[1]
    dernier = premier
    while time.monotonic() - debut < duree:
        time.sleep(pas)
        r = releve(pid)
        if r is None:
            raise SystemExit("Le démon s'est arrêté pendant la mesure.")
        dernier = r
        rss_max = max(rss_max, r[1])
    ecoule = time.monotonic() - debut
    resultat = {
        "pid": pid,
        "duree_s": round(ecoule),
        "cpu_moyen_pct": round(100 * (dernier[0] - premier[0]) / ecoule, 3),
        "ram_max_mo": round(rss_max / 1024, 1),
    }
    if base is not None and base.exists():
        resultat["base_mo"] = round(sum(p.stat().st_size for p in base.parent.glob(base.name + "*")) / 1e6, 2)
    return resultat


if __name__ == "__main__":
    duree = float(sys.argv[1]) if len(sys.argv) > 1 else 600
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from modules.corvees import config

    reglages, _ = config.charger()
    r = mesurer(duree, base=config.dossier_donnees(reglages) / "corvees.db")
    print(r)
    ok = r["cpu_moyen_pct"] < 1 and r["ram_max_mo"] < 120 and r.get("base_mo", 0) < 200
    print("✅ dans les budgets (CPU < 1 %, RAM < 120 Mo, base < 200 Mo)" if ok else "❌ hors budget")
    sys.exit(0 if ok else 1)
