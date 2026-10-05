"""D4 — Ponts copier-coller : copier dans l'appli A puis aller dans l'appli B, au moins 5 fois sur au moins 3 jours,
et plus souvent que ne le voudrait le hasard.

Le hasard : A et B sont peut-être simplement deux applis très utilisées. On calcule la probabilité de voir autant de
copies A → B par hasard (loi de Poisson), corrigée du nombre de paires d'applis examinées (Bonferroni) : seul ce qui
reste improbable est retenu.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from modules.corvees.detection.flux import Candidat, Flux
from modules.corvees.normalize import jour_de


def _bouts(token: str) -> tuple[str, str]:
    source, _, destination = token.split(":", 1)[1].partition("→")
    return source, destination


def queue_poisson(observe: int, attendu: float) -> float:
    """P(X ≥ observe) pour X qui suit une loi de Poisson de moyenne « attendu »."""
    if observe <= 0:
        return 1.0
    terme = math.exp(-attendu)
    cumul = terme
    for k in range(1, observe):
        terme *= attendu / k
        cumul += terme
    return max(0.0, 1.0 - cumul)


def detecter(flux: Flux, reglages: dict[str, Any]) -> list[Candidat]:
    p = reglages["detection"]["ponts"]
    instants: dict[str, list[float]] = defaultdict(list)
    for e in flux.evenements:
        if e.kind == "clip" and "→" in e.token:
            instants[e.token].append(e.ts)
    total = sum(len(v) for v in instants.values())
    sources: Counter[str] = Counter()
    destinations: Counter[str] = Counter()
    for token, ts in instants.items():
        a, b = _bouts(token)
        sources[a] += len(ts)
        destinations[b] += len(ts)
    candidats = []
    for token, ts in instants.items():
        jours = {jour_de(t) for t in ts}
        if len(ts) < p["occurrences_min"] or len(jours) < p["jours_min"]:
            continue
        a, b = _bouts(token)
        attendu = total * (sources[a] / total) * (destinations[b] / total)
        lift = len(ts) / max(attendu, 1e-9)
        if queue_poisson(len(ts), attendu) * len(instants) > p["alpha"]:
            continue
        candidats.append(Candidat("pont", (token,), len(ts), len(jours), ts, [0.0] * len(ts), lift=lift))
    return candidats
