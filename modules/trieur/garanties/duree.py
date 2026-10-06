"""La durée d'une garantie (§7) et le rappel de rétractation.

- La note envoyée avec le document l'emporte (« garantie 3 ans ») : c'est toi qui sais.
- Sinon, la plus longue entre la mention du document et la garantie légale de conformité : 24 mois pour un bien
  neuf, 12 mois pour un bien d'occasion acheté à un professionnel. La garantie légale s'applique toujours : une
  « garantie constructeur 12 mois » ne la raccourcit pas (D-13).
- Elle court à partir de la date du document (la date d'achat, sinon de facture).
- Achat en ligne : rappel 11 jours après la livraison (sinon après la commande), 3 jours avant la fin des 14 jours.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class Duree:
    mois: int
    source: str  # « note », « facture », « légale »


def ajouter_mois(d: date, mois: int) -> date:
    """Le même jour, n mois plus tard ; le 29 février d'une année non bissextile devient le 28."""
    total = d.month - 1 + mois
    annee, m = d.year + total // 12, total % 12 + 1
    return date(annee, m, min(d.day, calendar.monthrange(annee, m)[1]))


def duree(note_mois: int | None, mention_mois: int | None, occasion: bool, reglages: dict[str, Any]) -> Duree:
    g = reglages["garanties"]
    legale = int(g["legale_occasion_mois"] if occasion else g["legale_neuf_mois"])
    if note_mois:
        return Duree(note_mois, "note")
    if mention_mois and mention_mois > legale:
        return Duree(mention_mois, "facture")
    return Duree(legale, "légale")


def rappel_retractation(livraison: date | None, commande: date | None, reglages: dict[str, Any]) -> date | None:
    g = reglages["garanties"]
    if not g.get("retractation", True):
        return None
    depart = livraison or commande
    return depart + timedelta(days=int(g["retractation_rappel_jours"])) if depart else None
