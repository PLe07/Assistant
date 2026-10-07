"""Du frigo aux recettes (§5, §10.3) : 60 frigos réalistes, au moins une recette pertinente dans les 3 premières
dans 95 % des cas, et jamais une recette interdite par le profil (régime, allergies, aliments refusés, équipement)."""

from __future__ import annotations

import dataclasses
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from quotidien import config
from quotidien.frigo import analyse_texte as at
from quotidien.frigo import correspondance as co
from quotidien.repas import planificateur as pl
from quotidien.repas.base import charger
from tests.frigo.donnees_frigos import FRIGOS

BASE = charger()
PROFIL, _ = pl.profil_depuis(config.defauts(), BASE)
FRAIS = sorted(i for i, ing in BASE.ingredients.items() if not ing.placard)


def _profil(**kw: Any) -> pl.Profil:
    return dataclasses.replace(PROFIL, **{k: frozenset(v) if isinstance(v, set) else v for k, v in kw.items()})


def test_60_frigos_95_pourcent_pertinents_et_jamais_interdits() -> None:
    assert len(FRIGOS) >= 60
    rates, violations = [], []
    for texte, cles, kw in FRIGOS:
        profil = _profil(**kw)
        frigo = at.disponibles(at.analyser(texte, BASE))
        assert cles <= set(frigo) | {"poulet_filet"}, (texte, cles - set(frigo))  # le texte est bien compris
        props = co.proposer(BASE, profil, frigo)
        assert len(props) <= 3
        violations += [(texte, p.recette.id) for p in props if pl.refus(p.recette, profil) is not None]
        if not any(p.servis & cles for p in props):
            rates.append((texte, [p.recette.id for p in props]))
    taux = 1 - len(rates) / len(FRIGOS)
    print(f"frigos avec une recette pertinente dans les 3 premières : {taux:.0%} ({len(FRIGOS) - len(rates)}/60)")
    assert not violations
    assert taux >= 0.95, rates


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    contenu=st.lists(st.sampled_from(FRAIS), min_size=1, max_size=8, unique=True),
    regime=st.sampled_from(["omnivore", "sans_porc", "pescetarien", "vegetarien", "vegan"]),
    allergies=st.sets(st.sampled_from(["gluten", "lait", "oeufs", "arachides", "poissons", "crustaces", "soja"])),
    interdits=st.sets(st.sampled_from(FRAIS), max_size=3),
    sans_four=st.booleans(),
)
def test_propriete_jamais_interdit_au_plus_2_manquants(contenu: list[str], regime: str, allergies: set[str],
                                                       interdits: set[str], sans_four: bool) -> None:  # fmt: skip
    equipement = {"plaques", "micro-ondes"} if sans_four else {"four", "plaques", "micro-ondes"}
    profil = _profil(regime=regime, allergies=allergies, interdits=interdits, equipement=equipement)
    frigo = {i: at.Element(i, i, i, None, None) for i in contenu}
    props = co.proposer(BASE, profil, frigo, detestees={"croque-monsieur"})
    assert len(props) <= 3
    assert len({p.recette.id for p in props}) == len(props)
    assert [p.score for p in props] == sorted((p.score for p in props), reverse=True)
    for p in props:
        assert pl.refus(p.recette, profil) is None
        assert p.recette.id != "croque-monsieur"
        assert len(p.manquants) <= co.MANQUANTS_MAX
        assert set(p.utilises) <= set(frigo)
        assert not set(p.manquants) & set(frigo)


def test_frigo_vide_ou_seulement_le_placard() -> None:
    assert co.proposer(BASE, PROFIL, {}) == []
    sel = {"sel": at.Element("sel", "sel", "sel", None, None)}
    assert co.proposer(BASE, PROFIL, sel) == []  # le placard seul ne propose rien (pas « utilisé »)


def test_adaptations_facultatifs_et_quantites_justes() -> None:
    frigo = at.disponibles(at.analyser("200 g de saumon, 2 poireaux, 20 cl de crème, citron", BASE))
    props = {p.recette.id: p for p in co.proposer(BASE, PROFIL, frigo, n=10)}
    papillote = props["papillote-poisson-poireaux"]
    assert [a.par for a in papillote.adaptations] == ["saumon", "huile_olive"]  # le beurre : l'huile du placard
    assert papillote.adaptations[0].conseil.startswith("Pas de poisson blanc ?") and "saumon" in papillote.servis
    # Un seul œuf pour une recette qui en veut beaucoup : « un peu juste ».
    frigo = at.disponibles(at.analyser("1 oeuf, 4 tomates, 1 oignon", BASE))
    r = BASE.recettes["chakchouka"]
    p = co.evaluer(BASE, r, _profil(portions=4), frigo)
    assert p is not None and "oeuf" in p.juste
    # Les herbes et l'accompagnement manquants ne bloquent pas la recette.
    frigo = at.disponibles(at.analyser("pois chiches, épinards, tomates", BASE))
    toutes = co.proposer(BASE, PROFIL, frigo, n=20)
    assert any(p.sans for p in toutes)
    assert all(not set(p.sans) & set(p.manquants) for p in toutes)


def test_il_manque_la_viande_passe_apres() -> None:
    frigo = at.disponibles(at.analyser("oignons, citron, riz", BASE))
    props = co.proposer(BASE, PROFIL, frigo, n=10)
    p = next(p for p in props if p.recette.id == "poulet-yassa")
    assert p.manquants == ["poulet_cuisse"] and p.temps == p.recette.temps_total_min
    # Même recette, même frigo : il manque la viande → 12 points de moins qu'un autre manquant du même poids.
    profil = PROFIL
    r = BASE.recettes["poulet-yassa"]
    avec_poulet = co.evaluer(
        BASE, r, profil, {**frigo, "poulet_cuisse": at.Element("", "poulet_cuisse", "", None, None)}
    )
    assert avec_poulet is not None and avec_poulet.score > p.score + 15
