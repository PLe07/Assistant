"""Ce que tes modules coûtent au Mac : processeur, mémoire, énergie (§4.4).

« Mon assistant me coûte-t-il de la batterie ? » : la réponse tient en une phrase. L'énergie est **estimée** à partir
du temps processeur (aucune mesure de puissance sans droits d'administrateur) : un cœur occupé à 100 % consomme
environ `watts_par_coeur` (2,5 W sur un MacBook Air récent), le Mac entier en usage léger `watts_mac_moyen` (4,5 W),
sur `heures_eveil_par_jour` (8 h) éveillé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tableau import textes
from tableau.config import Reglages
from tableau.db import Base
from tableau.module import EtatModule


@dataclass
class Bilan:
    cpu_pct: float  # en % d'un cœur, tous modules
    rss_mo: float
    part_cpu_mac: float | None  # part de la charge du Mac
    part_memoire_mac: float | None
    minutes_batterie_jour: float
    phrase: str
    par_module: list[dict[str, Any]] = field(default_factory=list)


def moyennes(base: Base, depuis: float) -> dict[str, tuple[float | None, float | None]]:
    """Processeur et mémoire moyens de chaque module depuis `depuis` (mesures brutes et agrégats horaires)."""
    resultat: dict[str, tuple[float | None, float | None]] = {}
    for r in base.lignes(
        "SELECT module, AVG(cpu) AS c, AVG(rss_mo) AS m FROM echantillons WHERE ts >= ? GROUP BY module", (depuis,)
    ):
        resultat[r["module"]] = (r["c"], r["m"])
    return resultat


def bilan(etats: list[EtatModule], mac: dict[str, float] | None, reglages: Reglages,
          moyennes_24h: dict[str, tuple[float | None, float | None]] | None = None) -> Bilan:  # fmt: skip
    e = reglages["energie"]
    par_module = []
    cpu = rss = 0.0
    for etat in etats:
        moy = (moyennes_24h or {}).get(etat.id, (None, None))
        c = moy[0] if moy[0] is not None else etat.cpu_pct
        m = moy[1] if moy[1] is not None else etat.rss_mo
        if c is None and m is None:
            continue
        cpu += c or 0.0
        rss += m or 0.0
        par_module.append({"id": etat.id, "nom": etat.nom, "emoji": etat.emoji, "cpu_pct": c, "rss_mo": m})
    par_module.sort(key=lambda x: -float(x["cpu_pct"] or 0))
    part_cpu = part_mem = None
    if mac:
        total_cpu = mac.get("cpu_pct") or 0.0
        part_cpu = min(100.0, cpu / total_cpu * 100) if total_cpu > 0 else None
        total_mem = mac.get("memoire_totale_mo") or 0.0
        part_mem = rss / total_mem * 100 if total_mem > 0 else None
    wh_jour = cpu / 100 * float(e["watts_par_coeur"]) * float(e["heures_eveil_par_jour"])
    minutes = wh_jour / float(e["watts_mac_moyen"]) * 60
    return Bilan(cpu, rss, part_cpu, part_mem, minutes, phrase(cpu, rss, minutes, par_module), par_module)


def phrase(cpu: float, rss: float, minutes: float, par_module: list[dict[str, Any]]) -> str:
    conso = (f"tes modules utilisent {textes.pourcent(cpu, 1)} d'un cœur et {textes.mo(rss)} de mémoire, soit environ "
             f"{_minutes(minutes)} d'autonomie par jour")  # fmt: skip
    if minutes < 5:
        return f"Non : {conso}."
    principal = par_module[0]["nom"] if par_module else "un module"
    if minutes < 30:
        return f"Un peu : {conso}, surtout {principal}."
    return f"Oui : {conso}, surtout {principal}. Regarde la page Ressources."


def _minutes(m: float) -> str:
    if m < 1:
        return "moins d'une minute"
    if m < 60:
        return f"{m:.0f} min"
    return textes.duree(m * 60)
