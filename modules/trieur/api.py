"""L'API pour les autres modules de l'Assistant (D-11) : donner un fichier au Trieur, qui le traite tout de suite.

from modules.trieur import ajouter
resultat = ajouter("/chemin/facture.pdf", source="api", note="garantie 3 ans")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SOURCES = ("boite", "a_trier", "finder", "cli", "api", "telechargements", "courriel", "existant")


def ajouter(chemin: str | Path, source: str = "api", note: str | None = None,
            reglages: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """Met le fichier dans la file et le traite (avec ses pièces jointes s'il s'agit d'un courriel).
    Renvoie {"id", "etat", "type", "destination", "erreur"}."""
    from modules.trieur import config, traitement

    if source not in SOURCES:
        raise ValueError(f"source inconnue : {source} ({', '.join(SOURCES)})")
    fichier = Path(chemin).expanduser().resolve()
    if not fichier.is_file():
        raise FileNotFoundError(f"pas un fichier : {fichier}")
    if reglages is None:
        reglages, _ = config.charger()
    o = traitement.outils(reglages)
    try:
        element = o.base.ajouter(fichier, source, note)
        traitement.traiter(o, element)
        for enfant in list(o.ajoutes):
            traitement.traiter(o, enfant)
        el = o.base.element(element)
        assert el is not None
        return {"id": el.id, "etat": el.etat, "type": el.type, "destination": el.destination, "erreur": el.erreur,
                "pieces_jointes": list(o.ajoutes)}  # fmt: skip
    finally:
        o.base.fermer()
