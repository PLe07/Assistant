"""La surveillance en fond (complétée en P8)."""

from __future__ import annotations

from typing import Any


def boucle(ctx: Any) -> None:
    while not ctx.attendre(60):
        pass
