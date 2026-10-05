"""Rattacher chaque processus à l'élément qui l'a lancé, dans cet ordre :
1. le PID que launchd donne pour le label de l'élément ;
2. le chemin de l'exécutable (le programme de la fiche) ;
3. le bundle de l'app parente, pour un processus lancé directement par launchd ;
4. le parent : un processus fils compte pour l'élément de son parent (récursivement).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from modules.demarrage.collecteurs.plists import app_contenant
from modules.demarrage.modele import Fiche

PROFONDEUR_MAX = 64


@dataclass
class Proc:
    pid: int
    ppid: int
    uid: int
    cpu_pct: float
    rss_ko: int
    age_s: float  # depuis son lancement (etime)
    cpu_s: float  # temps processeur cumulé (time)
    comm: str


def _priorite(f: Fiche) -> int:
    """Quand plusieurs fiches partagent une app : l'app d'ouverture d'abord, puis les agents, Apple en dernier."""
    return (0 if f.source in ("ouverture", "ouverture_app") else 1) + (10 if f.est_apple else 0)


def rattacher(procs: Iterable[Proc], fiches: list[Fiche], pids_launchd: dict[str, int]) -> dict[int, str]:
    """PID → identifiant de fiche, pour chaque processus qu'on sait rattacher."""
    liste = list(procs)
    par_pid = {p.pid: p for p in liste}
    resultat: dict[int, str] = {}
    par_label: dict[str, Fiche] = {}
    par_programme: dict[str, Fiche] = {}
    par_app: dict[str, Fiche] = {}
    for f in sorted(fiches, key=_priorite):
        par_label.setdefault(f.label, f)
        if f.programme:
            par_programme.setdefault(f.programme, f)
        if f.app_parente:
            par_app.setdefault(f.app_parente, f)
    for label, pid in pids_launchd.items():
        trouvee = par_label.get(label)
        if trouvee and pid in par_pid:
            resultat[pid] = trouvee.id
    for p in liste:
        if p.pid in resultat:
            continue
        cible = par_programme.get(p.comm)
        if cible is None and p.ppid == 1:
            app = app_contenant(p.comm)
            cible = par_app.get(app) if app else None
        if cible is not None:
            resultat[p.pid] = cible.id
    for p in liste:
        if p.pid in resultat:
            continue
        courant, vus = p.ppid, 0
        while courant > 1 and vus < PROFONDEUR_MAX:
            if courant in resultat:
                resultat[p.pid] = resultat[courant]
                break
            parent = par_pid.get(courant)
            if parent is None:
                break
            courant, vus = parent.ppid, vus + 1
    return resultat
