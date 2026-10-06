"""Le coffre à garanties : fiches, alias, rappels (30 et 7 jours, rétractation), retrait, pages HTML."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from modules.trieur import pages, traitement
from modules.trieur.garanties.coffre import LISTE_TEST, Coffre
from tests.trieur.outils import FACTURE, pdf

EN_LIGNE = """Back Market
FACTURE
Commande n° : 452-3730852
Date de la commande : {commande}
Date de facture : {facture}
Livrée le : {livraison}
Désignation  Qté  Prix unitaire  Montant
iPhone 15 128 Go - reconditionné  1  529,00 €  529,00 €
Total TTC  529,00 €
Garantie Back Market : 24 mois.
www.backmarket.fr"""


def _boite(o, nom):
    return Path(o.reglages["chemins"]["icloud"]) / "BoiteMac" / nom


def _jj(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def test_facture_cree_fiche_alias_et_rappels(outils, faux_mac):
    achat = date.today() - timedelta(days=3)
    texte = EN_LIGNE.format(
        commande=_jj(achat - timedelta(days=2)), facture=_jj(achat), livraison=_jj(achat + timedelta(days=1))
    )
    el = traitement.traiter(outils, outils.base.ajouter(pdf(_boite(outils, "a.pdf"), texte), "boite"))
    fiches = outils.coffre.fiches()
    assert len(fiches) == 1 and fiches[0].produit.startswith("iPhone 15") and fiches[0].source == "facture"
    f = fiches[0]
    assert f.fin == date(achat.year + 2, achat.month, achat.day) and f.element == el.id and f.facture == el.destination
    alias = Path(f.alias)
    assert alias.is_symlink() and alias.resolve() == Path(el.destination).resolve()
    assert alias.parent == outils.classes / "Garanties" and "fin-" in alias.name
    titres = sorted(t for (_, t, _, _) in faux_mac.rappels.values())
    assert len(titres) == 3 and titres[0].startswith("Garantie : iPhone 15") and titres[2].startswith("Rétractation")
    listes = {liste for (liste, _, _, _) in faux_mac.rappels.values()}
    assert listes == {LISTE_TEST}  # mode test : jamais dans la vraie liste
    quand = sorted(q for (_, _, q, _) in faux_mac.rappels.values())
    assert quand[0] == datetime(*(achat + timedelta(days=12)).timetuple()[:3], 9, 0)  # livraison + 11 j, 9 h
    assert {(f.fin - q.date()).days for q in quand[1:]} == {30, 7}
    # Annuler la facture retire tout.
    traitement.annuler(outils, el.id)
    assert outils.coffre.fiches() == [] and not alias.is_symlink() and faux_mac.rappels == {}


def test_vieux_document_sans_rappels_passes(outils, faux_mac):
    el = traitement.traiter(
        outils, outils.base.ajouter(pdf(_boite(outils, "a.pdf"), FACTURE.replace("03/10/2026", "03/01/2020")), "boite")
    )
    f = outils.coffre.fiches()[0]
    assert f.fin == date(2022, 1, 3) and f.rappels == [] and faux_mac.rappels == {} and f.etat() == "expirée"
    assert el.etat == "classe"


def test_corriger_retire_la_garantie(outils, faux_mac):
    el = traitement.traiter(outils, outils.base.ajouter(pdf(_boite(outils, "a.pdf"), FACTURE), "boite"))
    assert len(outils.coffre.fiches()) == 1
    traitement.corriger(outils, el.id, "devis")
    assert outils.coffre.fiches() == []


def test_garanties_a_la_main(reglages, faux_mac, tmp_path):
    from modules.trieur.base import Base

    base = Base(tmp_path / "t.db")
    coffre = Coffre(reglages, base, faux_mac)
    achat = date.today() - timedelta(days=10)
    n = coffre.ajouter_a_la_main("Vélo cargo", achat, mois=60, emetteur="Atelier du vélo", prix="2400")
    f = coffre.fiche(n)
    assert f.mois == 60 and f.source == "manuelle" and f.alias is None and len(f.rappels) == 2
    n2 = coffre.ajouter_a_la_main("Tondeuse", achat, fin=achat + timedelta(days=400))
    assert coffre.fiche(n2).mois == 13
    assert coffre.fiche(coffre.ajouter_a_la_main("Four", achat)).mois == 24
    m = coffre.modifier(n, mois=36)
    assert (
        coffre.fiche(n) is None
        and coffre.fiche(m).fin.year == achat.year + 3
        and coffre.fiche(m).produit == "Vélo cargo"
    )
    with pytest.raises(ValueError, match="inconnu"):
        coffre.modifier(m, couleur="rouge")
    with pytest.raises(KeyError):
        coffre.modifier(999)
    faits = coffre.supprimer(m)
    assert any("rappel" in x for x in faits) and coffre.fiche(m) is None
    with pytest.raises(KeyError):
        coffre.supprimer(m)
    jour = coffre.fiche(n2).fin - timedelta(days=30)
    assert [(f.produit, j) for f, j in coffre.echeances(jour)] == [("Tondeuse", 30)]
    faux_mac.rappels_en_panne = True
    assert coffre.fiche(coffre.ajouter_a_la_main("Radiateur", achat)).rappels == []  # Rappels refusé : la fiche reste
    reglages["mode_test"] = False
    assert coffre.liste_rappels == "Garanties"
    base.fermer()


def test_pages_html(outils, tmp_path):
    traitement.traiter(outils, outils.base.ajouter(pdf(_boite(outils, "a.pdf"), FACTURE), "boite"))
    vue = outils.coffre.fiches()[0]
    outils.coffre.ajouter_a_la_main("Vieux grille-pain <b>", date(2019, 1, 1))
    ecrites = pages.mettre_a_jour(outils.reglages, outils.base, outils.coffre)
    assert [p.name for p in ecrites] == ["Mon coffre.html", "Derniers classements.html"]
    coffre = ecrites[0].read_text()
    assert pages.MARQUE in coffre and vue.produit in coffre and "&lt;b&gt;" in coffre and "expirée" in coffre
    assert "prefers-color-scheme: dark" in coffre and "http" not in coffre.replace("http-equiv", "")
    derniers = ecrites[1].read_text()
    assert "2026-10-03_Fnac_Facture" in derniers and "n°1" in derniers
    assert "Aucune garantie" in pages.page_coffre([]) and "Rien encore" in pages.page_derniers([])
    # Une page à toi du même nom n'est jamais remplacée.
    a_toi = tmp_path / "boite"
    a_toi.mkdir()
    (a_toi / "Mon coffre.html").write_text("<p>ma page</p>")
    cible = pages.ecrire(a_toi, "Mon coffre.html", pages.page_coffre([]))
    assert cible.name == "Mon coffre (Trieur).html" and (a_toi / "Mon coffre.html").read_text() == "<p>ma page</p>"
    assert pages.ecrire(a_toi, "Mon coffre.html", pages.page_coffre([])) == cible
    (a_toi / "Mon coffre (Trieur).html").write_text("<p>aussi à moi</p>")
    with pytest.raises(FileExistsError):
        pages.ecrire(a_toi, "Mon coffre.html", "x")
