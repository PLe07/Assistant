"""La table de décision exhaustive de la tenue (§10.1).

Températures de −5 à 35 °C, six scénarios de pluie, vent calme ou rafales, UV nul ou fort, jour ou nuit, jour de cours
(vélo) ou non : 41 × 6 × 2 × 2 × 2 × 2 = 3 936 cas. Pour chacun, un oracle écrit d'après la mission (et non d'après le
code) dit la tenue attendue ; le moteur doit donner exactement la même chose dans 100 % des cas. S'y ajoutent les
invariants (aucun conseil contradictoire) et les cas particuliers : verglas, bascule, tram, changement d'heure.
"""

from __future__ import annotations

import itertools
from datetime import date, datetime
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from quotidien import config
from quotidien.meteo import open_meteo, regles, textes
from tests.meteo import fabrique

MERCREDI = date(2026, 1, 14)  # jour de cours
SAMEDI = date(2026, 1, 17)

# Scénarios de pluie : (heure de fin de la période pluvieuse → mm dans l'heure). Rappel : la pluie d'une heure h
# tombe entre h − 1 h et h. L'aller (8h–8h30) est couvert par l'heure 9h, le retour (18h30–19h) par l'heure 19h.
PLUIES: dict[str, dict[int, float]] = {
    "sec": {},
    "bruine_aller": {9: 1.0},  # 0,5 mm pendant l'aller : pas d'équipement
    "pluie_aller": {9: 3.0},  # 1,5 mm pendant l'aller
    "deluge_aller": {9: 6.0},  # 3 mm, 6 mm/h : tram
    "pluie_retour": {19: 3.0},
    "pluie_continue": {h: 3.0 for h in range(24)},
}


def _attendu(t: int, pluie: str, rafales: int, uv: int, nuit: bool, cours: bool) -> dict[str, Any]:
    """L'oracle, écrit d'après la mission."""
    velo = cours
    ref = t - 3 if velo else t
    if ref >= 22:
        couches = ["t-shirt"]
    elif ref >= 17:
        couches = ["t-shirt", "veste légère"]
    elif ref >= 12:
        couches = ["pull", "veste légère"]
    elif ref >= 5:
        couches = ["pull", "manteau"]
    else:
        couches = ["pull", "doudoune"]
    acc = []
    if ref < (8 if velo else 2):
        acc.append("gants")
    if ref < 3:
        acc.append("bonnet")
    if ref < 5:
        acc.append("tour de cou")
    if uv >= 3 and pluie != "pluie_continue":
        acc.append("lunettes de soleil")
    if nuit and velo:
        acc += ["casque", "éclairage"]
    # mm tombés pendant les trajets
    p = PLUIES[pluie]
    if cours:
        mm_trajets = [p.get(9, 0.0) * 0.5, p.get(19, 0.0) * 0.5]  # 30 min de l'heure
        max_h = max(p.get(9, 0.0), p.get(19, 0.0))
    else:
        mm_trajets = [sum(v for h, v in p.items() if 10 <= h <= 19)]  # périodes dans 9h–19h
        max_h = max([v for h, v in p.items() if 10 <= h <= 19], default=0.0)
    verglas = t <= 1 and pluie != "sec"
    raisons = []
    if rafales > 50:
        raisons.append("rafales")
    if max_h > 4:
        raisons.append("pluie")
    if verglas:
        raisons.append("verglas")
    tram = bool(raisons)
    equipement: list[str] = []
    if any(mm > 1 for mm in mm_trajets):
        if velo and not tram:
            equipement = ["imper ou poncho", "sur-pantalon"]
        elif rafales > 50:
            equipement = ["imper à capuche"]
        else:
            equipement = ["parapluie"]
    return {"couches": couches, "accessoires": acc, "pluie": equipement, "tram": tram, "verglas": verglas}


def _prevision(t: int, pluie: str, rafales: int, uv: int, nuit: bool, jour: date) -> open_meteo.Prevision:
    p = PLUIES[pluie]

    def valeurs(instant: datetime) -> dict[str, Any]:
        v: dict[str, Any] = {
            "temperature_2m": float(t),
            "wind_gusts_10m": float(rafales),
            "wind_speed_10m": float(rafales) / 2,
            "uv_index": fabrique.uv_de_jour(instant, uv),
        }
        if instant.date() == jour and instant.hour in p:
            v["precipitation"] = p[instant.hour]
            v["weather_code"] = 61
            v["precipitation_probability"] = 90
        return v

    lever, coucher = ("08:40", "17:20") if nuit else ("07:00", "20:00")
    donnees = fabrique.reponse(jour.replace(day=jour.day - 1), 4, valeurs, lever, coucher)
    return open_meteo.analyser(donnees, 0.0)


REGLES, _ = regles.charger_regles()
PROFIL = config.defauts().profil

CAS = list(itertools.product(range(-5, 36), PLUIES, (20, 60), (0, 5), (False, True), (True, False)))


def test_table_exhaustive_100_pour_cent() -> None:
    assert len(CAS) == 3936
    echecs: list[str] = []
    for t, pluie, rafales, uv, nuit, cours in CAS:
        jour = MERCREDI if cours else SAMEDI
        c = regles.conseiller(_prevision(t, pluie, rafales, uv, nuit, jour), jour, PROFIL, REGLES)
        assert c is not None
        attendu = _attendu(t, pluie, rafales, uv, nuit, cours)
        obtenu = {"couches": c.couches, "accessoires": c.accessoires, "pluie": c.pluie_equipement, "tram": c.tram,
                  "verglas": c.verglas}  # fmt: skip
        if obtenu != attendu:
            echecs.append(f"{(t, pluie, rafales, uv, nuit, cours)} : attendu {attendu}, obtenu {obtenu}")
        texte = textes.rediger(c)
        if texte.count("\n") > 1:
            echecs.append(f"{(t, pluie, rafales, uv, nuit, cours)} : plus de deux lignes")
        _verifier_invariants(c, texte, echecs)
    assert not echecs, f"{len(echecs)} cas faux sur {len(CAS)} :\n" + "\n".join(echecs[:20])


def _verifier_invariants(c: regles.Conseil, texte: str, echecs: list[str]) -> None:
    cle = f"{c.jour} {c.situation}"
    if c.verglas and not c.tram:
        echecs.append(f"{cle} : verglas sans conseil tram")
    if c.nuit and "éclairage" not in c.accessoires:
        echecs.append(f"{cle} : trajet de nuit sans éclairage")
    if "éclairage" in c.accessoires and not c.nuit:
        echecs.append(f"{cle} : éclairage de jour")
    if "parapluie" in c.pluie_equipement and c.velo_aujourdhui:
        echecs.append(f"{cle} : parapluie un jour de vélo")
    if c.pluie_equipement and not any(p.mm > 1 for p in c.pluies):
        echecs.append(f"{cle} : équipement de pluie sans pluie")
    if "t-shirt" in c.couches and len(c.couches) == 1 and ("gants" in c.accessoires or "bonnet" in c.accessoires):
        echecs.append(f"{cle} : t-shirt seul avec gants ou bonnet")
    if "lunettes de soleil" in c.accessoires and c.situation in ("orage", "neige"):
        echecs.append(f"{cle} : lunettes sous l'orage ou la neige")
    if c.tram and "Vélo OK" in texte:
        echecs.append(f"{cle} : « Vélo OK » alors que le tram est conseillé")
    if c.nuit and "éclairage" not in texte:
        echecs.append(f"{cle} : trajet de nuit sans « éclairage » dans le texte")
    if c.tram and "tram" not in texte:
        echecs.append(f"{cle} : tram conseillé mais absent du texte")


def test_lunettes_jamais_sous_la_pluie_de_nuit() -> None:
    """Le cas cité par la mission : pluie toute la journée, trajets de nuit, UV annoncé quand même."""

    def valeurs(instant: datetime) -> dict[str, Any]:
        return {"precipitation": 2.0, "weather_code": 63, "uv_index": 6.0, "temperature_2m": 10.0}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 3, valeurs, "08:40", "17:20"), 0.0)
    c = regles.conseiller(prev, MERCREDI, PROFIL, REGLES)
    assert c is not None
    assert "lunettes de soleil" not in c.accessoires
    assert "éclairage" in c.accessoires and c.nuit and c.trajets_nuit == ["aller", "retour"]


def test_lunettes_de_nuit_meme_avec_uv_annonce() -> None:
    """Un UV aberrant annoncé la nuit ne donne pas de lunettes (seules les heures de jour comptent)."""

    def valeurs(instant: datetime) -> dict[str, Any]:
        return {"uv_index": 5.0 if instant.hour < 7 or instant.hour > 21 else 0.0}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 6, 16), 3, valeurs, "06:20", "22:10"), 0.0)
    c = regles.conseiller(prev, date(2026, 6, 17), PROFIL, REGLES)
    assert c is not None and "lunettes de soleil" not in c.accessoires


@pytest.mark.parametrize("t", [-3, -1, 0, 1])
def test_verglas_froid_humide(t: int) -> None:
    def valeurs(instant: datetime) -> dict[str, Any]:
        return {"temperature_2m": float(t), "relative_humidity_2m": 95}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 3, valeurs), 0.0)
    c = regles.conseiller(prev, MERCREDI, PROFIL, REGLES)
    assert c is not None and c.verglas and c.tram and "risque de verglas" in c.raisons_tram
    assert c.situation == "verglas" and "tram" in textes.rediger(c)


def test_pas_de_verglas_a_2_degres_ni_au_sec() -> None:
    for t, humidite in ((2, 95), (0, 60)):

        def valeurs(instant: datetime, t: int = t, humidite: int = humidite) -> dict[str, Any]:
            return {"temperature_2m": float(t), "relative_humidity_2m": humidite}

        prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 3, valeurs), 0.0)
        c = regles.conseiller(prev, MERCREDI, PROFIL, REGLES)
        assert c is not None and not c.verglas, (t, humidite)


def test_verglas_pluie_la_veille_et_gel_au_petit_matin() -> None:
    def valeurs(instant: datetime) -> dict[str, Any]:
        if instant.date() == date(2026, 1, 13):
            return {"precipitation": 0.4 if 14 <= instant.hour <= 18 else 0.0, "temperature_2m": 6.0}
        # Le 14 : −2 °C à 6 h, puis 3 °C au départ (8 h), air sec : seule la règle « veille + gel » joue.
        return {"temperature_2m": -2.0 if instant.hour <= 6 else 3.0, "relative_humidity_2m": 60}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 3, valeurs), 0.0)
    c = regles.conseiller(prev, MERCREDI, PROFIL, REGLES)
    assert c is not None and c.verglas and c.tram


def test_verglas_pluie_verglacante() -> None:
    def valeurs(instant: datetime) -> dict[str, Any]:
        return {"weather_code": 66 if instant.hour == 8 else 3, "temperature_2m": 4.0}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 3, valeurs), 0.0)
    c = regles.conseiller(prev, MERCREDI, PROFIL, REGLES)
    assert c is not None and c.verglas and c.tram


def test_neige_tram() -> None:
    def valeurs(instant: datetime) -> dict[str, Any]:
        return {"weather_code": 73, "temperature_2m": 3.0, "relative_humidity_2m": 80}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 3, valeurs), 0.0)
    c = regles.conseiller(prev, MERCREDI, PROFIL, REGLES)
    assert c is not None and c.neige and c.tram and c.situation == "neige" and "neige" in c.raisons_tram


def test_bascule_de_la_journee() -> None:
    def valeurs(instant: datetime) -> dict[str, Any]:
        h = instant.hour
        return {"temperature_2m": 9.0 if h <= 10 else (21.0 if 13 <= h <= 17 else 15.0)}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 4, 14), 3, valeurs), 0.0)
    c = regles.conseiller(prev, date(2026, 4, 15), PROFIL, REGLES)
    assert c is not None and c.bascule == (9, 21)
    texte = textes.rediger(c)
    assert "9 °C" in texte and "21 °C" in texte and "→" in texte
    assert any(m.format(m=9, a=21) in texte for m in textes.BASCULE)


def test_fraicheur_au_retour() -> None:
    def valeurs(instant: datetime) -> dict[str, Any]:
        return {"temperature_2m": 18.0 if instant.hour < 15 else 8.0}

    prev = open_meteo.analyser(fabrique.reponse(date(2026, 4, 14), 3, valeurs), 0.0)
    c = regles.conseiller(prev, date(2026, 4, 15), PROFIL, REGLES)
    assert c is not None and c.fraicheur_retour == (18, 8)
    assert c.couches == ["pull", "manteau"]  # habillé pour le plus froid (8 − 3 = 5 °C à vélo)
    assert "8 °C" in textes.rediger(c)


def test_profil_tram_parapluie() -> None:
    profil = config.defauts().profil
    profil["trajets"]["moyen"] = "tram"
    c = regles.conseiller(_prevision(12, "pluie_aller", 20, 0, False, MERCREDI), MERCREDI, profil, REGLES)
    assert c is not None and not c.velo and c.pluie_equipement == ["parapluie"]
    assert "éclairage" not in c.accessoires and c.couches == ["pull", "veste légère"]  # pas de correction vélo


def test_prevision_qui_ne_couvre_pas_le_jour() -> None:
    prev = open_meteo.analyser(fabrique.reponse(date(2026, 1, 13), 1), 0.0)
    assert regles.conseiller(prev, MERCREDI, PROFIL, REGLES) is None


@pytest.mark.parametrize("jour", [date(2026, 3, 29), date(2026, 10, 25)])
def test_changement_d_heure(jour: date) -> None:
    """Le dimanche du changement d'heure (23 ou 25 heures) : la pluie de 8 h à 9 h (heure de Paris) est bien vue à
    l'aller, quel que soit le décalage UTC."""
    profil = config.defauts().profil
    profil["semaine"]["jours_de_cours"] = ["dimanche"]

    def valeurs(instant: datetime) -> dict[str, Any]:
        return {"precipitation": 3.0 if instant.date() == jour and instant.hour == 9 else 0.0}

    donnees = fabrique.reponse(jour.replace(day=jour.day - 1), 3, valeurs)
    nb_heures_du_jour = sum(
        1 for t in donnees["hourly"]["time"] if datetime.fromtimestamp(t, fabrique.PARIS).date() == jour
    )
    assert nb_heures_du_jour == (23 if jour.month == 3 else 25)
    prev = open_meteo.analyser(donnees, 0.0)
    c = regles.conseiller(prev, jour, profil, REGLES)
    assert c is not None
    assert c.pluies[0].mm == 1.5 and c.pluies[1].mm == 0
    assert c.pluie_equipement == ["imper ou poncho", "sur-pantalon"]
    assert "entre 8h et 9h" in textes.rediger(c)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    temperatures=st.lists(st.floats(-8, 38), min_size=96, max_size=96),
    pluies=st.lists(st.sampled_from([0.0, 0.0, 0.0, 0.3, 1.5, 3.0, 7.0]), min_size=96, max_size=96),
    rafales=st.lists(st.floats(0, 90), min_size=96, max_size=96),
    uv=st.floats(0, 9),
    humidite=st.integers(30, 100),
    codes=st.lists(st.sampled_from([0, 1, 2, 3, 45, 51, 61, 66, 73, 80, 95]), min_size=96, max_size=96),
    cours=st.booleans(),
    nuit=st.booleans(),
)
def test_jamais_de_conseil_contradictoire(
    temperatures: list[float], pluies: list[float], rafales: list[float], uv: float, humidite: int,
    codes: list[int], cours: bool, nuit: bool,
) -> None:  # fmt: skip
    """Des journées tirées au hasard (températures, pluies, rafales, codes météo heure par heure) : jamais de conseil
    contradictoire, jamais plus de deux lignes."""
    debut = date(2026, 1, 13)

    def valeurs(instant: datetime) -> dict[str, Any]:
        i = min(95, int((instant - datetime(2026, 1, 13, tzinfo=fabrique.PARIS)).total_seconds() // 3600))
        return {"temperature_2m": temperatures[i], "precipitation": pluies[i], "wind_gusts_10m": rafales[i],
                "uv_index": fabrique.uv_de_jour(instant, uv), "relative_humidity_2m": humidite,
                "weather_code": codes[i]}  # fmt: skip

    lever, coucher = ("08:40", "17:20") if nuit else ("07:00", "20:00")
    prev = open_meteo.analyser(fabrique.reponse(debut, 4, valeurs, lever, coucher), 0.0)
    jour = MERCREDI if cours else date(2026, 1, 15)
    profil = config.defauts().profil
    if not cours:
        profil["semaine"]["jours_de_cours"] = []
    c = regles.conseiller(prev, jour, profil, REGLES)
    assert c is not None
    echecs: list[str] = []
    texte = textes.rediger(c)
    _verifier_invariants(c, texte, echecs)
    assert texte.count("\n") <= 1
    assert not echecs, echecs
