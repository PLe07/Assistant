"""Du jeu d'indices au score (0–100) et au niveau, avec les planchers des indices critiques (§3.3).

- Les indices tirés du texte ne font qu'ajouter des points ; seuls les faits techniques vérifiés en retirent.
- Un indice critique tient le verdict à 🟠 au moins ; deux indices critiques différents donnent 🔴.
"""

from __future__ import annotations

from bouclier.arnaque.signaux import SEUIL_ARNAQUE, SEUIL_PRUDENCE, SEUIL_TRES_SUSPECT, Niveau, Signal, niveau_du_score

BORNES: dict[Niveau, tuple[int, int]] = {
    Niveau.AUCUN_SIGNE: (0, SEUIL_PRUDENCE - 1),
    Niveau.PRUDENCE: (SEUIL_PRUDENCE, SEUIL_TRES_SUSPECT - 1),
    Niveau.TRES_SUSPECT: (SEUIL_TRES_SUSPECT, SEUIL_ARNAQUE - 1),
    Niveau.ARNAQUE: (SEUIL_ARNAQUE, 100),
}


def score_brut(signaux: list[Signal]) -> int:
    positif = min(100, sum(s.poids for s in signaux if s.poids > 0))
    negatif = sum(s.poids for s in signaux if s.poids < 0 and s.technique)
    return max(0, min(100, positif + negatif))


def ramener(score: int, niveau: Niveau) -> int:
    """Le score ramené dans la plage de son niveau (après un plancher ou l'avis de l'IA)."""
    bas, haut = BORNES[niveau]
    return max(bas, min(haut, score))


def evaluer(signaux: list[Signal]) -> tuple[int, Niveau]:
    score = score_brut(signaux)
    niveau = niveau_du_score(score)
    critiques = {s.code for s in signaux if s.critique}
    if len(critiques) >= 2:
        niveau = Niveau.ARNAQUE
    elif critiques and niveau.value < Niveau.TRES_SUSPECT.value:
        niveau = Niveau.TRES_SUSPECT
    return ramener(score, niveau), niveau
