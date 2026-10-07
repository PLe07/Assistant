"""La place prise par les données et les journaux d'un module, et sa croissance (§4.1).

Un simple parcours des dossiers avec `stat` (aucun fichier ouvert), borné à 200 000 entrées pour ne jamais peser
sur le Mac, fait au plus toutes les 30 minutes. Les liens symboliques ne sont pas suivis.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from tableau.db import Base

ENTREES_MAX = 200_000


def taille(chemins: Iterable[Path], exclure: Iterable[Path] = ()) -> int | None:
    """Octets occupés (None si aucun chemin n'existe)."""
    exclus = {str(p) for p in exclure}
    total = 0
    trouve = False
    vues = 0
    pile = []
    for c in chemins:
        try:
            st = os.stat(c, follow_symlinks=False)
        except OSError:
            continue
        trouve = True
        if os.path.isdir(c) and not os.path.islink(c):
            pile.append(str(c))
        else:
            total += st.st_size
    while pile and vues < ENTREES_MAX:
        dossier = pile.pop()
        if dossier in exclus:
            continue
        try:
            with os.scandir(dossier) as entrees:
                for e in entrees:
                    vues += 1
                    try:
                        if e.is_dir(follow_symlinks=False):
                            pile.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total if trouve else None


def noter(base: Base, module: str, ts: float, donnees: int | None, journaux: int | None) -> None:
    base.executer(
        "INSERT OR REPLACE INTO tailles (module, ts, donnees, logs) VALUES (?, ?, ?, ?)",
        (module, ts, donnees, journaux),
    )


def croissance_semaine(base: Base, module: str, maintenant: float) -> tuple[int | None, float | None]:
    """(taille actuelle données + journaux, croissance en % sur 7 jours) ; None si on ne sait pas encore."""
    recente = base.ligne(
        "SELECT ts, COALESCE(donnees, 0) + COALESCE(logs, 0) AS t FROM tailles WHERE module = ? ORDER BY ts DESC "
        "LIMIT 1",
        (module,),
    )
    if recente is None:
        return None, None
    ancienne = base.ligne(
        "SELECT ts, COALESCE(donnees, 0) + COALESCE(logs, 0) AS t FROM tailles WHERE module = ? AND ts <= ? "
        "ORDER BY ts DESC LIMIT 1",
        (module, maintenant - 7 * 86400),
    )
    if ancienne is None or ancienne["t"] <= 0:
        return int(recente["t"]), None
    return int(recente["t"]), (recente["t"] - ancienne["t"]) / ancienne["t"] * 100
