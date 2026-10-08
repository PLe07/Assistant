"""Un adaptateur par module connu ; tout module inconnu reçoit l'adaptateur générique."""

from __future__ import annotations

from tableau.adaptateurs.ambiance import Ambiance
from tableau.adaptateurs.assistant import Assistant
from tableau.adaptateurs.base import Adaptateur
from tableau.adaptateurs.bouclier import Bouclier
from tableau.adaptateurs.corvees import Corvees
from tableau.adaptateurs.generique import Generique
from tableau.adaptateurs.n8n import N8n
from tableau.adaptateurs.nettoyeur import Nettoyeur
from tableau.adaptateurs.quotidien import Quotidien
from tableau.adaptateurs.trieur import Trieur

ADAPTATEURS: dict[str, type[Adaptateur]] = {
    "generique": Generique,
    "assistant": Assistant,
    "corvees": Corvees,
    "nettoyeur": Nettoyeur,
    "trieur": Trieur,
    "bouclier": Bouclier,
    "quotidien": Quotidien,
    "ambiance": Ambiance,
    "tolerant": Ambiance,  # pour un futur module : battement, coûts et preuves lus s'ils existent
    "n8n": N8n,
}


def obtenir(nom: str) -> Adaptateur:
    return ADAPTATEURS.get(nom, Generique)()
