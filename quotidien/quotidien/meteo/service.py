"""La météo assemblée : la ligne du brief, et l'alerte de la veille à 21 h (seulement si demain change beaucoup)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as heure
from typing import Any

from quotidien import reseau
from quotidien.config import Reglages
from quotidien.db import Base
from quotidien.meteo import open_meteo, regles, textes
from quotidien.meteo.open_meteo import Prevision


@dataclass
class Meteo:
    conseil: regles.Conseil | None
    texte: str
    prevision: Prevision | None


INDISPONIBLE = "🌡️ Météo indisponible : pas de réseau et aucune prévision gardée. Regarde le ciel avant de partir."


def prevision(
    base: Base,
    reglages: Reglages,
    horloge: Callable[[], float] = time.time,
    telecharger: open_meteo.Telecharger = reseau.telecharger,
) -> Prevision | None:
    return open_meteo.obtenir(base, reglages["lieu"], float(reglages["meteo"]["cache_heures"]), horloge, telecharger)


def du_jour(
    base: Base,
    reglages: Reglages,
    jour: date,
    horloge: Callable[[], float] = time.time,
    telecharger: open_meteo.Telecharger = reseau.telecharger,
) -> Meteo:
    prev = prevision(base, reglages, horloge, telecharger)
    if prev is None:
        return Meteo(None, INDISPONIBLE, None)
    r, _ = regles.charger_regles()
    conseil = regles.conseiller(prev, jour, reglages.profil, r, horloge())
    if conseil is None:
        return Meteo(None, INDISPONIBLE, prev)
    texte = textes.rediger(conseil)
    textes.noter(base, conseil, texte)
    return Meteo(conseil, texte, prev)


def _temperature_vers(prev: Prevision, instant: datetime) -> float | None:
    proches = [h for h in prev.heures if abs((h.instant - instant).total_seconds()) <= 1800]
    return proches[0].temperature if proches else None


def _fenetre(prev: Prevision, jour: date, de: int, a: int) -> list[open_meteo.Heure]:
    zone = prev.heures[0].instant.tzinfo
    debut = datetime.combine(jour, heure(0, 0), tzinfo=zone)
    return prev.entre(debut + timedelta(hours=de), debut + timedelta(hours=a))


def alerte_veille(prev: Prevision, aujourdhui: date, profil: dict[str, Any], r: dict[str, Any]) -> str | None:
    """L'alerte de 21 h : seulement si demain est très différent d'aujourd'hui (8 °C d'écart ou plus, arrivée de la
    pluie, tempête ou gel). Sinon None : pas de notification."""
    demain = aujourdhui + timedelta(days=1)
    c1 = regles.conseiller(prev, demain, profil, r)
    jour0, jour1 = _fenetre(prev, aujourdhui, 7, 21), _fenetre(prev, demain, 7, 21)
    if c1 is None or not jour0 or not jour1:
        return None
    seuils = r["alerte_veille"]
    raisons: list[tuple[str, str]] = []

    depart = c1.trajets[0].debut
    t0 = _temperature_vers(prev, depart - timedelta(days=1))
    t1 = _temperature_vers(prev, depart)
    max0, max1 = max(h.temperature for h in jour0), max(h.temperature for h in jour1)
    if t0 is not None and t1 is not None and abs(t1 - t0) >= seuils["ecart_temperature"]:
        sens = "de moins" if t1 < t0 else "de plus"
        raisons.append(("🌡️", f"{round(abs(t1 - t0))} °C {sens} qu'aujourd'hui au départ ({textes.degres(t1)})"))
    elif abs(max1 - max0) >= seuils["ecart_temperature"]:
        sens = "de moins" if max1 < max0 else "de plus"
        raisons.append(("🌡️", f"{round(abs(max1 - max0))} °C {sens} qu'aujourd'hui l'après-midi"
                               f" ({textes.degres(max1)})"))  # fmt: skip

    pluie0 = sum(h.pluie * part for h, part in prev.couvrant(jour0[0].instant, jour0[-1].instant))
    pluie1 = sum(h.pluie * part for h, part in prev.couvrant(jour1[0].instant, jour1[-1].instant))
    if pluie0 < seuils["pluie_min_mm"] and (pluie1 >= seuils["pluie_min_mm"] or c1.pluie_equipement):
        quand = textes._quand_pluie(c1)
        raisons.append(("🌧️", f"la pluie revient ({quand})"))

    rafales1 = max(h.rafales for h in jour1)
    if rafales1 >= seuils["rafales_tempete"] or c1.orage:
        texte = (
            f"tempête (rafales jusqu'à {round(rafales1)} km/h)" if rafales1 >= seuils["rafales_tempete"] else "orages"
        )
        raisons.append(("💨" if rafales1 >= seuils["rafales_tempete"] else "⛈️", texte))

    matin0, matin1 = _fenetre(prev, aujourdhui, 0, 9), _fenetre(prev, demain, 0, 9)
    gel1 = bool(matin1) and min(h.temperature for h in matin1) < 0
    gel0 = bool(matin0) and min(h.temperature for h in matin0) < 0
    c0 = regles.conseiller(prev, aujourdhui, profil, r)
    verglas0 = c0.verglas if c0 is not None else False
    if (gel1 and not gel0) or (c1.verglas and not verglas0):
        mini = min(h.temperature for h in matin1) if matin1 else 0.0
        if c1.verglas:  # le moteur de règles le confirme : le tram sera conseillé aussi
            raisons.append(("🧊", f"gel au petit matin ({textes.degres(mini)}), risque de verglas"))
        else:
            raisons.append(("🧊", f"gel au petit matin ({textes.degres(mini)})"))

    if not raisons:
        return None
    emoji = raisons[0][0]
    constat = " ; ".join(t for _, t in raisons[:3])
    conseil = textes.tenue(c1)
    ligne1 = f"{emoji} Demain : {constat}."
    if c1.tram:
        ligne2 = f"Prévois {conseil}, et plutôt le tram ({', '.join(c1.raisons_tram)})."
    else:
        ligne2 = f"Prépare ce soir : {conseil}."
    return f"{ligne1}\n{ligne2}"
