"""La liste de courses (§10.2) : additions et conversions exactes, soustraction du frigo et du placard, arrondi aux
formats vendus, rangement par rayon, et aucun ingrédient perdu (tout ingrédient du menu est soit dans la liste, soit
marqué « déjà là »)."""

from __future__ import annotations

import itertools
import math
from datetime import date, timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from quotidien import config
from quotidien.repas import courses as mc
from quotidien.repas import planificateur as pl
from quotidien.repas import unites
from quotidien.repas.base import Format, charger

BASE = charger()
LUNDI = date(2026, 10, 12)


def _repas(jour: date, recette: str, portions: float = 1.0) -> pl.Repas:
    return pl.Repas(jour.isoformat(), "diner", "cuisine", recette, portions)


def _menu(*repas: pl.Repas, debut: date = LUNDI) -> pl.Menu:
    return pl.Menu(debut.isoformat(), list(repas), portions=1)


def _recette_avec(id_ingredient: str, sans: tuple[str, ...] = ()) -> str:
    for r in BASE.liste():
        if id_ingredient in r.ids() and not set(sans) & set(r.ids()):
            return r.id
    raise AssertionError(f"aucune recette avec {id_ingredient}")


# --- Unités ---------------------------------------------------------------------------------------------------------


def test_unites_conversions_et_affichage() -> None:
    assert unites.convertir(1.5, "kg", "g") == 1500
    assert unites.convertir(75, "cl", "ml") == 750
    assert unites.convertir(2, "p", "g", 55) == 110
    assert unites.convertir(110, "g", "p", 55) == 2
    assert unites.convertir(200, "ml", "g") == 200
    with pytest.raises(unites.UniteIncompatible):
        unites.convertir(1, "p", "g")  # pièce sans poids
    with pytest.raises(unites.UniteIncompatible):
        unites.convertir(1, "p", "ml", 55)
    with pytest.raises(unites.UniteIncompatible):
        unites.base("tasse")
    assert unites.base("pièces") == ("p", 1.0) and unites.base("") == ("p", 1.0)
    assert unites.afficher(1500, "g") == "1,5 kg"
    assert unites.afficher(500, "g") == "500 g"
    assert unites.afficher(2.5, "g") == "2,5 g"
    assert unites.afficher(750, "ml") == "75 cl"
    assert unites.afficher(1250, "ml") == "1,25 l"
    assert unites.afficher(15, "ml") == "15 ml"
    assert unites.afficher(125, "ml") == "125 ml"
    assert unites.afficher(1.5, "p") == "1 ½"
    assert unites.fraction(0.5) == "½" and unites.fraction(0.25) == "¼" and unites.fraction(2) == "2"
    assert unites.fraction(1 / 3) == "⅓" and unites.fraction(0) == "0" and unites.fraction(1.3) == "1,3"


# --- Le meilleur achat ----------------------------------------------------------------------------------------------


def test_meilleur_achat_formats_vendus() -> None:
    oeufs = BASE.ingredients["oeuf"].formats  # boîte de 6 à 1,99 €, de 12 à 3,69 €
    achats, cout = mc.meilleur_achat(4, oeufs)
    assert [(f.libelle, n) for f, n in achats] == [("boîte de 6", 1)] and cout == 1.99
    achats, cout = mc.meilleur_achat(8, oeufs)
    assert [(f.libelle, n) for f, n in achats] == [("boîte de 12", 1)] and cout == 3.69
    achats, cout = mc.meilleur_achat(13, oeufs)
    assert sum(f.quantite * n for f, n in achats) >= 13 and cout == pytest.approx(3.69 + 1.99)
    assert mc.meilleur_achat(0, oeufs) == ([], 0.0)
    pates = BASE.ingredients["pates"].formats
    achats, _ = mc.meilleur_achat(700, pates)
    assert achats == [(pates[0], 2)]  # 2 paquets de 500 g


@settings(max_examples=400, deadline=None)
@given(
    besoin=st.floats(0.1, 5000),
    formats=st.lists(
        st.tuples(st.floats(1, 1000), st.floats(0.1, 20)), min_size=1, max_size=3, unique_by=lambda x: x[0]
    ),
)
def test_meilleur_achat_couvre_toujours_au_moindre_cout(besoin: float, formats: list[tuple[float, float]]) -> None:
    fmts = tuple(Format(q, p, f"{q:g}") for q, p in formats)
    achats, cout = mc.meilleur_achat(besoin, fmts)
    assert sum(f.quantite * n for f, n in achats) >= besoin - 1e-6
    assert cout == pytest.approx(sum(f.prix * n for f, n in achats), abs=0.01)
    # Aucune combinaison d'au plus deux formats n'est moins chère.
    meilleur = math.inf
    for a, b in itertools.product(fmts, repeat=2):
        for na in range(math.ceil(besoin / a.quantite) + 1):
            reste = besoin - na * a.quantite
            nb = 0 if reste <= 1e-9 else math.ceil(reste / b.quantite - 1e-9)
            meilleur = min(meilleur, na * a.prix + nb * b.prix)
    assert cout <= meilleur + 0.011


# --- La liste -------------------------------------------------------------------------------------------------------


def test_additions_conversions_et_texte() -> None:
    r1, r2 = _recette_avec("courgette"), None
    r2 = next(r.id for r in BASE.liste() if "courgette" in r.ids() and r.id != r1)
    menu = _menu(_repas(LUNDI, r1, 2), _repas(LUNDI + timedelta(days=2), r2))
    besoins = mc.besoins(menu, BASE)
    attendu = sum(
        lg.quantite * (rp.portions / BASE.recettes[rp.recette].portions)
        for rp in menu.cuisines()
        for lg in BASE.recettes[rp.recette].ingredients
        if lg.id == "courgette"
    )
    assert sum(q for q, _, _ in besoins["courgette"]) == pytest.approx(attendu)
    liste = mc.construire(menu, BASE, set(), {}, jour_courses=0)
    courgettes = next(a for a in liste.articles if a.ingredient == "courgette")
    assert courgettes.besoin == pytest.approx(attendu)
    n = math.ceil(attendu - 1e-9)
    assert courgettes.texte == f"🥬 {'Courgettes' if n > 1 else 'Courgette'} ×{n}"
    assert courgettes.recettes == sorted({r1, r2}) and courgettes.cout == pytest.approx(0.6 * n)
    assert liste.total == pytest.approx(sum(a.cout for a in liste.articles))
    ordres = [BASE.rayons[a.rayon]["ordre"] for a in liste.articles]
    assert ordres == sorted(ordres)  # rangée par rayon
    assert [r for r, _ in liste.par_rayon()] == list(dict.fromkeys(a.rayon for a in liste.articles))


def test_placard_et_frigo_retires() -> None:
    rec = next(
        r.id for r in BASE.liste() if sum(lg.quantite for lg in r.ingredients if lg.id == "oeuf") >= 2 * r.portions
    )
    recette = BASE.recettes[rec]
    menu = _menu(_repas(LUNDI, rec, recette.portions))  # à l'échelle de la recette : les quantités sont celles écrites
    q_oeufs = sum(lg.quantite for lg in recette.ingredients if lg.id == "oeuf")
    placard = {"sel", "poivre", "huile_olive"}
    # Le frigo a déjà des œufs, mais pas assez : il en manque.
    liste = mc.construire(menu, BASE, placard, {"oeuf": (q_oeufs - 1, "p")}, jour_courses=0)
    oeufs = next(a for a in liste.articles if a.ingredient == "oeuf")
    assert oeufs.besoin == pytest.approx(1) and oeufs.besoin_total == pytest.approx(q_oeufs)
    assert oeufs.texte == "🧀 Œuf — boîte de 6" or oeufs.texte.endswith("boîte de 6")
    # Assez d'œufs dans le frigo (en grammes, convertis) : déjà là.
    liste = mc.construire(menu, BASE, placard, {"oeuf": (q_oeufs * 55, "g")}, jour_courses=0)
    assert not any(a.ingredient == "oeuf" for a in liste.articles)
    assert any(d.ingredient == "oeuf" and d.raison == "frigo" for d in liste.deja_la)
    # Quantité inconnue : « assez » ; unité incompatible : comme s'il n'y en avait pas.
    liste = mc.construire(menu, BASE, placard, {"oeuf": (None, None)}, jour_courses=0)
    assert any(d.ingredient == "oeuf" for d in liste.deja_la)
    liste = mc.construire(menu, BASE, placard, {"oeuf": (2, "ml")}, jour_courses=0)
    assert next(a for a in liste.articles if a.ingredient == "oeuf").besoin == pytest.approx(q_oeufs)
    for id_ in placard & set(BASE.recettes[rec].ids()):
        assert any(d.ingredient == id_ and d.raison == "placard" for d in liste.deja_la)


def test_congelation_et_besoin_avant_les_courses() -> None:
    rec = _recette_avec("poulet_filet")
    vendredi = LUNDI + timedelta(days=4)
    menu = _menu(_repas(LUNDI, rec), _repas(vendredi, next(r.id for r in BASE.liste()
                                                            if "poulet_filet" in r.ids() and r.id != rec)))  # fmt: skip
    liste = mc.construire(menu, BASE, set(), {}, jour_courses=0)  # courses le lundi
    poulet = next(a for a in liste.articles if a.ingredient == "poulet_filet")
    assert poulet.a_congeler == "congèle la part de vendredi en rentrant"
    # Courses le mercredi : le poulet du lundi est nécessaire avant les courses.
    liste = mc.construire(menu, BASE, set(), {}, jour_courses=2)
    assert liste.jour_courses == "mercredi"
    assert len(liste.notes) == 1 and liste.notes[0].startswith(
        "Avant tes courses du mercredi, il te faut déjà (dès lundi)"
    )
    assert "filet de poulet" in liste.notes[0]
    menu = _menu(_repas(vendredi, rec))
    poulet = next(a for a in mc.construire(menu, BASE, set(), {}, 0).articles if a.ingredient == "poulet_filet")
    assert poulet.a_congeler == "à congeler en rentrant (pour vendredi)"
    rappels = mc.textes_rappels(mc.construire(menu, BASE, set(), {}, 0))
    p = next(x for x in rappels if x["cle"].endswith(":poulet_filet"))
    assert p["titre"] == "🥩 Filet de poulet — barquette de 400 g" and "congeler" in p["note"]
    assert all(x["cle"].startswith(f"courses:{LUNDI.isoformat()}:") for x in rappels)


def test_jour_des_courses() -> None:
    assert mc.jour_des_courses(LUNDI, 0) == LUNDI
    assert mc.jour_des_courses(LUNDI, 5) == LUNDI + timedelta(days=5)
    assert mc.jour_des_courses(LUNDI + timedelta(days=2), 0) == LUNDI + timedelta(days=7)


def test_frigo_quantites(tmp_path: object) -> None:
    from pathlib import Path

    from quotidien.db import Base as BaseDonnees

    db = BaseDonnees(Path(str(tmp_path)) / "q.db")
    with db.transaction() as cx:
        cx.execute("INSERT INTO frigo(ingredient, quantite, unite, ajoute_le) VALUES ('creme', 200, 'ml', 0)")
        cx.execute("INSERT INTO frigo(ingredient, quantite, unite, ajoute_le) VALUES ('feta', NULL, NULL, 0)")
    assert mc.frigo_quantites(db) == {"creme": (200.0, "ml"), "feta": (None, None)}


@settings(max_examples=250, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    graine=st.integers(0, 10_000),
    portions=st.integers(1, 4),
    dejeuners=st.booleans(),
    jour_courses=st.integers(0, 6),
    frigo=st.dictionaries(
        st.sampled_from(sorted(BASE.ingredients)),
        st.one_of(st.none(), st.floats(0, 2000)),
        max_size=6,
    ),
    decalage=st.integers(0, 365),
)
def test_aucun_ingredient_perdu(graine: int, portions: int, dejeuners: bool, jour_courses: int,
                                frigo: dict[str, float | None], decalage: int) -> None:  # fmt: skip
    reglages = config.defauts()
    reglages.profil["repas"].update(portions=portions, dejeuners=dejeuners)
    profil, _ = pl.profil_depuis(reglages, BASE)
    debut = date(2026, 1, 5) + timedelta(days=7 * (decalage // 7))
    menu = pl.generer(pl.Contexte(BASE, profil, debut), graine=graine, essais=6)
    frigo_unites = {i: (q, BASE.ingredients[i].unite if q is not None else None) for i, q in frigo.items()}
    liste = mc.construire(menu, BASE, profil.placard, frigo_unites, jour_courses)
    besoins = {i: sum(q for q, _, _ in u) for i, u in mc.besoins(menu, BASE).items()}
    dans_liste = {a.ingredient: a for a in liste.articles}
    deja = {d.ingredient for d in liste.deja_la}
    assert set(besoins) == set(dans_liste) | deja and not set(dans_liste) & deja
    for i, a in dans_liste.items():
        q = frigo_unites.get(i, (0.0, None))[0] or 0.0
        assert a.besoin == pytest.approx(besoins[i] - q)
        achete = sum(f.quantite * n for f, n in a.achats)
        assert achete >= a.besoin - 1e-6 and a.cout > 0  # arrondi aux formats vendus, jamais en dessous
    for i in deja:
        assert i in profil.placard or frigo_unites[i][0] is None or frigo_unites[i][0] >= besoins[i] - 1e-9
    assert liste.total == pytest.approx(sum(a.cout for a in liste.articles), abs=0.01)
