"""Validation de la base de recettes (§10.2) : schéma strict, quantité, allergènes, saisons, sécurité alimentaire.

Les attentes sur les allergènes sont écrites ici à la main, indépendamment de la table des ingrédients : une erreur
dans la table ne peut pas se valider elle-même.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter

import pytest

from quotidien import config
from quotidien.repas import unites
from quotidien.repas.base import charger

BASE = charger()
RECETTES = BASE.liste()
ING = BASE.ingredients

VIANDES = {"volaille", "boeuf", "porc", "agneau", "charcuterie"}
MER = {"poisson", "crustace", "mollusque"}

# Attendus écrits à la main (règlement INCO, annexe II), pour les ingrédients les plus courants.
ALLERGENES_ATTENDUS = {
    "pates": {"gluten"},
    "farine": {"gluten"},
    "semoule": {"gluten"},
    "boulgour": {"gluten"},
    "pain": {"gluten"},
    "tortilla": {"gluten"},
    "lasagne": {"gluten", "oeufs"},
    "nouilles_ble": {"gluten", "oeufs"},
    "nouilles_riz": set(),
    "riz": set(),
    "quinoa": set(),
    "polenta": set(),
    "lait": {"lait"},
    "beurre": {"lait"},
    "creme": {"lait"},
    "yaourt_grec": {"lait"},
    "fromage_rape": {"lait"},
    "parmesan": {"lait"},
    "feta": {"lait"},
    "oeuf": {"oeufs"},
    "mayonnaise": {"oeufs", "moutarde"},
    "moutarde": {"moutarde"},
    "sauce_soja": {"soja", "gluten"},
    "tofu": {"soja"},
    "miso": {"soja"},
    "crevette": {"crustaces"},
    "moules": {"mollusques"},
    "sauce_huitre": {"mollusques", "gluten", "soja"},
    "saumon": {"poissons"},
    "thon": {"poissons"},
    "nuoc_mam": {"poissons"},
    "cacahuete": {"arachides"},
    "beurre_cacahuete": {"arachides"},
    "noix": {"fruits_a_coque"},
    "amande": {"fruits_a_coque"},
    "tahini": {"sesame"},
    "graines_sesame": {"sesame"},
    "huile_sesame": {"sesame"},
    "celeri_rave": {"celeri"},
    "celeri_branche": {"celeri"},
    "vin_blanc": {"sulfites"},
    "vin_rouge": {"sulfites"},
    "abricot_sec": {"sulfites"},
    "pate_curry": {"crustaces"},
    "pommes_de_terre_absentes": set(),
}


def test_au_moins_220_recettes_et_identifiants_uniques() -> None:
    assert len(RECETTES) >= 220
    assert len({r.id for r in RECETTES}) == len(RECETTES)
    assert len({r.nom.lower() for r in RECETTES}) == len(RECETTES)


def test_les_json_correspondent_aux_sources() -> None:
    r = subprocess.run([sys.executable, str(config.racine_projet() / "outils" / "construire_recettes.py"),
                        "--verifier"], capture_output=True, text=True)  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr


def test_au_moins_60_rapides_et_50_vegetariennes() -> None:
    rapides = [r for r in RECETTES if r.rapide]
    assert len(rapides) >= 60
    assert all(r.temps_total_min <= 20 for r in rapides)
    assert all(r.rapide for r in RECETTES if r.temps_total_min <= 20)
    assert sum("vegetarien" in r.etiquettes for r in RECETTES) >= 50


def test_chaque_mois_au_moins_40_recettes_de_saison() -> None:
    for mois in range(1, 13):
        n = sum(1 for r in RECETTES if r.produits_saisonniers and mois in r.saisons)
        assert n >= 40, f"mois {mois} : {n} recettes de saison"


@pytest.mark.parametrize("recette", RECETTES, ids=lambda r: r.id)
def test_schema_strict(recette) -> None:  # type: ignore[no-untyped-def]
    r = recette
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", r.id)
    assert 1 <= r.portions <= 8
    assert len(r.etapes) >= 2 and all(len(e) >= 12 for e in r.etapes)
    assert len(r.ingredients) >= 2
    assert r.difficulte in ("facile", "moyen", "avance")
    assert r.temps_total_min == r.preparation_min + r.cuisson_min
    assert 0 < r.temps_total_min <= 240 and r.preparation_min <= 60
    assert r.source.startswith("originale")
    assert r.ustensiles, "ustensiles manquants"
    assert set(r.allergenes) <= set(config.ALLERGENES)
    assert r.etiquettes >= ({"au_four"} if "four" in r.equipement else {"sans_four"})


@pytest.mark.parametrize("recette", RECETTES, ids=lambda r: r.id)
def test_unites_metriques_et_quantites_plausibles(recette) -> None:  # type: ignore[no-untyped-def]
    for lg in recette.ingredients:
        ing = ING[lg.id]
        assert lg.unite in ("g", "ml", "p") and lg.unite == ing.unite
        assert lg.quantite > 0
        par_portion = lg.quantite / recette.portions
        if lg.unite == "g":
            assert par_portion <= 800, f"{lg.id} : {par_portion:.0f} g par portion"
        elif lg.unite == "ml":
            assert par_portion <= 600, f"{lg.id} : {par_portion:.0f} ml par portion"
        else:
            poids = (ing.poids_piece_g or 100) * par_portion
            assert poids <= 1200, f"{lg.id} : {par_portion} pièce(s) par portion"
    assert 0.25 <= recette.cout_portion_eur <= 8, recette.cout_portion_eur


@pytest.mark.parametrize("recette", RECETTES, ids=lambda r: r.id)
def test_allergenes_coherents_avec_les_ingredients(recette) -> None:  # type: ignore[no-untyped-def]
    attendus = set()
    for lg in recette.ingredients:
        attendus |= set(ING[lg.id].allergenes)
        attendus |= ALLERGENES_ATTENDUS.get(lg.id, set())
    assert set(recette.allergenes) == attendus


def test_table_des_allergenes_conforme_aux_attendus() -> None:
    for id_, attendus in ALLERGENES_ATTENDUS.items():
        if id_ in ING:
            assert attendus <= set(ING[id_].allergenes), id_
    # Toute la crèmerie contient du lait ; tout ce qui est à base de blé contient du gluten.
    for ing in ING.values():
        if ing.categorie in ("laitier", "fromage"):
            assert "lait" in ing.allergenes, ing.id
        if ing.categorie == "oeuf":
            assert "oeufs" in ing.allergenes
        if ing.categorie == "poisson":
            assert "poissons" in ing.allergenes
        if ing.categorie == "crustace":
            assert "crustaces" in ing.allergenes
        if ing.categorie == "mollusque":
            assert "mollusques" in ing.allergenes
        if ing.categorie in ("pain", "pate"):
            assert "gluten" in ing.allergenes, ing.id


@pytest.mark.parametrize("recette", RECETTES, ids=lambda r: r.id)
def test_regimes_coherents(recette) -> None:  # type: ignore[no-untyped-def]
    ings = [ING[i] for i in recette.ids()]
    if "vegetarien" in recette.etiquettes:
        assert not any(i.categorie in VIANDES | MER for i in ings)
        assert all(i.vegetarien for i in ings)
    if "vegan" in recette.etiquettes:
        assert not any(i.categorie in VIANDES | MER | {"oeuf", "laitier", "fromage"} for i in ings)
        assert "miel" not in recette.ids()
    if "sans_porc" in recette.etiquettes:
        assert not any(i.categorie in ("porc", "charcuterie") for i in ings)
    if recette.proteine in ("volaille", "boeuf", "porc", "agneau", "poisson", "fruits_de_mer"):
        assert "vegetarien" not in recette.etiquettes


SIGNES_CUISSON = ("à cœur", "rosé", "rosée", "jus clair", "jus doit être clair", "opaque", "lamelles", "s'ouvrent",
                  "ouvertes", "se défaire", "se détacher", "cuite au centre", "cuites au centre", "jus qui coule",
                  "bien chaudes", "décongelées au réfrigérateur")  # fmt: skip


@pytest.mark.parametrize("recette", RECETTES, ids=lambda r: r.id)
def test_securite_alimentaire(recette) -> None:  # type: ignore[no-untyped-def]
    ings = [ING[i] for i in recette.ids()]
    a_risque = [i for i in ings if i.categorie in ("volaille", "porc") or i.hache
                or (i.categorie in MER and i.id not in ("thon", "sardine"))]  # fmt: skip
    if a_risque:
        assert recette.securite, "mention de sécurité absente"
        texte = " ".join([*recette.etapes, *(lg.note for lg in recette.ingredients)]).lower()
        assert any(s in texte for s in SIGNES_CUISSON), f"aucune étape ne dit quand {a_risque[0].nom} est cuit"
    if any(i.categorie == "volaille" for i in ings):
        assert any("volaille" in s for s in recette.securite)
    if any(i.hache for i in ings):
        assert any("hachée" in s for s in recette.securite)
    assert 0 <= recette.conservation_jours <= 3
    if any(i.categorie in MER for i in ings) or any(i.hache for i in ings):
        assert recette.conservation_jours <= 2
    if any(i.trempage_heures for i in ings):
        assert any("tremper" in s for s in recette.securite)
        assert any("tremp" in e.lower() for e in recette.etapes)
    assert recette.conservation


@pytest.mark.parametrize("recette", RECETTES, ids=lambda r: r.id)
def test_saisons_justes(recette) -> None:  # type: ignore[no-untyped-def]
    for mois in recette.saisons:
        for id_ in recette.produits_saisonniers:
            assert ING[id_].de_saison(mois), f"{id_} n'est pas de saison en {mois}"
    for mois in set(range(1, 13)) - set(recette.saisons):
        assert any(not ING[i].de_saison(mois) for i in recette.produits_saisonniers)


@pytest.mark.parametrize("recette", RECETTES, ids=lambda r: r.id)
def test_tutoiement_et_francais(recette) -> None:  # type: ignore[no-untyped-def]
    texte = " ".join(recette.etapes)
    assert not re.search(r"\b(vous|votre|vos)\b", texte, re.IGNORECASE)
    assert "  " not in texte


def test_calendrier_des_saisons() -> None:
    assert set(BASE.calendrier) == {str(m) for m in range(1, 13)}
    assert "tomate" in BASE.calendrier["7"]["legumes"] and "tomate" not in BASE.calendrier["1"]["legumes"]
    assert "poireau" in BASE.calendrier["1"]["legumes"] and "courgette" not in BASE.calendrier["1"]["legumes"]
    assert "pomme" in BASE.calendrier["10"]["fruits"]
    assert all(len(BASE.calendrier[str(m)]["legumes"]) >= 6 for m in range(1, 13))


def test_rayons_et_substitutions() -> None:
    assert {i.rayon for i in ING.values()} <= set(BASE.rayons)
    assert sorted(r["ordre"] for r in BASE.rayons.values()) == list(range(1, len(BASE.rayons) + 1))
    assert BASE.substitutions["creme"][0]["par"] == "yaourt_grec"
    assert "yaourt" in BASE.substitutions["creme"][0]["conseil"]
    for manquant, liste in BASE.substitutions.items():
        assert manquant in ING and all(s["par"] in ING for s in liste)


def test_diversite() -> None:
    proteines = Counter(r.proteine for r in RECETTES)
    assert all(proteines[p] >= 5 for p in ("volaille", "boeuf", "porc", "poisson", "oeuf", "fromage", "legumineuse"))
    assert len({r.cuisine for r in RECETTES}) >= 15
    assert sum(r.batch for r in RECETTES) >= 30


def test_placard_par_defaut_existe() -> None:
    for id_ in config.DEFAUT_PROFIL["repas"]["placard"]:
        assert id_ in ING and ING[id_].placard, id_


# --- Unités ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "q,de,vers,poids,attendu",
    [(1.5, "kg", "g", None, 1500), (250, "g", "kg", None, 0.25), (75, "cl", "ml", None, 750), (1, "l", "cl", None, 100),
     (3, "p", "g", 120, 360), (300, "g", "p", 150, 2), (200, "ml", "g", None, 200), (2, "pièces", "p", None, 2)],
)  # fmt: skip
def test_convertir(q: float, de: str, vers: str, poids: float | None, attendu: float) -> None:
    assert unites.convertir(q, de, vers, poids) == pytest.approx(attendu)


@pytest.mark.parametrize("de,vers", [("p", "g"), ("p", "ml"), ("g", "boite"), ("tasse", "g")])
def test_convertir_impossible(de: str, vers: str) -> None:
    with pytest.raises(unites.UniteIncompatible):
        unites.convertir(1, de, vers, None)


@pytest.mark.parametrize(
    "q,u,attendu",
    [(1500, "g", "1,5 kg"), (500, "g", "500 g"), (2.5, "g", "2,5 g"), (1250, "g", "1,25 kg"), (750, "ml", "75 cl"),
     (1000, "ml", "1 l"), (15, "ml", "15 ml"), (125, "ml", "125 ml"), (2, "p", "2"), (0.5, "p", "½"),
     (1.5, "p", "1 ½"), (0.25, "p", "¼"), (2.7, "p", "2,7"), (0.66, "p", "⅔"), (0, "p", "0")],
)  # fmt: skip
def test_afficher(q: float, u: str, attendu: str) -> None:
    assert unites.afficher(q, u) == attendu
