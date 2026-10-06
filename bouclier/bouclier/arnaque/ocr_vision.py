"""Lecture d'une capture d'écran par Apple Vision (pyobjc), en local, sur le Mac seulement.

Même façon de faire que le Trieur (éprouvée sur ce Mac) : un vrai dictionnaire macOS vide pour les options (un {} de
Python fait planter Vision avec PyObjC 12), précision maximale, français puis anglais. Vérifié par tests/e2e_mac.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _gestionnaire(image: Path) -> Any:
    import Vision
    from Foundation import NSURL, NSDictionary

    return Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(image)),
                                                                     NSDictionary.dictionary())  # fmt: skip


def lire(image: Path) -> tuple[str, float]:
    """(texte dans l'ordre de lecture, confiance moyenne de 0 à 1)."""
    import Vision as V

    requete = V.VNRecognizeTextRequest.alloc().init()
    requete.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate)
    requete.setUsesLanguageCorrection_(True)
    try:
        requete.setRecognitionLanguages_(["fr-FR", "en-US"])
    except Exception:  # noqa: BLE001 - une version de macOS sans ce réglage lit quand même
        pass
    ok, erreur = _gestionnaire(image).performRequests_error_([requete], None)
    if not ok:
        raise OSError(f"Vision : {erreur}")
    lignes: list[tuple[float, float, str, float]] = []
    for observation in requete.results() or []:
        candidats = observation.topCandidates_(1)
        if not candidats or not len(candidats):
            continue
        cadre = observation.boundingBox()  # origine en bas à gauche, de 0 à 1
        haut = 1.0 - (float(cadre.origin.y) + float(cadre.size.height))
        lignes.append(
            (round(haut, 2), float(cadre.origin.x), str(candidats[0].string()), float(candidats[0].confidence()))
        )
    lignes.sort(key=lambda ligne: (ligne[0], ligne[1]))
    if not lignes:
        return "", 0.0
    return "\n".join(ligne[2] for ligne in lignes), sum(ligne[3] for ligne in lignes) / len(lignes)
