"""Processeur, mémoire et temps de fonctionnement d'un module et de ses fils, avec psutil (lecture seule).

Le processeur se mesure par **différence** de temps processeur entre deux tours (aucune attente active, aucun
échantillonnage bloquant) : « 12 % » veut dire 12 % d'un cœur en moyenne depuis la mesure précédente. On ne lit que
les processus qui nous intéressent (le module, ses fils, les fils du superviseur de l'assistant) : jamais la liste
complète des processus du Mac à chaque tour.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import psutil

from tableau.module import StatsProcessus

Cle = tuple[int, float]  # (pid, instant de création) : un pid réutilisé n'est pas le même processus


@dataclass
class _Echantillon:
    cpu_s: float
    instant: float


def _arbre(pid: int) -> list[psutil.Process]:
    try:
        p = psutil.Process(pid)
        return [p, *p.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return []


class SondeProcessus:
    def __init__(self, horloge: Callable[[], float] = time.monotonic) -> None:
        self.horloge = horloge
        self._precedents: dict[str, dict[Cle, _Echantillon]] = {}

    def mesurer(self, nom: str, pids: Iterable[int]) -> StatsProcessus | None:
        """Le module `nom` (ses processus `pids` et tous leurs fils). None si aucun n'existe."""
        maintenant = self.horloge()
        vus: dict[Cle, _Echantillon] = {}
        rss = 0
        debut: float | None = None
        tous: list[int] = []
        for pid in pids:
            for p in _arbre(pid):
                try:
                    with p.oneshot():
                        cle = (p.pid, p.create_time())
                        if cle in vus:
                            continue
                        t = p.cpu_times()
                        vus[cle] = _Echantillon(t.user + t.system, maintenant)
                        rss += p.memory_info().rss
                        debut = cle[1] if debut is None else min(debut, cle[1])
                        tous.append(p.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        if not vus:
            self._precedents.pop(nom, None)
            return None
        avant = self._precedents.get(nom, {})
        self._precedents[nom] = vus
        cpu_pct: float | None = None
        if avant:
            instants = [e.instant for e in avant.values()]
            duree = maintenant - max(instants)
            if duree > 0.5:
                consomme = 0.0
                for cle, ech in vus.items():
                    precedent = avant.get(cle)
                    # Un fils né depuis la mesure précédente : tout son temps processeur est de cette période.
                    consomme += ech.cpu_s - (precedent.cpu_s if precedent else 0.0)
                cpu_pct = max(0.0, consomme / duree * 100)
        depuis = max(0.0, time.time() - debut) if debut is not None else None
        return StatsProcessus(pids=sorted(tous), cpu_pct=cpu_pct, rss_mo=rss / (1024 * 1024), depuis_s=depuis)

    def oublier(self, nom: str) -> None:
        self._precedents.pop(nom, None)


def fils_du_superviseur(pid_superviseur: int) -> dict[str, list[int]]:
    """Les modules lancés par le superviseur de l'assistant (`python -m modules.<nom>`) : nom → pids.

    Seuls les fils directs du superviseur sont lus (pas tout le Mac)."""
    resultat: dict[str, list[int]] = {}
    try:
        fils = psutil.Process(pid_superviseur).children(recursive=False)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return resultat
    for p in fils:
        try:
            ligne = p.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        for i, morceau in enumerate(ligne[:-1]):
            if morceau == "-m" and ligne[i + 1].startswith("modules."):
                nom = ligne[i + 1].split(".")[1]
                resultat.setdefault(nom, []).append(p.pid)
                break
    return resultat


def charge_du_mac() -> dict[str, float]:
    """Le processeur de tout le Mac (en % d'un cœur, comme les modules) et sa mémoire."""
    coeurs = psutil.cpu_count() or 1
    memoire = psutil.virtual_memory()
    return {
        "cpu_pct": psutil.cpu_percent(interval=None) * coeurs,
        "coeurs": float(coeurs),
        "memoire_totale_mo": memoire.total / (1024 * 1024),
        "memoire_utilisee_mo": (memoire.total - memoire.available) / (1024 * 1024),
    }


def moi() -> dict[str, float]:
    """Le tableau de bord lui-même (pour `tableau doctor` et la mesure de performance)."""
    p = psutil.Process(os.getpid())
    with p.oneshot():
        t = p.cpu_times()
        return {"cpu_s": t.user + t.system, "rss_mo": p.memory_info().rss / (1024 * 1024), "debut": p.create_time()}
