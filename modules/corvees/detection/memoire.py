"""La mémoire de tes décisions : une corvée refusée ne revient jamais (sauf si elle devient 3 fois plus fréquente),
une corvée reportée revient après le délai choisi, une corvée acceptée n'est plus proposée.

Une décision reconnaît sa corvée par ses étapes clés (fichiers, commandes, copier-coller, sites), pas seulement par
sa signature : la même corvée décrite un peu autrement par une analyse suivante reste reconnue.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from modules.corvees.detection.scoring import sorte


def cles(tokens: list[str] | tuple[str, ...]) -> set[str]:
    """Les étapes qui caractérisent une corvée : tout sauf les changements d'appli (s'il reste quelque chose)."""
    fortes = {t for t in tokens if sorte(t) != "app"}
    return fortes or set(tokens)


def correspond(candidat: dict[str, Any], decision: dict[str, Any], signature: str) -> bool:
    if candidat["signature"] == signature:
        return True
    a, b = cles(candidat["tokens"]), cles(decision.get("tokens") or [])
    if not a or not b:
        return False
    commun = len(a & b)
    return commun > 0 and commun >= 0.5 * min(len(a), len(b))


def frequence(compte: dict[str, int], jours_observes: int, tokens: list[str] | tuple[str, ...]) -> float:
    """Combien de fois par mois reviennent les étapes clés d'une corvée (la plus rare des étapes clés). La même
    mesure sert au moment du refus et ensuite : on compare ce qui est comparable, quelle que soit la forme sous
    laquelle la corvée a été proposée."""
    les_cles = cles(tokens)
    if not les_cles:
        return 0.0
    return min(compte.get(t, 0) for t in les_cles) / max(jours_observes, 7) * 30


def filtrer(
    candidats: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
    maintenant: float,
    frequence_actuelle: Callable[[list[str]], float] | None = None,
) -> list[dict[str, Any]]:
    gardes = []
    for c in candidats:
        decision = next(((s, d) for s, d in decisions.items() if correspond(c, d, s)), None)
        if decision is None:
            gardes.append(c)
            continue
        _, d = decision
        if d["statut"] == "reject":
            actuelle = frequence_actuelle(d.get("tokens") or c["tokens"]) if frequence_actuelle else c["frequence_mois"]
            if actuelle >= 3 * max(float(d.get("frequence_ref") or 0), 0.1):
                gardes.append(dict(c, revenue="Tu l'avais refusée, mais elle est devenue 3 fois plus fréquente."))
        elif d["statut"] == "snooze":
            if maintenant >= float(d.get("jusqua") or 0):
                gardes.append(c)
        # « accept » : déjà prise en main, on ne la repropose pas
    return gardes
