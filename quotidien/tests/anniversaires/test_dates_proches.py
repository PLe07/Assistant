"""Dates d'anniversaire (29 février, sans année, fuseau) et fiches de `proches.toml` reliées aux Contacts."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quotidien import config
from quotidien.anniversaires import contacts, dates, proches
from quotidien.anniversaires.dates import DateNaissance

AUJ = date(2026, 10, 7)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("1999-03-14", DateNaissance(14, 3, 1999)),
        ("14/03/1999", DateNaissance(14, 3, 1999)),
        ("14.03.1999", DateNaissance(14, 3, 1999)),
        ("14/03", DateNaissance(14, 3)),
        ("3/7", DateNaissance(3, 7)),
        ("03-14", DateNaissance(14, 3)),
        ("--03-14", DateNaissance(14, 3)),
        ("29/02", DateNaissance(29, 2)),
        ("2000-02-29", DateNaissance(29, 2, 2000)),
    ],
)
def test_lire(texte: str, attendu: DateNaissance) -> None:
    assert dates.lire(texte, AUJ) == attendu


@pytest.mark.parametrize("texte", ["", "demain", "31/02", "1999-02-29", "14/13", "00/03", "14/03/1850", "14/03/2030"])
def test_lire_refuse(texte: str) -> None:
    with pytest.raises(dates.DateInvalide):
        dates.lire(texte, AUJ)


def test_29_fevrier_et_age() -> None:
    n = DateNaissance(29, 2, 2004)
    assert dates.prochaine(n, date(2027, 1, 10)) == date(2027, 2, 28)
    assert dates.prochaine(n, date(2027, 1, 10), "01-03") == date(2027, 3, 1)
    assert dates.prochaine(n, date(2028, 1, 10)) == date(2028, 2, 29)
    assert dates.age(n, date(2027, 2, 28)) == 23  # fêté le 28 : il a 23 ans ce jour-là
    assert dates.age(n, date(2027, 3, 1)) == 23
    assert dates.age(n, date(2028, 2, 28)) == 23  # année bissextile : le 28, c'est la veille
    assert dates.age(n, date(2028, 2, 29)) == 24
    assert dates.age(DateNaissance(14, 3), date(2027, 3, 14)) is None  # sans année : pas d'âge
    assert dates.age(DateNaissance(14, 3, 2026), date(2026, 3, 14)) is None  # 0 an : absurde
    assert dates.prochaine(DateNaissance(7, 10), AUJ) == AUJ  # aujourd'hui compte
    assert dates.prochaine(DateNaissance(6, 10), AUJ) == date(2027, 10, 6)
    assert DateNaissance(1, 2, 2000).texte() == "01/02/2000" and DateNaissance(1, 2).texte() == "01/02"


def test_fuseau() -> None:
    # 23 h 30 à Paris le 6 octobre = 21 h 30 UTC : c'est encore le 6 à Paris, quel que soit le fuseau du Mac.
    t = datetime(2026, 10, 6, 21, 30, tzinfo=ZoneInfo("UTC")).timestamp()
    assert dates.aujourdhui(t, "Europe/Paris") == date(2026, 10, 6)
    assert dates.aujourdhui(t, "Asia/Tokyo") == date(2026, 10, 7)
    # Heure d'hiver (25 octobre 2026) : 9 h reste 9 h.
    neuf = dates.moment(date(2026, 10, 26), "09:00")
    assert datetime.fromtimestamp(neuf, ZoneInfo("Europe/Paris")).hour == 9


def _fiches(maison: Path, texte: str) -> proches.Lecture:
    config.dossier_support().mkdir(parents=True, exist_ok=True)
    proches.chemin().write_text(texte, encoding="utf-8")
    return proches.lire_fiches(aujourdhui=AUJ)


def test_fiches_bien_et_mal_remplies(maison: Path) -> None:
    assert proches.lire_fiches().personnes == []  # pas de fichier : rien, sans erreur
    lecture = _fiches(
        maison,
        """
[[personne]]
prenom = "Léa"
nom = "Exemple"
anniversaire = "14/03/2001"
relation = "Ami proche"
ton = "drôle"
notes = ["souvenir : voyage à Lisbonne", "adore le foot", "", "a", "b", "c", "d"]
telephone = "06 00 00 00 00"

[[personne]]
prenom = "Hugo"
anniversaire = "31/02"
relation = "voisin"
ton = "sarcastique"
notes = "aime la montagne"

[[personne]]
nom = "Sans-Prénom"

[[personne]]
prenom = "Zoé"
""",
    )
    lea, hugo, zoe = lecture.personnes
    assert (lea.prenom, lea.relation, lea.ton, lea.proche, lea.fiche) == ("Léa", "ami_proche", "drole", True, True)
    assert lea.naissance == DateNaissance(14, 3, 2001) and len(lea.notes) == proches.NOTES_MAX
    assert lea.telephone == "06 00 00 00 00" and lea.source == "proches"
    assert hugo.naissance.jour == 0 and hugo.relation is None and hugo.ton == "sobre"
    assert hugo.notes == ("aime la montagne",)
    assert zoe.naissance.jour == 0
    avert = " ".join(lecture.avertissements)
    assert "31/02 n'existe pas" in avert and "relation « voisin » inconnue" in avert
    assert "ton « sarcastique » inconnu" in avert and "personne n°3 : il manque le prénom" in avert
    assert lea.cle == proches.cle_de("proche", "Léa", "Exemple") and len(lea.cle) == 16


def test_fichier_illisible_ou_mal_forme(maison: Path) -> None:
    assert "illisible" in _fiches(maison, "[[personne]\nprenom=").avertissements[0]
    assert "[[personne]]" in _fiches(maison, 'personne = "Léa"\n').avertissements[0]


def _contact(identifiant: str, prenom: str, nom: str, jour: Any, mois: Any, annee: Any = None,
             telephones: list[tuple[str, str]] | None = None, surnom: str = "") -> dict[str, Any]:  # fmt: skip
    return {"identifiant": identifiant, "prenom": prenom, "nom": nom, "surnom": surnom, "jour": jour, "mois": mois,
            "annee": annee, "telephones": telephones or []}  # fmt: skip


def test_contacts_lus_et_cas_limites() -> None:
    bruts = [
        _contact("1", "Léa", "Exemple", 14, 3, 2001, [("_$!<Home>!$_", "05 00"), ("_$!<Mobile>!$_", "06 11")]),
        _contact("2", "Hugo", "Martin", 29, 2, contacts.INDEFINI, [("travail", "05 22")]),  # sans année
        _contact("3", "Sans", "Date", None, None),
        _contact("4", "Faux", "Jour", 31, 2, 1990),  # date impossible
        _contact("5", "", "Anonyme", 1, 1, 1990),  # pas de prénom
        _contact("6", "", "Surnommé", 2, 1, 1990, surnom="Bibi"),
        _contact("7", "Ancien", "Siècle", 3, 1, 1700),  # année absurde : jour gardé, sans âge
        _contact("8", "Tom", "Pouce", 14, 3, 2001),  # même jour que Léa
    ]
    lecture = contacts.lire(AUJ, lambda: ("ok", bruts))
    noms = [(p.prenom, p.naissance) for p in lecture.personnes]
    assert noms == [("Léa", DateNaissance(14, 3, 2001)), ("Hugo", DateNaissance(29, 2)), ("Bibi", DateNaissance(2, 1,
                    1990)), ("Ancien", DateNaissance(3, 1)), ("Tom", DateNaissance(14, 3, 2001))]  # fmt: skip
    assert lecture.sans_date == 1 and lecture.ignores == 2
    assert lecture.personnes[0].telephone == "06 11" and lecture.personnes[1].telephone == "05 22"
    assert all(p.source == "contacts" for p in lecture.personnes)
    # Contact supprimé : il n'est plus lu, il n'existe plus.
    assert len(contacts.lire(AUJ, lambda: ("ok", bruts[1:])).personnes) == 4
    for statut in ("refuse", "non_demande", "indisponible", "erreur"):
        assert contacts.lire(AUJ, lambda s=statut: (s, bruts)).personnes == []  # type: ignore[misc]
        assert statut in contacts.STATUTS


def test_fusion_fiches_et_contacts() -> None:
    lea_c = proches.Personne("c1", "Léa", "Exemple", DateNaissance(14, 3, 2001), telephone="06 11", source="contacts")
    lea2_c = proches.Personne("c2", "Léa", "Autre", DateNaissance(2, 5), source="contacts")
    hugo_c = proches.Personne("c3", "Hugo", "Martin", DateNaissance(29, 2), source="contacts")
    fiche_lea = proches.Personne("f1", "Léa", "Exemple", DateNaissance(0, 0), "couple", "tendre", ("adore le foot",),
                                 fiche=True)  # fmt: skip
    fiche_hugo = proches.Personne("f2", "hugo", "", DateNaissance(1, 3, 1998), "ami", "drole", fiche=True)
    fiche_seule = proches.Personne("f3", "Mamie", "", DateNaissance(5, 6, 1940), "famille", "tendre", fiche=True)
    fiche_sans_date = proches.Personne("f4", "Inconnu", "", DateNaissance(0, 0), "ami", fiche=True)
    toutes = proches.fusionner([lea_c, lea2_c, hugo_c], [fiche_lea, fiche_hugo, fiche_seule, fiche_sans_date])
    par_cle = {p.cle: p for p in toutes}
    assert par_cle["c1"].relation == "couple" and par_cle["c1"].ton == "tendre" and par_cle["c1"].fiche
    assert par_cle["c1"].naissance == DateNaissance(14, 3, 2001) and par_cle["c1"].telephone == "06 11"
    assert par_cle["c2"].relation is None and not par_cle["c2"].fiche  # l'autre Léa n'est pas reliée
    assert par_cle["c3"].relation == "ami" and par_cle["c3"].naissance == DateNaissance(1, 3, 1998)  # la fiche corrige
    assert "f3" in par_cle and "f4" not in par_cle and "f1" not in par_cle
    # Même prénom, sans nom dans la fiche, deux contacts : on ne devine pas.
    ambigue = proches.Personne("f5", "Léa", "", DateNaissance(0, 0), "famille", fiche=True)
    toutes = proches.fusionner([lea_c, lea2_c], [ambigue])
    assert all(p.relation is None for p in toutes)
