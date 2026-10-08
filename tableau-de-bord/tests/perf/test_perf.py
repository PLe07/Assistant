"""La performance (§9.5) : le vrai démon, avec ses réglages normaux (un tour par minute), pendant 30 minutes face au
faux écosystème. Processeur moyen sous 0,5 %, mémoire sous 100 Mo et stable, page chargée en moins de 300 ms, et
aucune alerte pour le module sain pendant tout ce temps.

Durée réglable pour un essai rapide : `TDB_DUREE_PERF_S=300 ./check.sh --complet` (30 minutes par défaut). Les
chiffres mesurés sont écrits dans `TDB_PERF_SORTIE` s'il est donné (pour PROGRESS.md et RAPPORT_FINAL.md).
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import time
import urllib.request
from pathlib import Path

import psutil
import pytest

from tests.faux_ecosysteme.harnais import Ecosysteme

pytestmark = pytest.mark.complet
DUREE_S = int(os.environ.get("TDB_DUREE_PERF_S", "1800"))
CHAUFFE_S = 60


def charger_page(port: int, jeton: str) -> float:
    debut = time.perf_counter()
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/?t={jeton}", timeout=10) as r:
        r.read()
    return (time.perf_counter() - debut) * 1000


def test_trente_minutes(tmp_path: Path) -> None:
    eco = Ecosysteme(tmp_path / "eco")
    eco.racine.mkdir()
    eco.preparer()
    mesures: dict[str, object] = {}
    pids: list[int] = []
    try:
        eco.demarrer()
        assert eco.demon is not None
        p = psutil.Process(eco.demon.pid)
        time.sleep(CHAUFFE_S)  # premier tour, référence d'intégrité, premières copies
        jeton = (eco.support / "jeton").read_text(encoding="utf-8").strip()
        port = int(eco.lire("SELECT valeur FROM meta WHERE cle = 'port'")[0]["valeur"])
        avant = p.cpu_times()
        debut = time.monotonic()
        memoire: list[float] = []
        pages: list[float] = []
        problemes_sain: set[str] = set()
        while time.monotonic() - debut < DUREE_S - CHAUFFE_S:
            time.sleep(15)
            memoire.append(p.memory_info().rss / 1024 / 1024)
            problemes_sain |= {r["cle"] for r in eco.problemes() if r["module"] == "tdbtest-sain"}
            if len(memoire) % 4 == 1:
                pages.append(charger_page(port, jeton))
        apres = p.cpu_times()
        duree = time.monotonic() - debut
        propre = (apres.user + apres.system) - (avant.user + avant.system)
        enfants = (apres.children_user + apres.children_system) - (avant.children_user + avant.children_system)
        tiers = max(1, len(memoire) // 3)
        mesures = {
            "duree_min": round((duree + CHAUFFE_S) / 60, 1),
            "cpu_pct": round(propre / duree * 100, 3),
            "cpu_avec_commandes_pct": round((propre + enfants) / duree * 100, 3),
            "memoire_max_mo": round(max(memoire), 1),
            "memoire_debut_mo": round(statistics.mean(memoire[:tiers]), 1),
            "memoire_fin_mo": round(statistics.mean(memoire[-tiers:]), 1),
            "page_mediane_ms": round(statistics.median(pages), 1),
            "page_max_ms": round(max(pages), 1),
            "tours": len(eco.lire("SELECT DISTINCT ts FROM echantillons")),
        }
        sortie = os.environ.get("TDB_PERF_SORTIE")
        if sortie:
            Path(sortie).write_text(json.dumps(mesures, indent=2), encoding="utf-8")
        print("\nPERF", json.dumps(mesures))
        assert mesures["cpu_pct"] < 0.5, mesures  # type: ignore[operator]
        assert mesures["memoire_max_mo"] < 100, mesures  # type: ignore[operator]
        assert mesures["memoire_fin_mo"] - mesures["memoire_debut_mo"] < 10, mesures  # type: ignore[operator]
        assert mesures["page_mediane_ms"] < 300 and mesures["page_max_ms"] < 300, mesures  # type: ignore[operator]
        assert problemes_sain == set(), problemes_sain
        assert not any("tdbtest-sain" in n["cles"] for n in eco.notifications())
        assert eco.espion.read_text(encoding="utf-8") == ""
        assert eco.ouverts_chez_les_modules() == [] and eco.verrous_vus_par_les_modules() == []
    finally:
        pids = eco.arreter()
    shutil.rmtree(eco.racine)
    restants = [x for x in pids if psutil.pid_exists(x) and psutil.Process(x).status() != psutil.STATUS_ZOMBIE]
    assert restants == []
