"""Le texte du frigo compris en local (§5, §10.3) : 200 formulations, absences, restes, quantités, fautes."""

from __future__ import annotations

import pytest

from quotidien.frigo import analyse_texte as at
from quotidien.repas.base import charger
from tests.frigo.donnees_formulations import FORMULATIONS

BASE = charger()


def _premier(texte: str) -> at.Element | None:
    elements = at.analyser(texte, BASE)
    return elements[0] if elements else None


def test_au_moins_200_formulations_comprises_a_95_pourcent() -> None:
    assert len(FORMULATIONS) >= 200
    echecs = []
    for texte, attendu, quantite in FORMULATIONS:
        e = _premier(texte)
        trouve = e.ingredient if e is not None else None
        if (trouve or "") != attendu or (attendu and e is not None and e.quantite != quantite):
            echecs.append((texte, attendu, quantite, trouve, e.quantite if e else None))
    taux = 1 - len(echecs) / len(FORMULATIONS)
    print(f"formulations comprises : {taux:.1%} ({len(FORMULATIONS) - len(echecs)}/{len(FORMULATIONS)})")
    assert taux >= 0.95, echecs


@pytest.mark.parametrize(
    ("texte", "absents"),
    [
        ("plus de lait", {"lait"}),
        ("pas de beurre", {"beurre"}),
        ("2 courgettes, plus de lait", {"lait"}),
        ("feta, plus de lait, 6 oeufs", {"lait"}),
        ("je n'ai plus de lait", {"lait"}),
        ("il n'y a plus de beurre", {"beurre"}),
        ("riz, plus d'oeufs", {"oeuf"}),
        ("2 courgettes et plus de beurre", {"beurre"}),
        ("courgettes plus feta", set()),
        ("du lait, ah non plus de lait", {"lait"}),
    ],
)
def test_absences(texte: str, absents: set[str]) -> None:
    elements = at.analyser(texte, BASE)
    assert {e.ingredient for e in elements if e.absent} == absents
    assert not absents & set(at.disponibles(elements))


def test_la_derniere_phrase_gagne_et_les_doublons_s_additionnent() -> None:
    e = at.analyser("plus de lait, 1 l de lait", BASE)
    assert [(x.ingredient, x.absent, x.quantite) for x in e] == [("lait", False, 1000)]
    e = at.analyser("2 courgettes, 3 courgettes", BASE)
    assert [(x.ingredient, x.quantite) for x in e] == [("courgette", 5)]
    e = at.analyser("2 courgettes, des courgettes", BASE)
    assert [(x.ingredient, x.quantite) for x in e] == [("courgette", None)]  # « assez »


def test_decoupage() -> None:
    assert at.decouper("1,5 kg de patates, 2 oeufs") == ["1,5 kg de patates", " 2 oeufs"]
    assert at.decouper("- courgettes\n- feta\n• riz") == ["courgettes", "feta", "riz"]
    assert at.decouper("pâtes / riz ; 1/2 citron") == ["pâtes ", " riz ", " 1/2 citron"]
    assert at.decouper("poulet avec crème et un oignon et demi") == ["poulet", "crème", "un oignon et demi"]
    assert at.decouper("courgettes + feta") == ["courgettes", "feta"]


def test_inconnu_jamais_invente_et_texte_long_borne() -> None:
    elements = at.analyser("bananes, kiwis, zzz, courgette", BASE)
    assert [e.ingredient for e in elements] == [None, None, None, "courgette"]
    assert [e.nom for e in elements[:3]] == ["bananes", "kiwis", "zzz"]
    assert at.analyser("", BASE) == [] and at.analyser(" , ; ", BASE) == []
    long = ", ".join(["courgette"] * 2000)
    assert len(at.analyser(long, BASE)) == 1  # 2 000 caractères lus au plus, doublons réunis


def test_faute_marquee_a_confirmer() -> None:
    e = _premier("courgete")
    assert e is not None and e.ingredient == "courgette" and e.incertain and e.confiance < 1
    e = _premier("courgette")
    assert e is not None and not e.incertain and e.confiance == 1


def test_distance_et_index() -> None:
    assert at.distance("tomate", "tomate") == 0
    assert at.distance("tomatte", "tomate") == 1
    assert at.distance("ognon", "oignon") == 1
    assert at.distance("cabillaud", "carotte") == 3  # borné à maximum + 1
    assert at.distance("ab", "abcdef") == 3
    assert at.distance("abcd", "abdc") == 1  # transposition
    index = at.index_noms(BASE)
    assert index is at.index_noms(BASE)  # calculé une fois
    assert index["courgette"] == "courgette" and index["patate"] == "pomme_de_terre"


def test_restes_et_quantites_particulieres() -> None:
    e = _premier("un reste de riz")
    assert e is not None and e.reste and e.quantite is None
    e = _premier("2 kilos de pommes")
    assert e is not None and e.ingredient == "pomme" and e.quantite == pytest.approx(2000 / 170)  # 170 g la pomme
    e = _premier("¼ de chou-fleur")
    assert e is not None and e.quantite == 0.25
