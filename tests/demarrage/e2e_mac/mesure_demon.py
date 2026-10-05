"""§9.6 — le démon réel pendant N secondes (10 minutes par défaut) : processeur moyen et mémoire maximale.

    cd ~/Assistant && .venv/bin/python tests/demarrage/e2e_mac/mesure_demon.py 600

Il lance sa propre surveillance (python -m modules.demarrage) dans un dossier de données temporaire, après un scan
de préparation (le cache codesign est chaud, comme en régime normal). Le processeur compte AUSSI les commandes
lancées par le démon (ps, launchctl, pmset, top) : resource.getrusage(RUSAGE_CHILDREN) les additionne quand le démon
s'arrête. Il affiche le détail par commande (noté par le démon, D-42). Budgets du §4 : CPU moyen < 0,3 %, RAM < 40 Mo.

Ce que « CPU moyen » veut dire (D-47) : la moyenne sur une journée de surveillance. Une fenêtre de 10 minutes compte
en entier ce qui n'arrive qu'une fois par jour : le lancement de Python à la connexion et le scan quotidien, que le
démon refait ici au début de la mesure (D-46). Le script les sépare donc :
- le régime : le processeur du démon ET de ses commandes après les 150 premières secondes, plus « top » (une fois
  toutes les 30 min, mesuré à part) ;
- le ponctuel : tout le reste de la fenêtre (lancement, scan), ramené à la journée (une fois par jour).
La fenêtre brute est affichée aussi. La mémoire maximale, elle, est mesurée sur toute la fenêtre, scan compris.
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
from typing import Any

RACINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RACINE))
from modules.demarrage import config  # noqa: E402
from modules.demarrage.mesure import energie  # noqa: E402
from modules.demarrage.mesure.echantillonneur import temps_ps  # noqa: E402

BUDGET_CPU_PCT, BUDGET_RAM_MO = 0.3, 40.0
DEBUT_REGIME_S = 150.0  # après le lancement et le premier tour (scan quotidien compris)
JOUR_S = 86400.0


def rss_ko(pid: int) -> int | None:
    sortie = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return int(sortie) if sortie.isdigit() else None


def cpu_ps(pid: int) -> float | None:
    """Le processeur consommé par le démon lui-même (pas ses commandes) depuis son lancement."""
    return temps_ps(subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout)


def cpu_enfants() -> float:
    u = resource.getrusage(resource.RUSAGE_CHILDREN)
    return u.ru_utime + u.ru_stime


def cout_de_top() -> float:
    """Ce que coûte un relevé d'énergie (« top »), lancé une fois ici : le démon n'en fait qu'un toutes les 30 min."""
    avant = cpu_enfants()
    subprocess.run(energie.COMMANDE, capture_output=True, timeout=30)
    return cpu_enfants() - avant


def moyenne_du_jour(cpu_total_s: float, ecoule_s: float, regime_cpu_s: float, regime_duree_s: float,
                    top_s: float, top_pas_s: float) -> dict[str, float]:  # fmt: skip
    """La moyenne sur une journée : le régime observé + top à son rythme + le ponctuel (lancement, scan) une fois."""
    regime_pct = 100 * regime_cpu_s / regime_duree_s
    ponctuel_s = max(0.0, cpu_total_s - regime_cpu_s / regime_duree_s * ecoule_s)
    jour_pct = regime_pct + 100 * top_s / top_pas_s + 100 * ponctuel_s / JOUR_S
    return {"regime_pct": round(regime_pct, 3), "ponctuel_s": round(ponctuel_s, 2), "jour_pct": round(jour_pct, 3)}


def total_commandes(couts: dict[str, dict[str, float]]) -> float:
    return sum(c.get("processeur_s", 0.0) for c in couts.values() if "appels" in c)


def mesurer(duree: float, pas: float = 5.0) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nettoyeur-mesure-") as dossier:
        env = {**os.environ, "DEMARRAGE_DOSSIER": dossier, "PYTHONUNBUFFERED": "1"}
        base = Path(dossier) / "demarrage.db"
        subprocess.run([sys.executable, "demarrage.py", "scan"], cwd=RACINE, env=env, check=True,
                       stdout=subprocess.DEVNULL)  # fmt: skip
        with sqlite3.connect(base) as db:  # le scan quotidien est « dû » : il le refera
            db.execute("UPDATE etat SET valeur = '0' WHERE cle = 'dernier_scan'")
        avant = cpu_enfants()
        demon = subprocess.Popen([sys.executable, "-m", "modules.demarrage"], cwd=RACINE, env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
        debut, rss_max = time.monotonic(), 0
        debut_regime = min(DEBUT_REGIME_S, duree / 2)
        repere: tuple[float, float, float] | None = None  # (instant, processeur du démon, de ses commandes)
        try:
            while time.monotonic() - debut < duree:
                time.sleep(pas)
                if demon.poll() is not None:
                    raise SystemExit(f"Le démon s'est arrêté (code {demon.returncode}).")
                rss_max = max(rss_max, rss_ko(demon.pid) or 0)
                if repere is None and time.monotonic() - debut >= debut_regime:
                    repere = (time.monotonic(), cpu_ps(demon.pid) or 0.0, total_commandes(couts_notes(base)))
            fin_regime, cpu_demon_fin = time.monotonic(), cpu_ps(demon.pid) or 0.0
        finally:
            ecoule = time.monotonic() - debut
            demon.send_signal(signal.SIGTERM)
            demon.wait(30)
        cpu = cpu_enfants() - avant
        couts = couts_notes(base)
    top_s = cout_de_top()
    if repere is None:
        raise SystemExit("Mesure trop courte pour séparer le lancement du régime.")
    regime_cpu = (cpu_demon_fin - repere[1]) + (total_commandes(couts) - repere[2])
    jour = moyenne_du_jour(cpu, ecoule, regime_cpu, fin_regime - repere[0], top_s,
                           config.DEFAUTS["echantillonnage"]["energie_pas_s"])  # fmt: skip
    return {"duree_s": round(ecoule), "cpu_s": round(cpu, 2), "cpu_fenetre_pct": round(100 * cpu / ecoule, 3),
            **jour, "top_s": round(top_s, 2), "ram_max_mo": round(rss_max / 1024, 1), "commandes": couts}  # fmt: skip


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
    print(f"   fenêtre brute de {r['duree_s']} s (lancement et scan quotidien compris) : {r['cpu_fenetre_pct']} %")
    print(f"   régime : {r['regime_pct']} % · top toutes les 30 min : {r['top_s']} s · ponctuel (lancement + scan, "
          f"une fois par jour) : {r['ponctuel_s']} s")  # fmt: skip
    print(f"   → moyenne sur une journée : {r['jour_pct']} % de processeur")
    ok = r["jour_pct"] < BUDGET_CPU_PCT and r["ram_max_mo"] < BUDGET_RAM_MO
    print("✅ dans les budgets" if ok else f"❌ hors budget (CPU < {BUDGET_CPU_PCT} %, RAM < {BUDGET_RAM_MO} Mo)")
    sys.exit(0 if ok else 1)
