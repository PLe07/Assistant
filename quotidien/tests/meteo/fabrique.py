"""Fabrique de réponses Open-Meteo, exactement au format de l'API (`timeformat=unixtime`, D-06).

Les heures sont des instants Unix pris d'heure en heure depuis minuit (heure de Paris) du premier jour : un jour de
changement d'heure compte donc 23 ou 25 heures, comme dans la vraie réponse.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")

DEFAUT = {
    "temperature_2m": 15.0,
    "apparent_temperature": 15.0,
    "precipitation_probability": 0,
    "precipitation": 0.0,
    "weather_code": 1,
    "wind_speed_10m": 10.0,
    "wind_gusts_10m": 20.0,
    "uv_index": 0.0,
    "relative_humidity_2m": 70,
}


def reponse(
    debut: date,
    jours: int = 4,
    valeurs: Callable[[datetime], dict[str, Any]] | None = None,
    lever: str = "07:30",
    coucher: str = "19:30",
    iso: bool = False,
) -> dict[str, Any]:
    """`valeurs(instant_local)` renvoie les variables à changer pour cette heure (le reste : DEFAUT)."""
    minuit = datetime.combine(debut, time(0, 0), tzinfo=PARIS)
    fin = datetime.combine(debut + timedelta(days=jours), time(0, 0), tzinfo=PARIS)
    instants: list[datetime] = []
    t = minuit.astimezone(UTC)
    while t < fin.astimezone(UTC):
        instants.append(t.astimezone(PARIS))
        t += timedelta(hours=1)
    horaire: dict[str, list[Any]] = {"time": []}
    for v in DEFAUT:
        horaire[v] = []
    for instant in instants:
        horaire["time"].append(instant.strftime("%Y-%m-%dT%H:%M") if iso else int(instant.timestamp()))
        donnees = dict(DEFAUT)
        if valeurs:
            donnees.update(valeurs(instant))
        if "apparent_temperature" not in (valeurs(instant) if valeurs else {}):
            donnees["apparent_temperature"] = donnees["temperature_2m"]
        for v in DEFAUT:
            horaire[v].append(donnees[v])
    quotidien: dict[str, list[Any]] = {"time": [], "sunrise": [], "sunset": []}
    for i in range(jours):
        j = debut + timedelta(days=i)
        lv = datetime.combine(j, time.fromisoformat(lever), tzinfo=PARIS)
        co = datetime.combine(j, time.fromisoformat(coucher), tzinfo=PARIS)
        if iso:
            quotidien["time"].append(j.isoformat())
            quotidien["sunrise"].append(lv.strftime("%Y-%m-%dT%H:%M"))
            quotidien["sunset"].append(co.strftime("%Y-%m-%dT%H:%M"))
        else:
            quotidien["time"].append(int(datetime.combine(j, time(0, 0), tzinfo=PARIS).timestamp()))
            quotidien["sunrise"].append(int(lv.timestamp()))
            quotidien["sunset"].append(int(co.timestamp()))
    decalage = int(minuit.utcoffset().total_seconds()) if minuit.utcoffset() else 0
    return {
        "latitude": 44.84,
        "longitude": -0.58,
        "generationtime_ms": 0.31,
        "utc_offset_seconds": decalage,
        "timezone": "Europe/Paris",
        "timezone_abbreviation": "GMT+2" if decalage == 7200 else "GMT+1",
        "elevation": 15.0,
        "hourly_units": {
            "time": "iso8601" if iso else "unixtime",
            "temperature_2m": "°C",
            "apparent_temperature": "°C",
            "precipitation_probability": "%",
            "precipitation": "mm",
            "weather_code": "wmo code",
            "wind_speed_10m": "km/h",
            "wind_gusts_10m": "km/h",
            "uv_index": "",
            "relative_humidity_2m": "%",
        },
        "hourly": horaire,
        "daily_units": {
            "time": "iso8601" if iso else "unixtime",
            "sunrise": "iso8601" if iso else "unixtime",
            "sunset": "iso8601" if iso else "unixtime",
        },  # fmt: skip
        "daily": quotidien,
    }


def uv_de_jour(instant: datetime, maximum: float) -> float:
    """Un indice UV en cloche : nul la nuit, maximum à 14 h."""
    if not 9 <= instant.hour <= 18:
        return 0.0
    return round(max(0.0, maximum * (1 - abs(instant.hour - 14) / 5)), 1)
