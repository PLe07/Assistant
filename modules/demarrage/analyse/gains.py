"""Ce que tu gagnerais en coupant les éléments 💤 et 👻 : mémoire libérée, secondes de processeur à chaque ouverture
de session, et mises en veille débloquées."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Gains:
    memoire_mo: float = 0.0
    cpu_session_s: float = 0.0
    veilles: int = 0  # éléments qui empêchent la veille
    elements: list[str] = field(default_factory=list)  # identifiants concernés


def calculer(elements: list[Any]) -> Gains:
    """elements : les Element de l'analyse (verdict, métriques, drapeaux)."""
    g = Gains()
    for e in elements:
        if e.verdict.code not in ("inutile", "orphelin"):
            continue
        g.elements.append(e.fiche.id)
        g.memoire_mo += e.metriques.memoire_mo or 0.0
        g.cpu_session_s += e.metriques.cpu_session_s or 0.0
        if "empêche la veille" in e.drapeaux:
            g.veilles += 1
    g.memoire_mo, g.cpu_session_s = round(g.memoire_mo, 1), round(g.cpu_session_s, 1)
    return g
