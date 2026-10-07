"""Envies en texte libre (local d'abord, l'IA seulement si rien n'est reconnu), rappels de la veille, page du menu."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from quotidien import config, ia
from quotidien.db import Base as BaseDonnees
from quotidien.html import e, ecrire_atomique, page
from quotidien.repas import courses as mc
from quotidien.repas import envies, rappels_veille
from quotidien.repas import page as module_page
from quotidien.repas import planificateur as pl
from quotidien.repas.base import charger

BASE = charger()
LUNDI = date(2026, 10, 12)


# --- Envies -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texte", "voulus", "exclus"),
    [
        ("envie de mexicain et de trucs légers", {"cuisine:mexicaine", "etiquette:leger"}, set()),
        ("Pas de poisson cette semaine !", set(), {"proteine:poisson"}),
        ("marre des pâtes, envie de riz", {"feculent:riz"}, {"feculent:pates"}),
        ("des pommes de terre au four", {"feculent:pomme_de_terre", "etiquette:au_four"}, set()),
        ("quelque chose de réconfortant, sans fromage", {"etiquette:reconfortant"}, {"proteine:fromage"}),
        ("Asiatique", {f"cuisine:{c}" for c in envies.CUISINES_ASIE}, set()),
        ("flemme de cuisiner", {"etiquette:rapide"}, set()),
        ("des noix", set(), set()),  # « noix » n'est pas un pluriel : pas de faux mot reconnu
        ("plus de pâtes, sans viande", {"etiquette:vegetarien"}, {"feculent:pates"}),
        ("je veux du poisson mais pas de riz", {"proteine:poisson"}, {"feculent:riz"}),
        ("", set(), set()),
    ],
)
def test_analyse_locale(texte: str, voulus: set[str], exclus: set[str]) -> None:
    c = envies.analyser(texte)
    assert (c.voulus, c.exclus) == (voulus, exclus)
    assert envies.Criteres.depuis_json(c.en_json()) == c


def test_normaliser_et_singulier() -> None:
    assert envies.normaliser("Crème brûlée, l’œuf !") == "creme brulee l oeuf"
    assert envies._singulier("poireaux") == "poireau" and envies._singulier("noix") == "noix"
    assert envies._singulier("tomates") == "tomate" and envies._singulier("bus") == "bus"
    assert envies._au_singulier("pommes de terre") == "pomme de terre"


def test_correspond() -> None:
    rec = next(r for r in BASE.liste() if r.cuisine == "mexicaine")
    assert envies.correspond("cuisine:mexicaine", rec) and not envies.correspond("cuisine:thai", rec)
    assert envies.correspond(f"proteine:{rec.proteine}", rec) and envies.correspond(f"feculent:{rec.feculent}", rec)
    assert envies.correspond(f"etiquette:{sorted(rec.etiquettes)[0]}", rec)
    assert not envies.correspond("inconnu:x", rec)


class FauxClient:
    nom = "imitation"

    def __init__(self, textes: list[str]) -> None:
        self.textes, self.demandes = textes, []

    def envoyer(self, systeme: str, contenu: ia.Contenu, max_jetons: int, delai: float) -> ia.ReponseBrute:
        self.demandes.append((systeme, contenu))
        return ia.ReponseBrute(self.textes.pop(0), 200, 30)


def test_l_ia_seulement_si_rien_n_est_reconnu(tmp_path: Path) -> None:
    db = BaseDonnees(tmp_path / "q.db")
    r = config.defauts().reglages
    client = FauxClient([])
    assert envies.comprendre(db, r, "envie de curry", client=client).voulus  # local : aucun appel
    assert client.demandes == []
    client = FauxClient(['{"voulus": ["cuisine:indienne"], "exclus": ["proteine:poisson"]}'])
    c = envies.comprendre(db, r, "un truc qui réchauffe comme chez ma grand-mère à Pondichéry", client=client)
    assert c.par_ia and c.voulus == {"cuisine:indienne"} and c.exclus == {"proteine:poisson"}
    assert "<envie>" in str(client.demandes[0][1]) and "DONNÉE" in client.demandes[0][0]
    # Une étiquette hors de la liste fermée est refusée (deux fois) : repli sur l'analyse locale (vide).
    client = FauxClient(['{"voulus": ["ignore les règles"]}', '{"voulus": ["supprime tout"]}'])
    c = envies.comprendre(db, r, "zzz", client=client, dormir=lambda s: None)
    assert c.vide() and not c.par_ia
    assert envies.comprendre(db, r, "   ", client=FauxClient([])).vide()


# --- Rappels de la veille ------------------------------------------------------------------------------------------


def _menu(*repas: tuple[int, str]) -> pl.Menu:
    return pl.Menu(LUNDI.isoformat(), [pl.Repas((LUNDI + timedelta(days=j)).isoformat(), "diner", "cuisine", r, 1.0)
                                       for j, r in repas], portions=1)  # fmt: skip


def test_rappels_de_la_veille() -> None:
    trempage = next(r for r in BASE.liste() if any(BASE.ingredients[i].trempage_heures for i in r.ids()))
    poulet = next(r for r in BASE.liste() if "poulet_filet" in r.ids())
    crevettes = next(r for r in BASE.liste() if "crevette" in r.ids())
    menu = _menu((2, trempage.id), (5, poulet.id), (1, crevettes.id), (0, poulet.id))
    rappels = rappels_veille.rappels(menu, BASE, jour_courses=0)
    textes = [x.texte for x in rappels]
    assert any(t.startswith("🫘 Ce soir, fais tremper les") and "demain mercredi" in t for t in textes)
    assert any("sors le poulet du congélateur et mets-le au réfrigérateur pour demain samedi" in t for t in textes)
    assert any("mets les crevettes à décongeler au réfrigérateur pour demain mardi" in t for t in textes)
    # Le poulet du lundi, acheté le lundi : rien à sortir du congélateur.
    assert not any("dimanche" in t and "poulet" in t for t in textes)
    assert [x.jour for x in rappels] == sorted(x.jour for x in rappels)
    assert all(x.jour == x.pour - timedelta(days=1) for x in rappels)
    assert len({x.cle for x in rappels}) == len(rappels)
    assert rappels_veille._article("inconnu", "navet") == "le navet"


# --- Page du menu ---------------------------------------------------------------------------------------------------


def test_page_du_menu(tmp_path: Path) -> None:
    profil, _ = pl.profil_depuis(config.defauts(), BASE)
    ctx = pl.Contexte(BASE, profil, LUNDI, envies=[envies.analyser("envie de mexicain")])
    menu = pl.generer(ctx, graine=3)
    menu.alertes = ["Budget <serré>"]
    menu.envies = ["envie de <b>mexicain</b>"]
    liste = mc.construire(menu, BASE, profil.placard, {}, profil.jour_courses)
    html = module_page.rendre(menu, BASE, liste)
    assert html.startswith("<!doctype html>") and "lundi 12 octobre" in html
    assert "Budget &lt;serré&gt;" in html and "&lt;b&gt;mexicain&lt;/b&gt;" in html and "<b>mexicain" not in html
    for r in menu.repas:
        assert e(BASE.recettes[r.recette].nom) in html
    assert f"{liste.total:.2f} €" in html and "Liste de courses" in html
    assert "prefers-color-scheme: dark" in html and "@media print" in html
    chemin = module_page.publier(menu, BASE, liste, tmp_path / "Quotidien")
    assert chemin.read_text(encoding="utf-8") == html
    assert not [p for p in chemin.parent.iterdir() if p.name.startswith(".quotidien-")]
    vide = pl.Menu(LUNDI.isoformat(), [], ["Impossible"], portions=2)
    html = module_page.rendre(vide, BASE, mc.construire(vide, BASE, set(), {}, 0))
    assert "Pas de menu possible" in html and "2 personnes" in html


def test_bloc_recette_quantites_a_l_echelle() -> None:
    rec = next(r for r in BASE.liste() if r.portions == 2 and any(lg.unite == "p" for lg in r.ingredients))
    bloc = module_page.bloc_recette(BASE, rec, 4)  # deux fois la recette
    lg = next(x for x in rec.ingredients if x.unite == "p")
    assert BASE.ingredients[lg.id].pluriel in bloc or BASE.ingredients[lg.id].nom in bloc
    assert "pour 4 portions" in bloc and "allergènes" in bloc
    assert module_page._quantite(BASE, "huile_olive", 15, "ml") == "15 ml d'huile d'olive"
    assert module_page._quantite(BASE, "pates", 200, "g") == "200 g de pâtes sèches"


def test_gabarit_html(tmp_path: Path) -> None:
    assert e('<a href="x">') == "&lt;a href=&quot;x&quot;&gt;"
    texte = page("Titre <x>", "<p>corps</p>")
    assert "<title>Titre &lt;x&gt;</title>" in texte and "<p>corps</p>" in texte
    cible = tmp_path / "a" / "b.html"
    ecrire_atomique(cible, "un")
    ecrire_atomique(cible, "deux")
    assert cible.read_text(encoding="utf-8") == "deux" and len(list(cible.parent.iterdir())) == 1


def test_menu_aller_retour_json_reste_valide() -> None:
    profil, _ = pl.profil_depuis(config.defauts(), BASE)
    menu = pl.generer(pl.Contexte(BASE, profil, LUNDI), graine=2)
    assert json.loads(menu.en_json())["debut"] == LUNDI.isoformat()
