"""Les textes (variés, deux lignes au plus), l'alerte de la veille, le fichier de règles et la ligne du brief."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from quotidien import config
from quotidien.db import Base
from quotidien.meteo import open_meteo, regles, service, textes, trajets
from tests.meteo import fabrique
from tests.meteo.test_open_meteo import FauxOpenMeteo

REGLES, _ = regles.charger_regles()
PROFIL = config.defauts().profil
FIXTURE = Path(__file__).parent / "fixtures" / "bordeaux_janvier.json"


def _prev(valeurs: Any, debut: date = date(2026, 1, 13), jours: int = 4, **kw: Any) -> open_meteo.Prevision:
    return open_meteo.analyser(fabrique.reponse(debut, jours, valeurs, **kw), 0.0)


def test_au_moins_5_variantes_par_situation() -> None:
    assert set(textes.PRINCIPALES) >= {"pluie_trajet", "pluie_journee", "orage", "neige", "verglas", "vent",
                                       "brouillard", "froid", "chaud", "beau", "voile", "gris"}  # fmt: skip
    for situation, modeles in textes.PRINCIPALES.items():
        assert len(set(modeles)) >= 5, situation
    for groupe in (textes.VELO_OK, textes.TRAM, textes.TRAM_JOURNEE, textes.RETOUR_SEC, textes.RETOUR_PLUIE,
                   textes.RETOUR_SEUL_PLUIE, textes.BASCULE, textes.FRAICHEUR, textes.NUIT):  # fmt: skip
        assert len(set(groupe)) >= 5


def test_jamais_le_meme_message_deux_jours_de_suite() -> None:
    """Même météo plusieurs jours de suite : le modèle change chaque jour (donc jamais 3 jours identiques)."""
    precedents: list[str] = []
    profil = config.defauts().profil
    profil["semaine"]["jours_de_cours"] = list(config.JOURS)
    prev = _prev(lambda i: {"temperature_2m": 14.0}, date(2026, 5, 1), 16)
    for k in range(1, 15):
        c = regles.conseiller(prev, date(2026, 5, 1) + timedelta(days=k), profil, REGLES)
        assert c is not None
        texte = textes.rediger(c)
        if precedents:
            assert texte != precedents[-1]
        precedents.append(texte)
    assert len(set(precedents)) >= 5


def test_meme_jour_meme_texte() -> None:
    c = regles.conseiller(_prev(lambda i: {}), date(2026, 1, 14), PROFIL, REGLES)
    assert c is not None and textes.rediger(c) == textes.rediger(c)


def test_exemple_de_la_mission() -> None:
    """« 🌧️ 11 °C, pluie entre 8h et 9h : imper + gants à vélo. Retour au sec vers 18h30. »"""

    def valeurs(i: datetime) -> dict[str, Any]:
        return {"temperature_2m": 11.0, "apparent_temperature": 10.0,
                "precipitation": 3.0 if i.date() == date(2026, 1, 14) and i.hour == 9 else 0.0,
                "weather_code": 61 if i.hour == 9 else 3}  # fmt: skip

    c = regles.conseiller(_prev(valeurs, lever="07:00", coucher="20:00"), date(2026, 1, 14), PROFIL, REGLES)
    assert c is not None
    texte = textes.rediger(c)
    assert texte.startswith("🌧️")
    assert "11 °C" in texte and "8h" in texte and "9h" in texte
    assert "imper ou poncho + sur-pantalon" in texte and "gants à vélo" in texte
    assert "18h30" in texte  # retour au sec
    assert texte.count("\n") <= 1
    assert c.pluie_equipement and c.situation == "pluie_trajet"


def test_beau_temps_velo_ok_et_lunettes() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"temperature_2m": 14.0 if i.hour < 11 else 19.0, "apparent_temperature": 21.0,
                "uv_index": fabrique.uv_de_jour(i, 6), "weather_code": 0}  # fmt: skip

    c = regles.conseiller(_prev(valeurs, date(2026, 5, 12), lever="06:40", coucher="21:20"), date(2026, 5, 13),
                          PROFIL, REGLES)  # fmt: skip
    assert c is not None and c.situation == "beau"
    texte = textes.rediger(c)
    assert texte.startswith("☀️ 14 °C → 19 °C")
    assert "lunettes" in texte and "veste légère" in texte
    assert any(v in texte for v in textes.VELO_OK)


def test_journee_sans_cours() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"temperature_2m": 16.0, "uv_index": fabrique.uv_de_jour(i, 5), "weather_code": 1}

    c = regles.conseiller(_prev(valeurs, date(2026, 5, 15)), date(2026, 5, 16), PROFIL, REGLES)
    assert c is not None and not c.cours and not c.velo and c.trajets[0].nom == "journée"
    texte = textes.rediger(c)
    assert "lunettes de soleil si tu sors" in texte
    assert not any(v in texte for v in textes.VELO_OK)


def test_nuit_texte() -> None:
    c = regles.conseiller(_prev(lambda i: {"temperature_2m": 9.0}, lever="08:40", coucher="17:20"), date(2026, 1, 14),
                          PROFIL, REGLES)  # fmt: skip
    assert c is not None and c.trajets_nuit == ["aller", "retour"]
    texte = textes.rediger(c)
    assert "casque" in texte.lower() and "éclairage" in texte.lower()
    assert "l'aller comme au retour" in texte.lower()


def test_pluie_seulement_au_retour() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"precipitation": 4.0 if i.date() == date(2026, 1, 14) and i.hour == 19 else 0.0}

    c = regles.conseiller(_prev(valeurs, lever="07:00", coucher="20:00"), date(2026, 1, 14), PROFIL, REGLES)
    assert c is not None
    texte = textes.rediger(c)
    assert "18h30" in texte and "sac" in texte or "emporte" in texte


def test_pluie_aller_et_retour() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"precipitation": 3.0 if i.date() == date(2026, 1, 14) and i.hour in (9, 19) else 0.0}

    c = regles.conseiller(_prev(valeurs, lever="07:00", coucher="20:00"), date(2026, 1, 14), PROFIL, REGLES)
    assert c is not None and "à l'aller et au retour" in textes.rediger(c)


def test_pluie_hors_trajets() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"precipitation": 2.0 if i.date() == date(2026, 1, 14) and i.hour in (15, 16) else 0.0}

    c = regles.conseiller(_prev(valeurs, lever="07:00", coucher="20:00"), date(2026, 1, 14), PROFIL, REGLES)
    assert c is not None and c.situation == "pluie_journee" and c.pluie_journee is not None
    assert "entre 14h et 16h" in textes.rediger(c)
    assert textes._quand_pluie(c) == "entre 14h et 16h"


def test_hors_ligne_signale() -> None:
    c = regles.conseiller(_prev(lambda i: {}), date(2026, 1, 14), PROFIL, REGLES)
    assert c is not None
    c.hors_ligne, c.age_prevision_h = True, 5.2
    assert "prévision d'il y a 5 h, Mac hors ligne" in textes.rediger(c)


@pytest.mark.parametrize(
    "valeurs,situation",
    [
        ({"weather_code": 95}, "orage"),
        ({"weather_code": 45}, "brouillard"),
        ({"temperature_2m": 30.0}, "chaud"),
        ({"temperature_2m": 3.0, "relative_humidity_2m": 60}, "froid"),
        ({"weather_code": 2}, "voile"),
        ({"weather_code": 3}, "gris"),
        ({"wind_gusts_10m": 65.0}, "vent"),
    ],
)
def test_situations(valeurs: dict[str, Any], situation: str) -> None:
    c = regles.conseiller(_prev(lambda i: valeurs), date(2026, 1, 14), PROFIL, REGLES)
    assert c is not None and c.situation == situation
    assert textes.rediger(c).count("\n") <= 1


def test_degres() -> None:
    assert textes.degres(-0.4) == "0 °C" and textes.degres(-2.6) == "−3 °C" and textes.degres(21.5) == "22 °C"


def test_trajets_heures() -> None:
    assert trajets.heure_lisible(datetime(2026, 1, 1, 8, 0)) == "8h"
    assert trajets.heure_lisible(datetime(2026, 1, 1, 18, 30)) == "18h30"
    t = trajets.trajets_du_jour(date(2026, 1, 14), PROFIL)
    assert [x.nom for x in t] == ["aller", "retour"] and t[0].libelle_heure() == "8h"
    assert (t[0].fin - t[0].debut) == timedelta(minutes=30)


# --- Alerte de la veille --------------------------------------------------------------------------------------------


def test_alerte_rien_si_demain_ressemble_a_aujourd_hui() -> None:
    assert service.alerte_veille(_prev(lambda i: {"temperature_2m": 12.0}), date(2026, 1, 13), PROFIL, REGLES) is None


def test_alerte_chute_de_temperature() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"temperature_2m": 14.0 if i.date() <= date(2026, 1, 13) else 3.0}

    alerte = service.alerte_veille(_prev(valeurs), date(2026, 1, 13), PROFIL, REGLES)
    assert alerte is not None and alerte.startswith("🌡️ Demain : 11 °C de moins")
    assert "doudoune" in alerte and alerte.count("\n") == 1


def test_alerte_apres_midi_beaucoup_plus_chaud() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        chaud = i.date() == date(2026, 1, 14) and 12 <= i.hour <= 18
        return {"temperature_2m": 24.0 if chaud else 12.0}

    alerte = service.alerte_veille(_prev(valeurs), date(2026, 1, 13), PROFIL, REGLES)
    assert alerte is not None and "12 °C de plus qu'aujourd'hui l'après-midi" in alerte


def test_alerte_arrivee_de_la_pluie() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"precipitation": 3.0 if i.date() == date(2026, 1, 14) and i.hour in (9, 10) else 0.0}

    alerte = service.alerte_veille(_prev(valeurs), date(2026, 1, 13), PROFIL, REGLES)
    assert alerte is not None and alerte.startswith("🌧️ Demain : la pluie revient")
    assert "imper ou poncho" in alerte


def test_alerte_tempete() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"wind_gusts_10m": 95.0 if i.date() == date(2026, 1, 14) else 20.0}

    alerte = service.alerte_veille(_prev(valeurs), date(2026, 1, 13), PROFIL, REGLES)
    assert alerte is not None and alerte.startswith("💨 Demain : tempête (rafales jusqu'à 95 km/h)")
    assert "tram" in alerte


def test_alerte_orage() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        return {"weather_code": 95 if i.date() == date(2026, 1, 14) and i.hour == 15 else 1}

    alerte = service.alerte_veille(_prev(valeurs), date(2026, 1, 13), PROFIL, REGLES)
    assert alerte is not None and "orages" in alerte


def test_alerte_gel_sec() -> None:
    """Gel sec : on le dit, mais sans parler de verglas ni de tram (le moteur de règles ne voit pas de verglas)."""

    def valeurs(i: datetime) -> dict[str, Any]:
        gel = i.date() == date(2026, 1, 14) and i.hour <= 9
        return {"temperature_2m": -3.0 if gel else 4.0, "relative_humidity_2m": 60}

    alerte = service.alerte_veille(_prev(valeurs), date(2026, 1, 13), PROFIL, REGLES)
    assert alerte is not None and "gel au petit matin (−3 °C)" in alerte
    assert "verglas" not in alerte and "tram" not in alerte and "doudoune" in alerte


def test_alerte_gel_humide_verglas_et_tram() -> None:
    def valeurs(i: datetime) -> dict[str, Any]:
        gel = i.date() == date(2026, 1, 14) and i.hour <= 9
        return {"temperature_2m": -1.0 if gel else 4.0, "relative_humidity_2m": 95 if gel else 60}

    alerte = service.alerte_veille(_prev(valeurs), date(2026, 1, 13), PROFIL, REGLES)
    assert alerte is not None and "risque de verglas" in alerte and "tram" in alerte


def test_alerte_sans_prevision_pour_demain() -> None:
    assert service.alerte_veille(_prev(lambda i: {}, jours=1), date(2026, 1, 13), PROFIL, REGLES) is None


# --- Fichier de règles ----------------------------------------------------------------------------------------------


def test_le_fichier_du_projet_egale_les_valeurs_par_defaut() -> None:
    r, avert = regles.charger_regles(config.racine_projet() / "regles_tenue.toml")
    assert avert == [] and r == regles.DEFAUT_REGLES


def test_regles_perso_dans_application_support() -> None:
    config.dossier_support().mkdir(parents=True)
    (config.dossier_support() / "regles_tenue.toml").write_text(
        '[accessoires]\ngants_velo_sous = 10\n[tram]\nrafales_au_dessus_de = "beaucoup"\n', encoding="utf-8"
    )
    r, avert = regles.charger_regles()
    assert r["accessoires"]["gants_velo_sous"] == 10 and r["tram"]["rafales_au_dessus_de"] == 50
    assert len(avert) == 1 and "rafales_au_dessus_de" in avert[0]


@pytest.mark.parametrize(
    "contenu,attendu",
    [
        ("[couches", "illisible"),
        ("velo = 3", "n'est pas une section"),
        ('[[couches]]\na_partir_de = 10\ntenue = ["cape"]\n', "couches"),
    ],
)
def test_regles_mal_remplies(tmp_path: Path, contenu: str, attendu: str) -> None:
    f = tmp_path / "regles.toml"
    f.write_text(contenu, encoding="utf-8")
    r, avert = regles.charger_regles(f)
    assert any(attendu in a for a in avert) and r["couches"] == regles.DEFAUT_REGLES["couches"]


def test_couches_perso_completees_par_le_grand_froid(tmp_path: Path) -> None:
    f = tmp_path / "regles.toml"
    f.write_text('[[couches]]\na_partir_de = 15\ntenue = ["t-shirt"]\n[[couches]]\na_partir_de = 0\n'
                 'tenue = ["pull", "manteau"]\n', encoding="utf-8")  # fmt: skip
    r, avert = regles.charger_regles(f)
    assert avert == [] and r["couches"][-1]["tenue"] == ["pull", "doudoune"]
    assert regles._couches(-10, r) == ["pull", "doudoune"]


# --- La ligne du brief ----------------------------------------------------------------------------------------------


def test_du_jour_avec_la_fixture(tmp_path: Path) -> None:
    base = Base(tmp_path / "q.db")
    faux = FauxOpenMeteo(json.loads(FIXTURE.read_text(encoding="utf-8")))
    m = service.du_jour(base, config.defauts(), date(2026, 1, 14), lambda: 1_768_370_400.0, faux)
    assert m.conseil is not None and m.prevision is not None
    assert m.conseil.situation == "pluie_trajet" and m.conseil.nuit  # 8 h avant le lever (8 h 33)
    assert m.texte.startswith("🌧️") and "casque" in m.texte.lower()
    assert base.lignes("SELECT texte FROM textes_meteo")[0]["texte"] == m.texte


def test_du_jour_indisponible(tmp_path: Path) -> None:
    from quotidien import reseau

    base = Base(tmp_path / "q.db")
    m = service.du_jour(base, config.defauts(), date(2026, 1, 14), lambda: 0.0,
                        FauxOpenMeteo(reseau.ErreurReseau("panne")))  # fmt: skip
    assert m.conseil is None and m.texte == service.INDISPONIBLE
    faux = FauxOpenMeteo(fabrique.reponse(date(2026, 3, 1), 2))
    m = service.du_jour(base, config.defauts(), date(2026, 1, 14), lambda: 0.0, faux)
    assert m.conseil is None and m.texte == service.INDISPONIBLE and m.prevision is not None


def test_toutes_les_variantes_de_nuit_disent_eclairage() -> None:
    assert all("éclairage" in v for v in textes.NUIT)
