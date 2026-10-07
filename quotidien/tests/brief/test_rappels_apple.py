"""Tes listes de Rappels : seulement « Courses (menu) » et « Anniversaires », un suffixe « (Quotidien) » si une
liste de ce nom existe déjà sans être à nous, jamais une autre liste lue ni touchée, jamais un rappel en double."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from quotidien import config, rappels_apple
from quotidien.anniversaires.dates import DateNaissance
from quotidien.anniversaires.proches import Personne
from quotidien.db import Base as BaseDonnees
from quotidien.repas.base import charger as charger_base
from quotidien.systeme import Systeme
from tests.faux_mac import FauxMac

AUTRES = {"Travail": ["rapport", "réunion"], "Corvées": ["poubelles"], "Courses (menu)": ["lait d'un autre projet"]}


@pytest.fixture
def db(maison: Path) -> BaseDonnees:
    return BaseDonnees(config.chemin_base())


def _rappels(db: BaseDonnees, mac: FauxMac, **reglages: object) -> rappels_apple.Rappels:
    r = config.defauts().reglages
    r["rappels"].update(reglages)
    return rappels_apple.Rappels(db, mac.systeme(), r)


def test_collision_suffixe_et_listes_des_autres_intactes(db: BaseDonnees) -> None:
    mac = FauxMac({k: list(v) for k, v in AUTRES.items()})
    avant = mac.etat_listes()
    r = _rappels(db, mac)
    assert r.liste("courses") == "Courses (menu) (Quotidien)"  # « Courses (menu) » existe et n'est pas à nous
    assert r.liste("anniversaires") == "Anniversaires"
    elements = [rappels_apple.Element(f"courses:2026-10-12:{i}", f"article {i}", "note") for i in range(3)]
    assert r.ajouter("courses", elements) == 3
    assert r.ajouter("courses", elements) == 0  # jamais en double
    assert r.ajouter("courses", [*elements, rappels_apple.Element("courses:2026-10-12:x", "x")]) == 1
    apres = mac.etat_listes()
    assert {k: apres[k] for k in avant} == avant  # les listes des autres : mêmes noms, mêmes nombres
    assert mac.listes["Courses (menu)"][0]["titre"] == "lait d'un autre projet"
    assert apres["Courses (menu) (Quotidien)"] == 4 and r.nos_listes() == ["Courses (menu) (Quotidien)",
                                                                           "Anniversaires"]  # fmt: skip
    # Aucun script n'a jamais visé une liste qui n'est pas à nous, à part le test d'existence.
    for a in mac.appels:
        script, argv = a[2], a[4:]
        if script != rappels_apple._EXISTE:
            assert argv[0] in ("Courses (menu) (Quotidien)", "Anniversaires"), (script[:40], argv)


def test_retirer_seulement_nos_rappels(db: BaseDonnees) -> None:
    mac = FauxMac({"Courses (menu)": []})  # vide, mais pas à nous
    r = _rappels(db, mac)
    r.ajouter("courses", [rappels_apple.Element(f"courses:2026-10-05:{i}", f"a{i}") for i in range(2)])
    r.ajouter("courses", [rappels_apple.Element(f"courses:2026-10-12:{i}", f"b{i}") for i in range(3)])
    nom = r.liste("courses")
    assert nom == "Courses (menu) (Quotidien)"
    mac.listes[nom].append({"id": "a-toi", "titre": "ajouté à la main", "note": "", "date": None})
    assert r.retirer_semaines_passees("courses", date(2026, 10, 12)) == 2
    assert [x["titre"] for x in mac.listes[nom]] == ["b0", "b1", "b2", "ajouté à la main"]
    assert r.retirer("courses", "rien:") == 0
    assert r.compter(nom) == 4 and r.compter("n'existe pas") is None


def test_notre_liste_supprimee_a_la_main_est_recreee(db: BaseDonnees) -> None:
    mac = FauxMac()
    r = _rappels(db, mac)
    assert r.liste("anniversaires") == "Anniversaires"
    del mac.listes["Anniversaires"]
    assert r.liste("anniversaires", creer=False) is None
    assert r.liste("anniversaires") == "Anniversaires" and "Anniversaires" in mac.listes
    # Après une suppression à la main, ce qu'on y avait mis peut y revenir (les anciennes traces sont oubliées).
    e = rappels_apple.Element("anniv:x/2026-10-14", "x")
    assert r.ajouter("anniversaires", [e]) == 1
    del mac.listes["Anniversaires"]
    assert r.ajouter("anniversaires", [e]) == 0  # la base croit encore l'avoir mis…
    assert r.liste("anniversaires") == "Anniversaires"  # … jusqu'à ce que la liste soit recréée
    assert r.ajouter("anniversaires", [e]) == 1 and len(mac.listes["Anniversaires"]) == 1


def test_la_liste_suit_le_menu(db: BaseDonnees) -> None:
    """Un autre menu, un plat remplacé : la liste de la semaine change ; ce que tu as ajouté à la main reste."""
    from quotidien import cli

    mac = FauxMac()
    s = mac.systeme()
    mercredi = datetime(2026, 10, 14, 18, 0).timestamp()
    assert cli.main(["menu"], s, lambda: mercredi) == 0
    articles = len(mac.listes["Courses (menu)"])
    assert articles > 10
    mac.listes["Courses (menu)"].append({"id": "a-toi", "titre": "dentifrice", "note": "", "date": None})
    assert cli.main(["menu", "--regenerer"], s, lambda: mercredi) == 0
    from quotidien.repas import service

    menu = service.menu_de(db, date(2026, 10, 12))
    assert menu is not None
    liste = service.liste_de(db, config.defauts(), menu, charger_base())
    titres = sorted(x["titre"] for x in mac.listes["Courses (menu)"])
    assert titres == sorted([a.texte for a in liste.articles] + ["dentifrice"])
    assert cli.main(["menu", "remplacer", "jeudi"], s, lambda: mercredi) == 0
    assert "dentifrice" in [x["titre"] for x in mac.listes["Courses (menu)"]]


def test_anniversaires_passes_retires(db: BaseDonnees) -> None:
    mac = FauxMac()
    r = _rappels(db, mac)
    r.ajouter("anniversaires", [rappels_apple.Element("anniv:a/2026-10-01", "ancien"),
                                rappels_apple.Element("anniv:b/2026-10-13", "récent")])  # fmt: skip
    assert r.retirer_anniversaires_passes(date(2026, 10, 14)) == 1
    assert [x["titre"] for x in mac.listes["Anniversaires"]] == ["récent"]
    assert r.retirer_cles("anniversaires", []) == 0


def test_les_deux_noms_pris_rien_n_est_cree(db: BaseDonnees) -> None:
    mac = FauxMac({"Anniversaires": ["x"], "Anniversaires (Quotidien)": ["y"]})
    r = _rappels(db, mac)
    assert r.liste("anniversaires") is None and r.statut == "collision"
    assert r.ajouter("anniversaires", [rappels_apple.Element("anniv:x", "x")]) == 0
    assert mac.etat_listes() == {"Anniversaires": 1, "Anniversaires (Quotidien)": 1}


def test_modes_degrades(db: BaseDonnees) -> None:
    refuse = FauxMac(rappels_refuses=True)
    r = _rappels(db, refuse)
    assert r.liste("courses") is None and r.statut == "refuse"
    assert r.ajouter("courses", [rappels_apple.Element("courses:x:y", "y")]) == 0
    assert _rappels(db, FauxMac(), active=False).liste("courses") is None
    hors_mac = rappels_apple.Rappels(db, Systeme(lambda a, e, d: pytest.fail("rien ne doit être lancé"), mac=False),
                                     config.defauts().reglages)  # fmt: skip
    assert hors_mac.liste("courses") is None and hors_mac.statut == "indisponible"


def test_desinstallation_seulement_nos_listes(db: BaseDonnees) -> None:
    mac = FauxMac({k: list(v) for k, v in AUTRES.items()})
    r = _rappels(db, mac)
    r.ajouter("courses", [rappels_apple.Element("courses:2026-10-12:a", "a")])
    r.ajouter("anniversaires", [rappels_apple.Element("anniv:x/2026-10-14", "x")])
    assert sorted(r.supprimer_nos_listes()) == ["Anniversaires", "Courses (menu) (Quotidien)"]
    assert mac.etat_listes() == {k: len(v) for k, v in AUTRES.items()}
    assert r.nos_listes() == [] and db.lignes("SELECT * FROM rappels_apple") == []


def test_elements_courses_et_anniversaires(db: BaseDonnees) -> None:
    from quotidien.repas import service
    from quotidien.repas.base import charger

    base = charger()
    resultat = service.produire(db, config.defauts(), date(2026, 10, 12), base=base)
    elements = rappels_apple.elements_courses(resultat.liste, base)
    assert len(elements) == len(resultat.liste.articles)
    assert all(e.cle.startswith("courses:2026-10-12:") and e.titre for e in elements)
    lea = Personne("lea", "Léa", "Nom", DateNaissance(14, 10, 2001), "ami", "sobre")
    loin = Personne("loin", "Loin", "", DateNaissance(1, 1), None)
    t = datetime(2026, 10, 13, 19, 30).timestamp()
    (e,) = rappels_apple.elements_anniversaires(db, config.defauts().reglages, [lea, loin], date(2026, 10, 13), t)
    assert e.cle == "anniv:lea/2026-10-14" and e.titre == "🎂 Anniversaire de Léa (25 ans)"
    assert e.quand == datetime(2026, 10, 14, 9, 0) and e.note.startswith("Messages prêts")
    assert "1. " in e.note and "3. " in e.note and "Nom" not in e.note
