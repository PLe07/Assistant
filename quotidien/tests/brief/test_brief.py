"""Le brief du matin dans toutes les combinaisons : les lignes vides sont omises, une brique en panne n'emporte pas
les autres, et la page « Ma journée » est écrite (texte échappé)."""

from __future__ import annotations

import itertools
from datetime import date
from pathlib import Path

import pytest

from quotidien import brief, config
from quotidien.db import Base as BaseDonnees
from quotidien.repas import planificateur as pl
from quotidien.repas import service
from quotidien.repas.base import charger

BASE = charger()
METEO = "☀️ 14 °C → 19 °C, sec : veste légère, lunettes. Vélo OK."
ANNIV = "🎂 Demain : anniversaire de Léa → message prêt."


@pytest.fixture
def db(maison: Path) -> BaseDonnees:
    return BaseDonnees(config.chemin_base())


def _casse() -> str:
    raise RuntimeError("panne")


def test_composer() -> None:
    assert brief.composer(None, "", "  ", "a", None, "b", "a") == ["a", "b"]
    assert brief.composer() == []


@pytest.mark.parametrize(("meteo", "menu", "anniv"), list(itertools.product(("ok", "absente", "panne"),
                                                                            (True, False), (True, False))))  # fmt: skip
def test_toutes_les_combinaisons(db: BaseDonnees, meteo: str, menu: bool, anniv: bool) -> None:
    mardi = date(2026, 10, 13)
    if menu:
        service.produire(db, config.defauts(), date(2026, 10, 12), base=BASE)
    source_meteo = {"ok": lambda: METEO, "absente": lambda: None, "panne": _casse}[meteo]
    b = brief.produire(db, config.defauts(), mardi, 0.0, meteo=source_meteo,
                       anniversaires=(lambda: ANNIV) if anniv else (lambda: None), base=BASE)  # fmt: skip
    attendu = []
    if meteo == "ok":
        attendu.append(METEO)
    assert b.lignes[: len(attendu)] == attendu
    assert any(x.startswith("🍽️ ") for x in b.lignes) == menu
    assert (ANNIV in b.lignes) == anniv
    assert all(x.strip() for x in b.lignes) and len(b.lignes) == len(set(b.lignes))
    assert b.texte == "\n".join(b.lignes)


def test_ligne_repas_restes_et_courses(db: BaseDonnees) -> None:
    r = config.defauts()
    resultat = service.produire(db, r, date(2026, 10, 12), base=BASE)
    menu = resultat.menu
    source = next(x for x in menu.repas if x.restes_pour)
    jour = source.date
    ligne = brief.ligne_repas(db, BASE, jour)
    assert ligne is not None and ligne.startswith("🍽️ Ce soir : ") and " — reste pour " in ligne
    reste = next(x for x in menu.repas if x.genre == "reste")
    assert "restes de" in (brief.ligne_repas(db, BASE, reste.date) or "")
    assert brief.ligne_repas(db, BASE, date(2030, 1, 1)) is None
    lundi = brief.ligne_courses(db, BASE, r, date(2026, 10, 12))
    assert lundi is not None and lundi.startswith("🛒 Jour de courses : ")
    assert brief.ligne_courses(db, BASE, r, date(2026, 10, 13)) is None
    assert brief.ligne_courses(db, BASE, r, date(2030, 1, 7)) is None
    assert brief.ligne_veille(db, BASE, r, date(2030, 1, 7)) is None


def test_reste_pour_demain_midi(db: BaseDonnees) -> None:
    rec = next(iter(BASE.recettes))
    soir = pl.Repas("2026-10-13", "diner", "cuisine", rec, 2.0, restes_pour=["2026-10-14/dejeuner"])
    assert brief._plat(BASE, soir, date(2026, 10, 14)).endswith("— reste pour demain midi")
    plus_tard = pl.Repas("2026-10-13", "diner", "cuisine", rec, 2.0, restes_pour=["2026-10-15/diner"])
    assert brief._plat(BASE, plus_tard, date(2026, 10, 14)).endswith("— reste pour jeudi soir")


def test_page_ma_journee(maison: Path) -> None:
    b = brief.Brief(date(2026, 10, 13), ["☀️ <b>chaud</b> & sec", ANNIV])
    chemin = brief.publier(b)
    assert chemin.name == "Ma journée.html" and chemin.parent == config.dossier_support()
    html = chemin.read_text(encoding="utf-8")
    assert "&lt;b&gt;chaud&lt;/b&gt; &amp; sec" in html and "<b>chaud" not in html
    assert "Mardi 13 octobre" in html
    import json

    assert json.loads((config.dossier_support() / "brief.json").read_text(encoding="utf-8")) == {
        "date": "2026-10-13", "lignes": ["☀️ <b>chaud</b> & sec", ANNIV]}  # fmt: skip
    config.icloud_drive().mkdir(parents=True)
    assert brief.publier(brief.Brief(date(2026, 10, 13))).parent == config.dossier_icloud()
    assert "Rien de particulier" in (config.dossier_icloud() / "Ma journée.html").read_text(encoding="utf-8")
