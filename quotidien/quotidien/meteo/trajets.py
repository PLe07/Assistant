"""Tes trajets du jour (§3) : à vélo les jours de cours, un conseil général les autres jours.

Jours de cours (mercredi, jeudi, vendredi par défaut) : l'aller part à 8 h 00, le retour à 18 h 30, chacun dure
`duree_minutes` (30 min par défaut). Les autres jours : une seule fenêtre « journée », de 9 h à 19 h, sans vélo
(le parapluie redevient permis).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from quotidien.config import JOURS, en_minutes

JOURNEE_DEBUT = time(9, 0)
JOURNEE_FIN = time(19, 0)


@dataclass(frozen=True)
class Trajet:
    nom: str  # « aller », « retour » ou « journée »
    debut: datetime
    fin: datetime
    velo: bool

    def libelle_heure(self) -> str:
        return heure_lisible(self.debut)


def heure_lisible(instant: datetime) -> str:
    """8 h 00 → « 8h », 18 h 30 → « 18h30 »."""
    return f"{instant.hour}h" if instant.minute == 0 else f"{instant.hour}h{instant.minute:02d}"


def _a(jour: date, hhmm: str, zone: ZoneInfo) -> datetime:
    m = en_minutes(hhmm)
    return datetime.combine(jour, time(m // 60, m % 60), tzinfo=zone)


def est_jour_de_cours(jour: date, profil: dict[str, Any]) -> bool:
    return JOURS[jour.weekday()] in profil["semaine"]["jours_de_cours"]


def trajets_du_jour(jour: date, profil: dict[str, Any], fuseau: str = "Europe/Paris") -> list[Trajet]:
    zone = ZoneInfo(fuseau)
    t = profil["trajets"]
    if not est_jour_de_cours(jour, profil):
        return [
            Trajet(
                "journée", datetime.combine(jour, JOURNEE_DEBUT, zone), datetime.combine(jour, JOURNEE_FIN, zone), False
            )
        ]
    duree = timedelta(minutes=int(t["duree_minutes"]))
    velo = t["moyen"] == "velo"
    aller = _a(jour, t["depart"], zone)
    retour = _a(jour, t["retour"], zone)
    return [Trajet("aller", aller, aller + duree, velo), Trajet("retour", retour, retour + duree, velo)]
