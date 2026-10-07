"""Le planificateur (§10.2) : contraintes dures vérifiées sur des milliers de profils et de semaines tirés au hasard.

Pour chaque menu : 0 violation d'allergie, de régime ou d'aliment détesté ; 0 recette lente un jour chargé ; 0 recette
répétée sur 14 jours ; restes mangés dans leur durée de conservation ; équipement respecté ; budget à +10 % (ou alerte
claire) ; au moins 70 % de saison (ou alerte) ; au moins un chaînage anti-gaspi quand c'est possible (ou alerte).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from quotidien import config
from quotidien.db import Base as BaseDonnees
from quotidien.repas import envies as module_envies
from quotidien.repas import planificateur as pl
from quotidien.repas.base import charger

BASE = charger()
LUNDI = date(2026, 10, 12)
MOTS_DETESTES = sorted(
    {i.nom for i in BASE.ingredients.values()}
    | {"poisson", "viande", "fromage", "coriandre", "champignons", "noix de pécan", "fruits de mer"}
)


def _reglages(**repas: Any) -> config.Reglages:
    r = config.defauts()
    semaine = repas.pop("semaine", None)
    r.profil["repas"].update(repas)
    if semaine is not None:
        r.profil["semaine"]["jours_charges"] = semaine
    return r


def verifier_menu(menu: pl.Menu, ctx: pl.Contexte, historique_dates: dict[str, date] | None = None) -> list[str]:
    """Toutes les contraintes dures ; renvoie la liste des violations (vide si tout va bien)."""
    profil, base = ctx.profil, ctx.base
    violations: list[str] = []
    cuisines = menu.cuisines()
    par_cle = {r.cle: r for r in menu.repas}
    vus: set[str] = set()
    for r in menu.repas:
        rec = base.recettes[r.recette]
        if set(rec.allergenes) & profil.allergies:
            violations.append(f"{r.cle} {rec.id} : allergène {set(rec.allergenes) & profil.allergies}")
        etiquette = pl.REGIME_ETIQUETTE.get(profil.regime)
        if etiquette and etiquette not in rec.etiquettes:
            violations.append(f"{r.cle} {rec.id} : régime {profil.regime}")
        if set(rec.ids()) & profil.interdits:
            violations.append(f"{r.cle} {rec.id} : aliment détesté {set(rec.ids()) & profil.interdits}")
        if rec.id in ctx.detestees and r.genre == "cuisine":
            violations.append(f"{r.cle} {rec.id} : noté 👎")
        if pl.refus(rec, profil) is not None:
            violations.append(f"{r.cle} {rec.id} : refusé ({pl.refus(rec, profil)})")
        if r.charge and r.genre == "cuisine" and not rec.rapide:
            violations.append(f"{r.cle} {rec.id} : {rec.temps_total_min} min un jour chargé")
        if r.genre == "cuisine":
            if rec.id in vus:
                violations.append(f"{rec.id} cuisiné deux fois dans la semaine")
            vus.add(rec.id)
            if rec.id in ctx.historique:
                violations.append(f"{rec.id} déjà cuisiné dans les 14 jours d'avant")
            if len(r.restes_pour) > (pl.RESTES_MAX if rec.batch else 1):
                violations.append(f"{rec.id} couvre trop de repas")
            for cible in r.restes_pour:
                ecart = (date.fromisoformat(cible[:10]) - r.date).days
                if not 0 <= ecart <= rec.conservation_jours:
                    violations.append(f"{rec.id} : reste mangé {ecart} j après (garde {rec.conservation_jours} j)")
                if cible in par_cle and par_cle[cible].reste_de != r.cle:
                    violations.append(f"{cible} : lien de reste incohérent")
            attendu = profil.portions * (1 + len(r.restes_pour))
            if abs(r.portions - attendu) > 1e-9:
                violations.append(f"{r.cle} : {r.portions} portions au lieu de {attendu}")
        else:
            source = par_cle.get(r.reste_de or "")
            if source is None and r.cle not in ctx.restes_imposes:
                violations.append(f"{r.cle} : reste sans plat d'origine")
            if source is not None and (source.recette != r.recette or r.cle not in source.restes_pour):
                violations.append(f"{r.cle} : reste qui ne correspond pas à son plat")
    if historique_dates:
        for r in cuisines:
            avant = historique_dates.get(r.recette)
            if avant is not None and 0 < (r.date - avant).days < 14:
                violations.append(f"{r.recette} répété {(r.date - avant).days} jours après")
    ev = pl.evaluer(ctx, menu.repas)
    if ev.cout > profil.budget * pl.TOLERANCE_BUDGET and not any("Budget" in a for a in menu.alertes):
        violations.append(f"budget dépassé ({ev.cout:.2f} € pour {profil.budget:.0f} €) sans alerte")
    if ev.part_saison < pl.SAISON_MIN and not any("saison" in a for a in menu.alertes):
        violations.append(f"saison {ev.part_saison:.0%} sans alerte")
    liens = sum(len(r.restes_pour) for r in cuisines)
    possible = any(r.conservation_jours >= 1 for r in pl.candidats_pour(ctx)) and len(pl.candidats_pour(ctx)) >= 2
    if possible and menu.repas and liens + len(ev.chainages) == 0 and not any("anti-gaspi" in a for a in menu.alertes):
        violations.append("aucun chaînage anti-gaspi alors que c'était possible")
    nb_attendus = 7 * (2 if profil.dejeuners else 1)
    if menu.repas and len(menu.repas) != nb_attendus:
        violations.append(f"{len(menu.repas)} repas au lieu de {nb_attendus}")
    return violations


def test_menu_par_defaut() -> None:
    profil, _ = pl.profil_depuis(config.defauts(), BASE)
    ctx = pl.Contexte(BASE, profil, LUNDI)
    menu = pl.generer(ctx, graine=7)
    assert verifier_menu(menu, ctx) == []
    assert len(menu.repas) == 7 and menu.alertes == []
    assert menu.cout <= 45 * 1.1 and menu.part_saison >= 0.7
    assert menu.chainages or any(r.restes_pour for r in menu.repas)
    # Les jours de cours (mercredi, jeudi, vendredi) : rapide ou restes.
    for r in menu.repas:
        if r.date.weekday() in (2, 3, 4):
            assert r.charge and (r.genre == "reste" or BASE.recettes[r.recette].rapide)


@settings(max_examples=1200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    regime=st.sampled_from(config.REGIMES),
    allergies=st.lists(st.sampled_from(config.ALLERGENES), max_size=4, unique=True),
    detestes=st.lists(st.sampled_from(MOTS_DETESTES), max_size=4, unique=True),
    charges=st.lists(st.sampled_from(config.JOURS), max_size=6, unique=True),
    budget=st.floats(15, 90),
    portions=st.integers(1, 4),
    equipement=st.lists(st.sampled_from(config.EQUIPEMENTS), max_size=5, unique=True),
    dejeuners=st.booleans(),
    decalage=st.integers(0, 730),
    historique=st.lists(st.sampled_from(sorted(BASE.recettes)), max_size=12, unique=True),
    pouces_bas=st.lists(st.sampled_from(sorted(BASE.recettes)), max_size=6, unique=True),
    envie=st.sampled_from(["", "envie de mexicain et de trucs légers", "pas de poisson", "réconfortant", "soupe"]),
    graine=st.integers(0, 10_000),
)
def test_proprietes_sur_des_milliers_de_profils(
    regime: str, allergies: list[str], detestes: list[str], charges: list[str], budget: float, portions: int,
    equipement: list[str], dejeuners: bool, decalage: int, historique: list[str], pouces_bas: list[str], envie: str,
    graine: int,
) -> None:  # fmt: skip
    reglages = _reglages(regime=regime, allergies=allergies, deteste=detestes, budget_semaine=budget,
                         portions=portions, equipement=equipement or ["plaques"], dejeuners=dejeuners,
                         semaine=charges)  # fmt: skip
    profil, _ = pl.profil_depuis(reglages, BASE)
    debut = date(2026, 1, 5) + timedelta(days=decalage)
    envies = [module_envies.analyser(envie)] if envie else []
    ctx = pl.Contexte(BASE, profil, debut, set(historique), set(pouces_bas), set(), {}, envies)
    menu = pl.generer(ctx, graine=graine, essais=25)
    violations = verifier_menu(menu, ctx)
    assert not violations, violations
    if not menu.repas:
        assert menu.alertes, "menu vide sans explication"


def test_semaines_qui_se_suivent_14_jours_et_restes_d_une_semaine_sur_l_autre(tmp_path: Path) -> None:
    """8 semaines d'affilée dans la base : aucune recette répétée sur 14 jours, d'une semaine à l'autre ; le plat du
    dimanche qui couvre le mercredi suivant est bien repris par le menu suivant."""
    db = BaseDonnees(tmp_path / "q.db")
    reglages = config.defauts()
    dates: dict[str, date] = {}
    reports = 0
    for k in range(8):
        debut = LUNDI + timedelta(days=7 * k)
        ctx, _ = pl.contexte(db, reglages, debut)
        menu = pl.planifier(db, reglages, debut, graine=k)
        assert verifier_menu(menu, ctx, dates) == []
        for r in menu.cuisines():
            dates[r.recette] = r.date
        imposes = pl.restes_imposes(db, debut)
        for cle, reste in imposes.items():
            dans_menu = next(x for x in menu.repas if x.cle == cle)
            assert dans_menu.genre == "reste" and dans_menu.recette == reste.recette
            reports += 1
    assert reports >= 1  # au moins une fois, le batch du dimanche a couvert la semaine suivante


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    regime=st.sampled_from(config.REGIMES),
    allergies=st.lists(st.sampled_from(config.ALLERGENES), max_size=3, unique=True),
    charges=st.lists(st.sampled_from(config.JOURS), max_size=5, unique=True),
    graine=st.integers(0, 10_000),
)
def test_proprietes_sur_quatre_semaines_d_affilee(
    tmp_path_factory: pytest.TempPathFactory, regime: str, allergies: list[str], charges: list[str], graine: int
) -> None:
    db = BaseDonnees(tmp_path_factory.mktemp("semaines") / "q.db")
    reglages = _reglages(regime=regime, allergies=allergies, semaine=charges)
    dates: dict[str, date] = {}
    for k in range(4):
        debut = date(2026, 3, 2) + timedelta(days=7 * k)
        ctx, _ = pl.contexte(db, reglages, debut)
        ctx.cache.clear()
        menu = pl.generer(ctx, graine=graine + k, essais=20)
        menu.alertes = menu.alertes
        pl.enregistrer(db, menu)
        assert verifier_menu(menu, ctx, dates) == []
        for r in menu.cuisines():
            dates[r.recette] = r.date


# --- Cas particuliers -------------------------------------------------------------------------------------------


def test_allergie_a_tout_menu_vide_et_alerte() -> None:
    reglages = _reglages(regime="vegan", allergies=list(config.ALLERGENES), deteste=["carotte", "oignon", "ail"])
    profil, _ = pl.profil_depuis(reglages, BASE)
    menu = pl.generer(pl.Contexte(BASE, profil, LUNDI), graine=1)
    assert menu.alertes
    assert all(not (set(BASE.recettes[r.recette].allergenes) & profil.allergies) for r in menu.repas)


def test_budget_impossible_alerte_claire() -> None:
    reglages = _reglages(budget_semaine=5)
    profil, _ = pl.profil_depuis(reglages, BASE)
    menu = pl.generer(pl.Contexte(BASE, profil, LUNDI), graine=1)
    assert any(a.startswith("Budget de 5 € impossible") for a in menu.alertes)


def test_aucune_recette_rapide_compatible() -> None:
    profil, _ = pl.profil_depuis(_reglages(semaine=list(config.JOURS)), BASE)
    rapides = {r.id for r in BASE.liste() if r.rapide}
    ctx = pl.Contexte(BASE, profil, LUNDI, historique=rapides)
    menu = pl.generer(ctx, graine=1)
    assert any("Aucune recette rapide" in a for a in menu.alertes)
    assert all(r.genre == "reste" or not r.charge for r in menu.repas)


def test_mots_detestes_prudents() -> None:
    tous, par_mot, inconnus = pl.ingredients_designes(BASE, ["Poulet", "noix de pécan", "poisson", "lactose",
                                                              "zzz inconnu", ""])  # fmt: skip
    assert {"poulet_filet", "poulet_cuisse"} <= par_mot["Poulet"]
    assert "noix" in par_mot["noix de pécan"]
    assert {"saumon", "thon", "sardine", "poisson_blanc"} <= par_mot["poisson"]
    assert {"lait", "beurre", "fromage_rape", "creme"} <= par_mot["lactose"]
    assert inconnus == ["zzz inconnu"]


def test_profil_aversion_inconnue_signalee() -> None:
    _, avert = pl.profil_depuis(_reglages(deteste=["xylophone"]), BASE)
    assert avert and "xylophone" in avert[0]


def test_equipement_airfryer_remplace_le_four() -> None:
    profil, _ = pl.profil_depuis(_reglages(equipement=["plaques", "airfryer"]), BASE)
    tian = BASE.recettes["tian-legumes-chevre"]
    quiche = BASE.recettes["quiche-lorraine"]
    assert pl.refus(tian, profil) is None
    assert pl.refus(quiche, profil) == "équipement : four"


def test_envies_orientent_le_menu() -> None:
    profil, _ = pl.profil_depuis(config.defauts(), BASE)
    mexicain = module_envies.analyser("envie de mexicain")
    ctx = pl.Contexte(BASE, profil, LUNDI, envies=[mexicain])
    menu = pl.generer(ctx, graine=3)
    assert any(BASE.recettes[r.recette].cuisine == "mexicaine" for r in menu.cuisines())
    assert any("ton envie" in x for r in menu.repas for x in r.raisons)
    sans = module_envies.analyser("pas de poisson cette semaine")
    ctx = pl.Contexte(BASE, profil, LUNDI, envies=[sans])
    menu = pl.generer(ctx, graine=3)
    assert not any(BASE.recettes[r.recette].proteine == "poisson" for r in menu.cuisines())


def test_frigo_utilise() -> None:
    profil, _ = pl.profil_depuis(config.defauts(), BASE)
    ctx = pl.Contexte(BASE, profil, LUNDI, frigo={"courgette": 2.0, "feta": 6.0})
    menu = pl.generer(ctx, graine=5)
    ids = {i for r in menu.cuisines() for i in BASE.recettes[r.recette].ids()}
    assert ids & {"courgette", "feta"}
    assert any("frigo" in x for r in menu.repas for x in r.raisons)


def test_dejeuners_restes_du_soir() -> None:
    profil, _ = pl.profil_depuis(_reglages(dejeuners=True), BASE)
    ctx = pl.Contexte(BASE, profil, LUNDI)
    menu = pl.generer(ctx, graine=11)
    assert len(menu.repas) == 14 and verifier_menu(menu, ctx) == []
    assert any(r.moment == "dejeuner" and r.genre == "reste" for r in menu.repas)


# --- Mémoire : notes, remplacer, envies -----------------------------------------------------------------------


def test_noter_et_le_menu_en_tient_compte(tmp_path: Path) -> None:
    db = BaseDonnees(tmp_path / "q.db")
    reglages = config.defauts()
    menu = pl.planifier(db, reglages, LUNDI, graine=1)
    jeudi = LUNDI + timedelta(days=3)
    recette = pl.noter(db, jeudi, -1, horloge=1.0)
    assert recette == menu.repas_du(jeudi).recette  # type: ignore[union-attr]
    adorees, detestees = pl.notes(db)
    assert recette in detestees and not adorees
    suivant = pl.planifier(db, reglages, LUNDI + timedelta(days=21), graine=2)
    assert recette not in {r.recette for r in suivant.repas}
    pl.noter(db, jeudi, 1, horloge=2.0)  # la dernière note compte
    adorees, detestees = pl.notes(db)
    assert recette in adorees and recette not in detestees
    with pytest.raises(pl.JourIntrouvable):
        pl.noter(db, date(2020, 1, 1), 1)


def test_remplacer_un_jour(tmp_path: Path) -> None:
    db = BaseDonnees(tmp_path / "q.db")
    reglages = config.defauts()
    menu = pl.planifier(db, reglages, LUNDI, graine=4)
    for jour in menu.jours():
        avant = menu.repas_du(jour)
        assert avant is not None
        nouveau_menu, nouveau = pl.remplacer(db, reglages, jour)
        assert nouveau.recette != avant.recette and nouveau.genre == "cuisine"
        ctx, _ = pl.contexte(db, reglages, LUNDI)
        ctx.restes_imposes = {}
        assert verifier_menu(nouveau_menu, ctx) == [], jour
        menu = nouveau_menu
    with pytest.raises(pl.JourIntrouvable):
        pl.remplacer(db, reglages, date(2020, 1, 1))
    with pytest.raises(pl.JourIntrouvable):
        pl.remplacer(db, reglages, LUNDI, "dejeuner")


def test_remplacer_une_source_suit_la_semaine_suivante(tmp_path: Path) -> None:
    db = BaseDonnees(tmp_path / "q.db")
    reglages = config.defauts()
    for graine in range(30):
        menu = pl.planifier(db, reglages, LUNDI, graine=graine)
        source = next((r for r in menu.cuisines() if any(c[:10] >= (LUNDI + timedelta(days=7)).isoformat()
                                                         for c in r.restes_pour)), None)  # fmt: skip
        if source is not None:
            break
    assert source is not None
    suivant = pl.planifier(db, reglages, LUNDI + timedelta(days=7), graine=1)
    _, nouveau = pl.remplacer(db, reglages, source.date)
    suivant = pl.menu_couvrant(db, LUNDI + timedelta(days=7))
    assert suivant is not None
    repris = [r for r in suivant.repas if r.reste_de == source.cle]
    assert repris and all(r.recette == nouveau.recette for r in repris)


def test_envies_en_attente_puis_consommees(tmp_path: Path) -> None:
    db = BaseDonnees(tmp_path / "q.db")
    pl.ajouter_envie(db, module_envies.analyser("envie d'indien"), 1.0)
    assert len(pl.envies_en_attente(db, LUNDI)) == 1
    with db.transaction() as cx:
        cx.execute("INSERT INTO envies(date, texte, etiquettes, semaine) VALUES (2, 'x', '{casse', '')")
    menu = pl.planifier(db, config.defauts(), LUNDI, graine=2)
    assert menu.envies == ["envie d'indien"]
    assert len(pl.envies_en_attente(db, LUNDI)) == 1  # gardée pour une regénération de la même semaine
    assert pl.envies_en_attente(db, LUNDI + timedelta(days=7)) == []


def test_frigo_actuel(tmp_path: Path) -> None:
    db = BaseDonnees(tmp_path / "q.db")
    with db.transaction() as cx:
        cx.execute("INSERT INTO frigo(ingredient, quantite, unite, ajoute_le) VALUES ('creme', 200, 'ml', 0)")
        cx.execute("INSERT INTO frigo(ingredient, quantite, unite, ajoute_le) VALUES ('inconnu', 1, 'p', 0)")
    frigo = pl.frigo_actuel(db, BASE, maintenant=2 * 86400)
    assert frigo == {"creme": 3.0}


def test_debut_semaine_suivante() -> None:
    assert pl.debut_semaine_suivante(date(2026, 10, 11)) == date(2026, 10, 12)  # dimanche → lundi
    assert pl.debut_semaine_suivante(date(2026, 10, 12)) == date(2026, 10, 19)  # lundi → lundi suivant


def test_menu_json_aller_retour(tmp_path: Path) -> None:
    profil, _ = pl.profil_depuis(config.defauts(), BASE)
    menu = pl.generer(pl.Contexte(BASE, profil, LUNDI), graine=9)
    copie = pl.Menu.depuis_json(menu.en_json())
    assert copie == menu
    assert copie.repas_du(LUNDI) is not None and copie.repas_du(LUNDI, "dejeuner") is None
    assert copie.jours()[0] == LUNDI and len(copie.jours()) == 7
