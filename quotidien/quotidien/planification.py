"""Quand faire quoi (§7) : les tâches datées du démon, chacune faite une seule fois par échéance.

| tâche          | quand (réglable)          | encore utile jusqu'à            |
|----------------|---------------------------|---------------------------------|
| brief          | chaque jour 7 h 15        | 11 h (pas de brief du matin à 15 h) |
| alerte_meteo   | chaque jour 21 h          | début du silence (23 h)          |
| rappels_veille | chaque jour 20 h          | début du silence (23 h)          |
| menu           | dimanche 17 h             | lundi 20 h                       |

Un Mac qui dormait à l'heure prévue rattrape la tâche au réveil, une seule fois, et seulement si elle sert encore.
Ce qui est fait est noté en base (table `taches`) : un redémarrage ne refait rien. Les heures sont celles du fuseau
des réglages (changement d'heure compris). Une heure réglée dans le silence (23 h – 7 h) est repoussée à sa fin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from quotidien import config
from quotidien.db import Base as BaseDonnees

FIN_BRIEF = "11:00"
FIN_MENU = "20:00"  # le lendemain (lundi)


@dataclass(frozen=True)
class Echeance:
    tache: str
    cle: str  # « 2026-10-07 » : le jour concerné
    quand: float
    fin: float


def _moment(jour: date, heure: str, fuseau: str) -> float:
    h, m = (int(x) for x in heure.split(":"))
    return datetime(jour.year, jour.month, jour.day, h, m, tzinfo=ZoneInfo(fuseau)).timestamp()


def _hors_silence(heure: str, horaires: dict[str, str]) -> str:
    debut, fin = horaires["silence_debut"], horaires["silence_fin"]
    dans = heure >= debut or heure < fin if debut > fin else debut <= heure < fin
    return fin if dans else heure


def echeances_du_jour(jour: date, reglages: dict[str, Any]) -> list[Echeance]:
    h, fuseau = reglages["horaires"], reglages["lieu"]["fuseau"]
    cle = jour.isoformat()
    silence = _moment(jour, h["silence_debut"], fuseau) if h["silence_debut"] > h["silence_fin"] else (
        _moment(jour + timedelta(days=1), h["silence_debut"], fuseau))  # fmt: skip
    resultat = [
        Echeance("brief", cle, _moment(jour, _hors_silence(h["brief"], h), fuseau),
                 max(_moment(jour, FIN_BRIEF, fuseau), _moment(jour, _hors_silence(h["brief"], h), fuseau) + 3600)),
        Echeance("rappels_veille", cle, _moment(jour, _hors_silence(h["rappels_veille"], h), fuseau), silence),
        Echeance("alerte_meteo", cle, _moment(jour, _hors_silence(h["alerte_meteo_veille"], h), fuseau), silence),
    ]  # fmt: skip
    if jour.weekday() == config.JOURS.index(h["menu_jour"]):
        resultat.append(Echeance("menu", cle, _moment(jour, _hors_silence(h["menu_heure"], h), fuseau),
                                 _moment(jour + timedelta(days=1), FIN_MENU, fuseau)))  # fmt: skip
    return [e for e in resultat if e.fin > e.quand]


def aujourdhui(maintenant: float, reglages: dict[str, Any]) -> date:
    return datetime.fromtimestamp(maintenant, ZoneInfo(reglages["lieu"]["fuseau"])).date()


def fait(db: BaseDonnees, e: Echeance) -> bool:
    return db.cx.execute("SELECT 1 FROM taches WHERE nom = ? AND echeance = ?", (e.tache, e.cle)).fetchone() is not None


def dues(db: BaseDonnees, reglages: dict[str, Any], maintenant: float) -> list[Echeance]:
    """Les tâches à faire maintenant : leur heure est passée, elles servent encore, elles ne sont pas faites."""
    jour = aujourdhui(maintenant, reglages)
    candidates = echeances_du_jour(jour - timedelta(days=1), reglages) + echeances_du_jour(jour, reglages)
    return [e for e in candidates if e.quand <= maintenant < e.fin and not fait(db, e)]


def noter(db: BaseDonnees, e: Echeance, maintenant: float, resultat: str = "") -> None:
    with db.transaction() as cx:
        cx.execute("INSERT OR REPLACE INTO taches(nom, echeance, faite_le, resultat) VALUES (?, ?, ?, ?)",
                   (e.tache, e.cle, maintenant, resultat[:300]))  # fmt: skip
        cx.execute("DELETE FROM taches WHERE faite_le < ?", (maintenant - 90 * 86400,))


def prochaines(db: BaseDonnees, reglages: dict[str, Any], maintenant: float) -> dict[str, float]:
    """La prochaine exécution de chaque tâche (pour `quotidien doctor`)."""
    jour = aujourdhui(maintenant, reglages)
    resultat: dict[str, float] = {}
    for n in range(0, 9):
        for e in echeances_du_jour(jour + timedelta(days=n), reglages):
            if e.tache in resultat or fait(db, e) or e.fin <= maintenant:
                continue
            resultat[e.tache] = max(e.quand, maintenant)
    return resultat


def derniere(db: BaseDonnees, tache: str) -> tuple[str, float, str] | None:
    ligne = db.cx.execute("SELECT echeance, faite_le, resultat FROM taches WHERE nom = ? ORDER BY faite_le DESC "
                          "LIMIT 1", (tache,)).fetchone()  # fmt: skip
    return (str(ligne[0]), float(ligne[1]), str(ligne[2])) if ligne else None
