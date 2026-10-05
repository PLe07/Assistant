"""L'impact énergétique : `top -l 2 -s 1 -stats pid,command,cpu,mem,power -o power -n 25`.

Le premier relevé de top n'a pas de valeurs de processeur fiables : on lit le dernier. La commande est tronquée
et peut contenir des espaces : on lit chaque ligne par la droite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMANDE = ["top", "-l", "2", "-s", "1", "-stats", "pid,command,cpu,mem,power", "-o", "power", "-n", "25"]
_ENTETE = re.compile(r"^\s*PID\s+COMMAND\s+%CPU\s+MEM\s+POWER\s*$")
_MEMOIRE = re.compile(r"^([\d.]+)([BKMGT])?[+-]?$")
_FACTEURS = {"B": 1 / 1024, "K": 1, "M": 1024, "G": 1024**2, "T": 1024**3, None: 1 / 1024}


@dataclass
class Energie:
    pid: int
    commande: str
    cpu: float
    memoire_ko: int
    puissance: float


def _memoire(texte: str) -> int | None:
    m = _MEMOIRE.match(texte)
    if not m:
        return None
    return int(float(m.group(1)) * _FACTEURS[m.group(2)])


def analyser(texte: str) -> dict[int, Energie]:
    lignes = texte.splitlines()
    debuts = [i for i, ligne in enumerate(lignes) if _ENTETE.match(ligne)]
    if not debuts:
        return {}
    resultats: dict[int, Energie] = {}
    for ligne in lignes[debuts[-1] + 1 :]:
        mots = ligne.split()
        if len(mots) < 5 or not mots[0].isdigit():
            continue
        try:
            cpu, puissance = float(mots[-3]), float(mots[-1])
        except ValueError:
            continue
        memoire = _memoire(mots[-2])
        if memoire is None:
            continue
        pid = int(mots[0])
        resultats[pid] = Energie(pid, " ".join(mots[1:-3]), cpu, memoire, puissance)
    return resultats
