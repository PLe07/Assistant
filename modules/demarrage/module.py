"""L'interface du Nettoyeur pour l'Assistant (§8 « module.py ») : la boucle lancée par le superviseur, et l'état
pour « python assistant.py etat » et « demarrage doctor »."""

from __future__ import annotations

from typing import Any

from modules.demarrage import config, daemon, travail


def boucle(ctx: Any) -> None:
    daemon.boucle(ctx)


def status(maintenant: float) -> dict[str, Any]:
    reglages, _ = config.charger()
    base = travail.ouvrir_base(reglages)
    try:
        return {"actif": reglages["actif"], **daemon.status(base, maintenant)}
    finally:
        base.fermer()
