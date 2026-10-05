"""Qui empêche la veille : `pmset -g assertions`, section « Listed by owning process »."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Les assertions qui empêchent le Mac de se mettre en veille (l'écran seul ne compte pas).
EMPECHENT_LA_VEILLE = {"PreventUserIdleSystemSleep", "PreventSystemSleep", "NoIdleSleepAssertion"}

_ASSERTION = re.compile(r"^\s*pid (\d+)\((.*?)\):\s*\[[^\]]*\]\s*(?:[\d:]+\s+)?(\w+)\s+named:\s*\"(.*)\"\s*$")
_POUR = re.compile(r"\(pid (\d+)\)\s*$")


@dataclass
class Assertion:
    pid: int
    processus: str
    type: str
    nom: str
    au_nom_de: int | None = None  # « on behalf of … (pid N) » : le vrai demandeur

    @property
    def empeche_la_veille(self) -> bool:
        return self.type in EMPECHENT_LA_VEILLE


def analyser(texte: str) -> list[Assertion]:
    assertions: list[Assertion] = []
    dans_la_liste = False
    for ligne in texte.splitlines():
        if ligne.startswith("Listed by owning process"):
            dans_la_liste = True
            continue
        if dans_la_liste and ligne and not ligne[0].isspace():
            break  # « Kernel Assertions », « Idle sleep preventers »…
        if not dans_la_liste:
            continue
        m = _ASSERTION.match(ligne)
        if m:
            assertions.append(Assertion(int(m.group(1)), m.group(2), m.group(3), m.group(4)))
            continue
        m = _POUR.search(ligne)
        if m and assertions and "Details:" in ligne and "behalf" in ligne:
            assertions[-1].au_nom_de = int(m.group(1))
    return assertions


def pids_qui_empechent(assertions: list[Assertion]) -> set[int]:
    """Les PID responsables (le demandeur et, s'il agit pour un autre, cet autre aussi)."""
    pids: set[int] = set()
    for a in assertions:
        if a.empeche_la_veille:
            pids.add(a.pid)
            if a.au_nom_de:
                pids.add(a.au_nom_de)
    return pids
