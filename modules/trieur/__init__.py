"""Le Trieur : ce que tu envoies depuis l'iPhone ou donnes au Mac est reconnu, renommé, rangé ; une facture d'un
bien durable crée sa garantie et ses rappels."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def ajouter(chemin: str | Path, source: str = "api", note: str | None = None,
            reglages: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """Donne un fichier au Trieur (D-11) : voir modules/trieur/api.py."""
    from modules.trieur.api import ajouter as _ajouter

    return _ajouter(chemin, source, note, reglages)
