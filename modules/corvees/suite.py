"""Ce qui suit l'analyse du soir : descriptions (Claude, ou faites sur place), propositions, rapport, notification.

Tout se passe dans un fil à part : l'appel à Claude peut prendre quelques minutes, et pendant ce temps les capteurs
continuent. Une erreur ici est notée dans le journal, sans jamais faire tomber le démon.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from modules.corvees import ia, notifier, propositions, rapport

_fil: threading.Thread | None = None


def traiter(
    reglages: dict[str, Any],
    candidats: list[dict[str, Any]],
    maintenant: float,
    journal: Callable[[str], None],
    demander: Callable[..., Any] | None = None,
    dormir: Callable[[float], None] = time.sleep,
    prevenir: bool = True,
    afficher: Callable[[str, str], bool] | None = None,
) -> dict[str, dict[str, Any]]:
    """Décrit les corvées, écrit leurs propositions et le rapport, puis prépare la notification (prevenir=False :
    pas de notification, par exemple quand tu lances l'analyse toi-même). Renvoie signature → description."""
    from modules.corvees.daemon import ouvrir

    base = ouvrir(reglages)  # sa propre connexion : on est dans un autre fil que le démon
    try:
        descriptions = ia.decrire(
            base, candidats, reglages, maintenant, demander=demander, dormir=dormir, journal=journal
        )
        if not base.toujours_la():  # tu as tout effacé pendant l'appel à Claude : on n'écrit plus rien
            journal("Suite de l'analyse abandonnée : tes données ont été effacées entre-temps (purge)")
            return {}
        for c in candidats:
            d = descriptions.get(c["signature"])
            if d is not None:
                propositions.ecrire(reglages, c, d)
        rapport.ecrire(base, reglages, maintenant)
        if prevenir:
            notifier.preparer(base, candidats, descriptions, maintenant)
            notifier.tenter(base, reglages, maintenant, afficher=afficher, journal=journal)
        return descriptions
    finally:
        base.fermer()


def _travailler(reglages: dict[str, Any], candidats: list[dict[str, Any]], maintenant: float, journal: Any) -> None:
    try:
        traiter(reglages, candidats, maintenant, journal)
    except Exception as e:
        journal(f"Suite de l'analyse : {e.__class__.__name__} : {e}")


def apres_analyse(demon: Any, candidats: list[dict[str, Any]], maintenant: float) -> None:
    """Appelé par le démon après chaque analyse : lance la suite dans un fil (un seul à la fois)."""
    global _fil
    if _fil is not None and _fil.is_alive():
        demon.journal("Suite de l'analyse précédente encore en cours : celle-ci attendra demain")
        return
    _fil = threading.Thread(
        target=_travailler,
        args=(demon.reglages, candidats, maintenant, demon.journal),
        name="corvees-suite",
        daemon=True,
    )
    _fil.start()


def attendre(delai: float | None = None) -> None:
    """Attend la fin de la suite en cours (pour la commande « analyser --maintenant » et les essais)."""
    if _fil is not None:
        _fil.join(delai)
