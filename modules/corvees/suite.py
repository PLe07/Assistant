"""Ce qui suit l'analyse du soir : descriptions (Claude, ou locales), propositions, rapport, notification.
Complété aux phases 6 et 7."""

from __future__ import annotations

from typing import Any


def apres_analyse(demon: Any, candidats: list[dict[str, Any]], maintenant: float) -> None:
    """Appelé par le démon après chaque analyse. Ne lève jamais : le démon s'en protège quand même."""
