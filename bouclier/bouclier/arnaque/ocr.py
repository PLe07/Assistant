"""Quel lecteur de capture d'écran utiliser : Apple Vision sur le Mac, rien ailleurs (mode dégradé expliqué)."""

from __future__ import annotations

import platform
from collections.abc import Callable
from pathlib import Path

LecteurImage = Callable[[Path], tuple[str, float]]


def lecteur(mac: bool | None = None) -> LecteurImage | None:
    """Le lecteur Vision s'il est utilisable ici, sinon None (une image donne alors un message clair)."""
    if not (platform.system() == "Darwin" if mac is None else mac):
        return None
    try:
        import Vision  # noqa: F401
    except ImportError:
        return None
    from bouclier.arnaque import ocr_vision

    return ocr_vision.lire


def etat(mac: bool | None = None) -> tuple[str, str]:
    """Pour doctor : (état, explication)."""
    if lecteur(mac) is not None:
        return "ok", "lecture des captures d'écran par Apple Vision, sur le Mac"
    return "absent", "lecture des captures d'écran indisponible (Apple Vision introuvable) : relance ./install.sh"
