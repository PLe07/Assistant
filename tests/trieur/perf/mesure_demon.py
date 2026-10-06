"""Lancé dans un processus à part par test_perf.py : le démon au repos dans un bac à sable, puis un document.

python -m tests.trieur.perf.mesure_demon DOSSIER   → une ligne JSON (processeur par tour, mémoire maximale)
"""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path


def memoire_max_mo() -> float:
    """Le pic de mémoire de CE programme. Sous Linux, ru_maxrss garde celui du parent d'avant exec (pytest, avec
    son OCR chargé) : on lit VmHWM, propre à ce programme. Sur le Mac, ru_maxrss est en octets."""
    statut = Path("/proc/self/status")
    if statut.exists():
        for ligne in statut.read_text().splitlines():
            if ligne.startswith("VmHWM:"):
                return int(ligne.split()[1]) / 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def main(racine: Path) -> dict[str, float]:
    from modules.trieur import config, daemon, traitement
    from tests.trieur.outils import FACTURE, FauxSysteme, pdf

    reglages = config.pour_le_bac_a_sable(racine)
    o = traitement.outils(reglages, systeme_=FauxSysteme(), moteur=None, ia=None)
    d = daemon.Demon(reglages, outils=o)
    d.demarrer()
    dl = config.chemin(reglages, "telechargements")
    dl.mkdir(parents=True, exist_ok=True)
    for i in range(400):  # un dossier Téléchargements bien rempli (fichiers d'avant l'installation)
        (dl / f"vieux-{i}.pdf").write_bytes(b"%PDF-1.4 vieux")
    import os

    for f in dl.iterdir():
        os.utime(f, (time.time() - 86400, time.time() - 86400))
    for _ in range(3):
        d.tour()
    debut = time.process_time()
    tours = 50
    for _ in range(tours):
        d.tour()
    cpu_par_tour = (time.process_time() - debut) / tours
    repos_mo = memoire_max_mo()
    pdf(config.chemin(reglages, "a_trier") / "facture.pdf", FACTURE)
    for _ in range(4):
        d.tour()
        time.sleep(1.05)
    rangés = o.base.compter().get("classe", 0)
    pic_mo = memoire_max_mo()
    d.arreter()
    return {"cpu_par_tour_s": cpu_par_tour, "cpu_pct": 100 * cpu_par_tour / daemon.PAS_S, "repos_mo": repos_mo,
            "pic_mo": pic_mo, "ranges": rangés}  # fmt: skip


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]))))
