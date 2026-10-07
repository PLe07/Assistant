"""Open-Meteo (§3) : la prévision horaire de Bordeaux, gratuite et sans clé.

- Une requête : hier (pour le verglas : « pluie la veille »), aujourd'hui, demain et après-demain, heure par heure :
  température, ressenti, probabilité et quantité de pluie, vent, rafales, UV, code météo, humidité ; lever et coucher
  du soleil chaque jour.
- `timeformat=unixtime` : chaque heure est un instant exact, converti en heure de Paris par `zoneinfo` (aucune
  ambiguïté les nuits de changement d'heure, D-06).
- Attention au sens des données (documentation d'Open-Meteo) : la **pluie** et les **rafales** d'une heure *h* sont le
  cumul et le maximum **de l'heure qui précède** *h* ; température, ressenti, vent, UV et humidité sont la valeur à
  l'instant *h*.
- Cache de 3 h dans la base. Hors ligne ou Open-Meteo en panne : la dernière prévision reçue, marquée `hors_ligne`
  (le brief le signale). Jamais de prévision : `None`, le brief dit « météo indisponible ».
"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from quotidien import reseau
from quotidien.db import Base
from quotidien.journal import log

URL_PREVISION = "https://api.open-meteo.com/v1/forecast"
URL_GEOCODAGE = "https://geocoding-api.open-meteo.com/v1/search"
VARIABLES_HEURE = (
    "temperature_2m",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_gusts_10m",
    "uv_index",
    "relative_humidity_2m",
)
VARIABLES_JOUR = ("sunrise", "sunset")

Telecharger = Callable[..., reseau.Reponse]


class PrevisionInvalide(Exception):
    """La réponse d'Open-Meteo n'a pas la forme attendue."""


@dataclass(frozen=True)
class Heure:
    instant: datetime  # à l'heure de Paris
    temperature: float
    ressenti: float
    proba_pluie: float  # %
    pluie: float  # mm, cumul de l'heure qui précède `instant`
    code: int  # code météo WMO
    vent: float  # km/h, à l'instant
    rafales: float  # km/h, maximum de l'heure qui précède
    uv: float
    humidite: float  # %


@dataclass(frozen=True)
class Soleil:
    jour: date
    lever: datetime
    coucher: datetime


@dataclass
class Prevision:
    heures: list[Heure]
    soleil: dict[date, Soleil]
    recue_le: float
    hors_ligne: bool = False
    fuseau: str = "Europe/Paris"
    erreurs: list[str] = field(default_factory=list)

    def age_heures(self, maintenant: float) -> float:
        return max(0.0, (maintenant - self.recue_le) / 3600)

    def entre(self, debut: datetime, fin: datetime) -> list[Heure]:
        """Les heures dont l'instant est dans [debut, fin]."""
        return [h for h in self.heures if debut <= h.instant <= fin]

    def couvrant(self, debut: datetime, fin: datetime) -> list[tuple[Heure, float]]:
        """Les heures dont la période cumulée (h − 1 h, h] chevauche [debut, fin], avec la part chevauchée (0–1).

        Sert à la pluie et aux rafales, qui portent sur l'heure qui précède."""
        resultat: list[tuple[Heure, float]] = []
        for h in self.heures:
            secondes = (min(fin, h.instant) - max(debut, h.instant - timedelta(hours=1))).total_seconds()
            if secondes > 0:
                resultat.append((h, min(1.0, secondes / 3600)))
        return resultat

    def jours(self) -> list[date]:
        return sorted({h.instant.date() for h in self.heures})


# --- Requête -------------------------------------------------------------------------------------------------------


def url_prevision(latitude: float, longitude: float, fuseau: str = "Europe/Paris") -> str:
    parametres = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "hourly": ",".join(VARIABLES_HEURE),
        "daily": ",".join(VARIABLES_JOUR),
        "timezone": fuseau,
        "timeformat": "unixtime",
        "past_days": "1",
        "forecast_days": "3",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "temperature_unit": "celsius",
    }
    return f"{URL_PREVISION}?{urllib.parse.urlencode(parametres)}"


def _nombre(valeur: Any, defaut: float | None = None) -> float | None:
    if isinstance(valeur, bool):
        return defaut
    if isinstance(valeur, int | float):
        return float(valeur)
    return defaut


def _instant(valeur: Any, zone: ZoneInfo, decalage: int) -> datetime:
    """Un instant Open-Meteo : secondes Unix (ce que Quotidien demande) ou texte ISO local."""
    if isinstance(valeur, int | float) and not isinstance(valeur, bool):
        return datetime.fromtimestamp(float(valeur), tz=zone)
    if isinstance(valeur, str):
        naif = datetime.fromisoformat(valeur)
        if naif.tzinfo is not None:
            return naif.astimezone(zone)
        # Heure locale du fuseau demandé : on l'interprète avec le décalage annoncé par Open-Meteo.
        return (naif - timedelta(seconds=decalage)).replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    raise PrevisionInvalide(f"instant illisible : {valeur!r}")


def analyser(donnees: Any, recue_le: float, fuseau: str = "Europe/Paris") -> Prevision:
    """Transforme la réponse JSON d'Open-Meteo en `Prevision`. Lève PrevisionInvalide."""
    if not isinstance(donnees, dict):
        raise PrevisionInvalide("la réponse n'est pas un objet JSON")
    if donnees.get("error"):
        raise PrevisionInvalide(f"Open-Meteo signale une erreur : {str(donnees.get('reason'))[:200]}")
    horaire, quotidien = donnees.get("hourly"), donnees.get("daily")
    if not isinstance(horaire, dict) or not isinstance(horaire.get("time"), list) or not horaire["time"]:
        raise PrevisionInvalide("pas de données heure par heure")
    zone = ZoneInfo(fuseau)
    decalage = int(_nombre(donnees.get("utc_offset_seconds"), 0) or 0)
    n = len(horaire["time"])
    colonnes: dict[str, list[Any]] = {}
    for v in VARIABLES_HEURE:
        col = horaire.get(v)
        if not isinstance(col, list) or len(col) != n:
            raise PrevisionInvalide(f"variable « {v} » absente ou de mauvaise longueur")
        colonnes[v] = col
    heures: list[Heure] = []
    erreurs: list[str] = []
    for i, t in enumerate(horaire["time"]):
        temperature = _nombre(colonnes["temperature_2m"][i])
        if temperature is None:
            erreurs.append(f"heure {i} sans température : ignorée")
            continue
        ressenti = _nombre(colonnes["apparent_temperature"][i], temperature)
        heures.append(
            Heure(
                instant=_instant(t, zone, decalage),
                temperature=temperature,
                ressenti=ressenti if ressenti is not None else temperature,
                proba_pluie=_nombre(colonnes["precipitation_probability"][i], 0.0) or 0.0,
                pluie=max(0.0, _nombre(colonnes["precipitation"][i], 0.0) or 0.0),
                code=int(_nombre(colonnes["weather_code"][i], 0) or 0),
                vent=_nombre(colonnes["wind_speed_10m"][i], 0.0) or 0.0,
                rafales=_nombre(colonnes["wind_gusts_10m"][i], 0.0) or 0.0,
                uv=_nombre(colonnes["uv_index"][i], 0.0) or 0.0,
                humidite=_nombre(colonnes["relative_humidity_2m"][i], 0.0) or 0.0,
            )
        )
    if not heures:
        raise PrevisionInvalide("aucune heure exploitable")
    heures.sort(key=lambda h: h.instant)
    soleil: dict[date, Soleil] = {}
    if isinstance(quotidien, dict) and isinstance(quotidien.get("time"), list):
        levers, couchers = quotidien.get("sunrise") or [], quotidien.get("sunset") or []
        for i, t in enumerate(quotidien["time"]):
            try:
                jour = _instant(t, zone, decalage).date() if not isinstance(t, str) else date.fromisoformat(t[:10])
                lever, coucher = _instant(levers[i], zone, decalage), _instant(couchers[i], zone, decalage)
            except (IndexError, ValueError, PrevisionInvalide):
                erreurs.append(f"jour {i} sans lever ou coucher du soleil")
                continue
            soleil[jour] = Soleil(jour, lever, coucher)
    return Prevision(heures, soleil, recue_le, fuseau=fuseau, erreurs=erreurs)


# --- Cache et repli -------------------------------------------------------------------------------------------------


def _cle_cache(latitude: float, longitude: float) -> str:
    return f"{latitude:.3f},{longitude:.3f}"


def obtenir(
    base: Base,
    lieu: dict[str, Any],
    cache_heures: float = 3,
    horloge: Callable[[], float] = time.time,
    telecharger: Telecharger = reseau.telecharger,
    forcer: bool = False,
) -> Prevision | None:
    """La prévision : en cache si elle a moins de `cache_heures`, sinon demandée à Open-Meteo, sinon la dernière."""
    lat, lon, fuseau = float(lieu["latitude"]), float(lieu["longitude"]), str(lieu.get("fuseau") or "Europe/Paris")
    cle = _cle_cache(lat, lon)
    maintenant = horloge()
    ligne = base.cx.execute("SELECT recu_le, json FROM meteo_cache WHERE cle = ?", (cle,)).fetchone()
    en_cache: Prevision | None = None
    if ligne is not None:
        try:
            en_cache = analyser(json.loads(ligne["json"]), float(ligne["recu_le"]), fuseau)
        except (PrevisionInvalide, json.JSONDecodeError) as e:
            log().warning("prévision en cache illisible : %s", e)
    if en_cache is not None and not forcer and en_cache.age_heures(maintenant) < cache_heures:
        return en_cache
    try:
        reponse = telecharger(url_prevision(lat, lon, fuseau), delai=20)
        if reponse.statut != 200:
            raise PrevisionInvalide(f"Open-Meteo répond {reponse.statut}")
        donnees = json.loads(reponse.texte())
        prevision = analyser(donnees, maintenant, fuseau)
    except (reseau.ErreurReseau, reseau.HoteInterdit, PrevisionInvalide, json.JSONDecodeError) as e:
        log().warning("Open-Meteo indisponible (%s) : %s", e.__class__.__name__, e)
        if en_cache is not None:
            en_cache.hors_ligne = True
            return en_cache
        return None
    with base.transaction() as cx:
        cx.execute(
            "INSERT INTO meteo_cache(cle, recu_le, json) VALUES (?, ?, ?) "
            "ON CONFLICT(cle) DO UPDATE SET recu_le = excluded.recu_le, json = excluded.json",
            (cle, maintenant, json.dumps(donnees)),
        )
    return prevision


@dataclass(frozen=True)
class Lieu:
    nom: str
    latitude: float
    longitude: float
    fuseau: str
    region: str


def geocoder(nom: str, telecharger: Telecharger = reseau.telecharger) -> list[Lieu]:
    """Retrouver une ville (pour régler tes trajets ailleurs qu'à Bordeaux)."""
    parametres = urllib.parse.urlencode({"name": nom, "count": 5, "language": "fr", "format": "json"})
    reponse = telecharger(f"{URL_GEOCODAGE}?{parametres}", delai=15)
    if reponse.statut != 200:
        raise reseau.ErreurReseau(f"géocodage : code {reponse.statut}")
    try:
        donnees = json.loads(reponse.texte())
    except json.JSONDecodeError as e:
        raise reseau.ErreurReseau("géocodage : réponse illisible") from e
    lieux: list[Lieu] = []
    for r in donnees.get("results") or []:
        try:
            lieux.append(Lieu(str(r["name"]), float(r["latitude"]), float(r["longitude"]),
                              str(r.get("timezone") or "Europe/Paris"), str(r.get("admin1") or "")))  # fmt: skip
        except (KeyError, TypeError, ValueError):
            continue
    return lieux
