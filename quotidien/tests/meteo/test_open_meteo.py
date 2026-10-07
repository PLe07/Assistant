"""Open-Meteo : la requête, la lecture de la réponse, le cache de 3 h et le repli hors ligne."""

from __future__ import annotations

import json
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from quotidien import config, reseau
from quotidien.db import Base
from quotidien.meteo import open_meteo
from tests.meteo import fabrique

FIXTURES = Path(__file__).parent / "fixtures"
LIEU = config.DEFAUT_REGLAGES["lieu"]


class FauxOpenMeteo:
    """Imite `reseau.telecharger` : réponses programmées, appels notés."""

    def __init__(self, *reponses: Any) -> None:
        self.reponses = list(reponses)
        self.urls: list[str] = []

    def __call__(self, url: str, **_: Any) -> reseau.Reponse:
        reseau.verifier_url(url)  # la vraie liste blanche s'applique aussi ici
        self.urls.append(url)
        r = self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]
        if isinstance(r, Exception):
            raise r
        if isinstance(r, reseau.Reponse):
            return r
        return reseau.Reponse(200, json.dumps(r).encode(), url)


@pytest.fixture()
def base(tmp_path: Path) -> Base:
    return Base(tmp_path / "q.db")


def test_url_demande_unixtime_hier_et_trois_jours() -> None:
    url = open_meteo.url_prevision(44.8378, -0.5792)
    morceaux = urllib.parse.urlsplit(url)
    assert morceaux.hostname == "api.open-meteo.com" and morceaux.scheme == "https"
    q = urllib.parse.parse_qs(morceaux.query)
    assert q["timeformat"] == ["unixtime"] and q["past_days"] == ["1"] and q["forecast_days"] == ["3"]
    assert q["timezone"] == ["Europe/Paris"]
    for v in ("temperature_2m", "apparent_temperature", "precipitation_probability", "precipitation", "weather_code",
              "wind_gusts_10m", "uv_index", "relative_humidity_2m"):  # fmt: skip
        assert v in q["hourly"][0]
    assert q["daily"] == ["sunrise,sunset"]


def test_fixture_au_format_documente() -> None:
    """La fixture du dépôt, construite au format documenté d'Open-Meteo (D-06), se lit sans erreur."""
    donnees = json.loads((FIXTURES / "bordeaux_janvier.json").read_text(encoding="utf-8"))
    prev = open_meteo.analyser(donnees, 1_000.0)
    assert len(prev.heures) == 96 and prev.erreurs == []
    assert set(prev.soleil) == {date(2026, 1, 13), date(2026, 1, 14), date(2026, 1, 15), date(2026, 1, 16)}
    s = prev.soleil[date(2026, 1, 14)]
    assert s.lever.hour == 8 and s.coucher.hour == 17
    h = prev.entre(datetime(2026, 1, 14, 8, tzinfo=fabrique.PARIS), datetime(2026, 1, 14, 8, tzinfo=fabrique.PARIS))[0]
    assert h.instant.utcoffset() == timedelta(hours=1)
    assert prev.jours()[0] == date(2026, 1, 13)


def test_captures_reelles_du_mac_si_presentes() -> None:
    """Sur ton Mac, install.sh dépose une vraie capture anonymisée : elle doit se lire comme la fixture."""
    for capture in sorted((FIXTURES / "reelles").glob("*.json")):
        prev = open_meteo.analyser(json.loads(capture.read_text(encoding="utf-8")), 0.0)
        assert len(prev.heures) >= 72 and prev.soleil


def test_format_iso_local_aussi() -> None:
    prev_iso = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 2, iso=True), 0.0)
    prev_unix = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 2), 0.0)
    assert [h.instant for h in prev_iso.heures] == [h.instant for h in prev_unix.heures]
    assert prev_iso.soleil == prev_unix.soleil


def test_valeurs_manquantes() -> None:
    donnees = fabrique.reponse(date(2026, 1, 13), 2)
    donnees["hourly"]["temperature_2m"][5] = None
    donnees["hourly"]["apparent_temperature"][6] = None
    donnees["hourly"]["precipitation"][7] = None
    donnees["hourly"]["weather_code"][8] = "?"
    donnees["daily"]["sunrise"] = donnees["daily"]["sunrise"][:1]
    prev = open_meteo.analyser(donnees, 0.0)
    assert len(prev.heures) == 47
    assert prev.heures[5].ressenti == prev.heures[5].temperature  # ressenti manquant : la température
    assert prev.heures[6].pluie == 0.0 and prev.heures[7].code == 0
    assert len(prev.soleil) == 1 and any("lever" in e for e in prev.erreurs)


@pytest.mark.parametrize(
    "casse",
    [
        [],
        {"error": True, "reason": "Latitude must be in range"},
        {"hourly": {"time": []}},
        {"hourly": {"time": [1, 2], "temperature_2m": [1]}},
        {"hourly": {"time": ["pas une date"], **{v: [1] for v in open_meteo.VARIABLES_HEURE}}},
        {"hourly": {"time": [1], **{v: [None] for v in open_meteo.VARIABLES_HEURE}}},
    ],
)
def test_reponses_invalides(casse: Any) -> None:
    with pytest.raises((open_meteo.PrevisionInvalide, ValueError)):
        open_meteo.analyser(casse, 0.0)


def test_cache_de_trois_heures(base: Base) -> None:
    faux = FauxOpenMeteo(fabrique.reponse(date(2026, 1, 13), 4))
    t0 = 1_768_370_400.0
    p1 = open_meteo.obtenir(base, LIEU, 3, lambda: t0, faux)
    p2 = open_meteo.obtenir(base, LIEU, 3, lambda: t0 + 2.9 * 3600, faux)
    assert p1 is not None and p2 is not None and len(faux.urls) == 1 and not p2.hors_ligne
    assert p2.age_heures(t0 + 2.9 * 3600) == pytest.approx(2.9)
    p3 = open_meteo.obtenir(base, LIEU, 3, lambda: t0 + 3.1 * 3600, faux)
    assert p3 is not None and len(faux.urls) == 2 and p3.recue_le == t0 + 3.1 * 3600
    open_meteo.obtenir(base, LIEU, 3, lambda: t0 + 3.2 * 3600, faux, forcer=True)
    assert len(faux.urls) == 3


@pytest.mark.parametrize(
    "panne",
    [
        reseau.ErreurReseau("api.open-meteo.com injoignable"),
        reseau.Reponse(503, b"Service Unavailable", "https://api.open-meteo.com/"),
        reseau.Reponse(200, b"<html>pas du json", "https://api.open-meteo.com/"),
        {"error": True, "reason": "panne"},
    ],
)
def test_hors_ligne_repli_sur_la_derniere_prevision(base: Base, panne: Any) -> None:
    t0 = 1_768_370_400.0
    assert open_meteo.obtenir(base, LIEU, 3, lambda: t0, FauxOpenMeteo(fabrique.reponse(date(2026, 1, 13), 4)))
    p = open_meteo.obtenir(base, LIEU, 3, lambda: t0 + 5 * 3600, FauxOpenMeteo(panne))
    assert p is not None and p.hors_ligne and p.age_heures(t0 + 5 * 3600) == pytest.approx(5)


def test_hors_ligne_sans_rien_en_cache(base: Base) -> None:
    assert open_meteo.obtenir(base, LIEU, 3, lambda: 0.0, FauxOpenMeteo(reseau.ErreurReseau("x"))) is None


def test_cache_illisible_redemande(base: Base) -> None:
    with base.transaction() as cx:
        cx.execute("INSERT INTO meteo_cache(cle, recu_le, json) VALUES ('44.838,-0.579', 1, '{casse')")
    faux = FauxOpenMeteo(fabrique.reponse(date(2026, 1, 13), 4))
    assert open_meteo.obtenir(base, LIEU, 3, lambda: 10.0, faux) is not None and len(faux.urls) == 1


def test_vrai_telechargement_reseau_coupe(base: Base, espion_reseau: Any) -> None:
    """Avec la vraie fonction réseau (réseau coupé pendant les tests) : None, et seul Open-Meteo a été tenté."""
    assert open_meteo.obtenir(base, LIEU, 3) is None
    assert set(espion_reseau.hotes) == {"api.open-meteo.com"}


def test_geocoder() -> None:
    merignac = {"name": "Mérignac", "latitude": 44.84, "longitude": -0.65, "timezone": "Europe/Paris",
                "admin1": "Nouvelle-Aquitaine"}  # fmt: skip
    faux = FauxOpenMeteo({"results": [merignac, {"name": "sans coordonnées"}]})
    lieux = open_meteo.geocoder("Mérignac", faux)
    assert lieux == [open_meteo.Lieu("Mérignac", 44.84, -0.65, "Europe/Paris", "Nouvelle-Aquitaine")]
    assert urllib.parse.urlsplit(faux.urls[0]).hostname == "geocoding-api.open-meteo.com"
    assert open_meteo.geocoder("Nulle-part", FauxOpenMeteo({})) == []
    with pytest.raises(reseau.ErreurReseau):
        open_meteo.geocoder("x", FauxOpenMeteo(reseau.Reponse(500, b"", "https://geocoding-api.open-meteo.com/")))
    with pytest.raises(reseau.ErreurReseau):
        open_meteo.geocoder("x", FauxOpenMeteo(reseau.Reponse(200, b"{", "https://geocoding-api.open-meteo.com/")))


def test_couvrant_prorata() -> None:
    prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 2), 0.0)
    debut = datetime(2026, 1, 13, 8, 0, tzinfo=fabrique.PARIS)
    couverts = prev.couvrant(debut, debut + timedelta(minutes=30))
    assert [(h.instant.hour, part) for h, part in couverts] == [(9, 0.5)]
    couverts = prev.couvrant(debut + timedelta(minutes=45), debut + timedelta(minutes=75))
    assert [(h.instant.hour, round(part, 2)) for h, part in couverts] == [(9, 0.25), (10, 0.25)]
