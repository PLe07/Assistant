"""L'interface du Trieur pour l'Assistant : la boucle lancée par le superviseur, et l'état pour l'Assistant."""

from __future__ import annotations

from typing import Any

from modules.trieur import daemon


def boucle(ctx: Any) -> None:
    daemon.boucle(ctx)
