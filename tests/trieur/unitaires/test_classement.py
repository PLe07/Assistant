"""Le classement local : texte, dates, montants, émetteurs, règles, champs, garanties, nommage."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from modules.trieur.classement import Classement, champs, classer, dates, emetteurs, issue, montants, nommage, regles
from modules.trieur.classement.texte import espaces_simples, normaliser, sans_accents
from modules.trieur.garanties import duree

# --- texte -------------------------------------------------------------------------------------------------------


def test_normaliser():
    assert normaliser("Facture N° 12 — Réglé\n  Œuvre’s   x ") == "facture n° 12 - regle\noeuvre's x"
    assert normaliser("Qté  1  249,99 €", colonnes=True) == "qte  1  249,99 €"
    assert sans_accents("Été") == "Ete" and espaces_simples(" a \t b ") == "a b"


# --- dates -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texte,attendu",
    [("03/10/2026", date(2026, 10, 3)), ("03-10-2026", date(2026, 10, 3)), ("03.10.2026", date(2026, 10, 3)),
     ("03/10/26", date(2026, 10, 3)), ("3 octobre 2026", date(2026, 10, 3)), ("03 oct. 2026", date(2026, 10, 3)),
     ("1er mars 2026", date(2026, 3, 1)), ("2026-10-03", date(2026, 10, 3)), ("le2avril2025", date(2025, 4, 2)),
     ("12 févr. 2025", date(2025, 2, 12))],
)  # fmt: skip
def test_formats_de_date(texte, attendu):
    assert [d.valeur for d in dates.toutes(texte)] == [attendu]


def test_dates_impossibles_ignorees():
    assert dates.toutes("31/02/2026 et 12/13/2026 et 01/01/1850 et 03/09") == []


def test_categories_et_choix_selon_le_type():
    texte = """FACTURE
Date de la commande : 01/10/2026
Date de facture : 03/10/2026
Livrée le 05/10/2026
Imprimé le 20/10/2026"""
    trouvees = dates.toutes(texte)
    assert [d.categorie for d in trouvees] == ["commande", "facture", "livraison", "exclue"]
    assert dates.date_du_document(trouvees, "facture_achat") == date(2026, 10, 3)
    assert dates.premiere(trouvees, "livraison") == date(2026, 10, 5)
    releve = dates.toutes("Période : du 01/09/2026 au 30/09/2026\n03/09 CB CARREFOUR 12,30")
    assert dates.date_du_document(releve, "releve_bancaire") == date(2026, 9, 30)
    billet = dates.toutes("Émis le 01/09/2026\nAller le 3 octobre 2026 à 14:04")
    assert dates.date_du_document(billet, "billet_transport") == date(2026, 10, 3)
    assert dates.categorie("Fait à Lyon, le") == "fait" and dates.categorie("Délivrée le") == "fait"
    assert dates.categorie("Date de délivrance :") == "delivrance" and dates.categorie("Né(e) le") == "exclue"
    assert dates.categorie("FaitaLyon,le") == "fait" and dates.categorie("rien") == "sans_etiquette"
    # L'étiquette sur la ligne du dessus (un tableau, l'OCR).
    dessus = dates.toutes("Date d'achat\n12/05/2026")
    assert dessus[0].categorie == "achat"
    assert dates.date_du_document([], "facture_achat") is None


# --- montants ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ligne,attendu",
    [("Total TTC : 1 249,99 €", "1249.99"), ("Net à payer 1.249,99 €", "1249.99"), ("Total TTC 249,99€", "249.99"),
     ("Montant TTC EUR 249,99", "249.99"), ("Reste à payer : 1 234 €", "1234.00"), ("Total TTC 89,90 EUR", "89.90"),
     ("Total à payer : 1 249,99 €", "1249.99")],
)  # fmt: skip
def test_montant_par_etiquette(ligne, attendu):
    assert montants.montant_ttc(ligne) == Decimal(attendu)


def test_montant_priorites_et_pieges():
    texte = """Désignation  Qté  Prix unitaire  Montant
Casque  1  249,99 €  249,99 €
Total HT  208,33 €
TVA 20 %  41,66 €
Total TTC  249,99 €
Ce montant sera prélevé le 12/10/2026"""
    assert montants.montant_ttc(texte) == Decimal("249.99")
    assert montants.montant_ttc("TOTAL\n23,45\nCB 23,45") == Decimal("23.45")  # étiquette seule : ligne suivante
    assert montants.montant_ttc("Ancien solde 1 200,00 €\nNouveau solde 980,00 €") is None
    assert montants.montant_ttc("Qté 2 pièces") is None
    assert montants.le_plus_grand("12,00 €\n1 249,99 €\nTVA 300,00 €") == Decimal("1249.99")
    assert montants.le_plus_grand("rien") is None
    assert montants.en_francais(Decimal("1249.9")) == "1249,90"
    assert [m.valeur for m in montants.dans("casque  1  249,99 €")] == [Decimal("249.99")]  # pas « 1 249,99 »


# --- émetteurs ---------------------------------------------------------------------------------------------------


def test_base_des_emetteurs():
    base = emetteurs.charger()
    assert len(base) >= 80 and len({e.nom for e in base}) == len(base)
    assert {e.categorie for e in base} >= {"commerce", "banque", "energie", "telecom", "sante", "assurance"}


def test_emetteur_en_tete_site_et_texte():
    releve = "BNP PARIBAS\nRELEVÉ DE COMPTE\n03/09 CB CARREFOUR MARKET\n05/09 PRLV SEPA EDF\n"
    assert emetteurs.trouver(releve).nom == "BNP Paribas"
    ligne = "FACTURE\nn° 12\n\n03/10/2026\nCasque\n1\n249,99 €\nTotal\nwww.boulanger.com"
    trouve = emetteurs.trouver(ligne)
    assert trouve.nom == "Boulanger" and trouve.source == "site" and trouve.connu
    # « Orange » est un mot courant : seulement en haut ou par son site.
    corps = (
        "MON ÉPICERIE\nFACTURE\n" + "ligne\n" * 6 + "jus d'orange  2,30 €\njus d'orange  2,30 €\njus d'orange 2,30 €"
    )
    assert emetteurs.trouver(corps).nom == "Mon Épicerie"
    assert emetteurs.trouver("Facture\nOrange\nForfait").nom == "Orange"


def test_emetteur_inconnu_lu_en_haut():
    assert emetteurs.trouver("Plomberie Martin\n12 rue des Artisans · 44000 Nantes\nDEVIS").nom == "Plomberie Martin"
    assert emetteurs.trouver("FACTURE\n12 rue des Lilas\nMairie  de  Rezé\n").nom == "Mairie de Rezé"
    assert emetteurs.trouver("BOULANGERIE DU PORT\nTICKET").nom == "Boulangerie du Port"
    assert emetteurs.trouver("Camille Dupont\nFACTURE", moi="Camille Dupont") is None
    assert emetteurs.trouver("") is None
    assert emetteurs.mise_en_forme("JBL") == "JBL" and emetteurs.mise_en_forme("BackMarket") == "Back Market"
    assert emetteurs.cle("Leroy-Merlin") == emetteurs.cle("LEROY MERLIN")


def test_emetteurs_perso(tmp_path):
    perso = tmp_path / "emetteurs_perso.json"
    perso.write_text(json.dumps({"emetteurs": [{"nom": "Fnac", "categorie": "ecommerce", "motifs": ["fnac"]},
                                               {"nom": "Ma Boulangerie", "categorie": "supermarche"}]}))  # fmt: skip
    base = emetteurs.charger(perso)
    assert [e.categorie for e in base if e.nom == "Fnac"] == ["ecommerce"]
    assert emetteurs.trouver("MA BOULANGERIE\nTICKET", base).categorie == "supermarche"
    (tmp_path / "casse.json").write_text("{")
    assert len(emetteurs.charger(tmp_path / "casse.json")) == len(emetteurs.charger())


# --- règles ------------------------------------------------------------------------------------------------------


def test_regles_toml_valide_et_erreurs(tmp_path):
    r = regles.charger()
    assert set(r.indices) == set(regles.TYPES) - {"autre"} and r.libelles["releve_bancaire"] == "Relevé"
    assert regles.souple("net a payer") == r"net\s*a\s*payer" and regles.souple(r"a\ b") == r"a\ b"
    with pytest.raises(regles.ReglesInvalides, match="inconnu"):
        regles.construire({"types": {"pas_un_type": {}}})
    with pytest.raises(regles.ReglesInvalides, match="indice 1"):
        regles.construire({"types": {"devis": {"indices": [{"re": "(", "poids": 1}]}}})
    with pytest.raises(regles.ReglesInvalides, match="catégorie"):
        regles.construire({"categories": {"banque": {"pas_un_type": 1}}})
    (tmp_path / "r.toml").write_text("[types")
    with pytest.raises(regles.ReglesInvalides, match="illisible"):
        regles.lire(tmp_path / "r.toml")


def test_decider_confiance():
    r = regles.charger()
    assert regles.decider(regles.Scores(), r) == ("autre", 0.0)
    assert regles.decider(regles.Scores({"devis": 2.0}), r)[0] == "autre"
    net, _ = regles.decider(regles.Scores({"devis": 12.0, "facture_achat": 2.0}), r), None
    proche = regles.decider(regles.Scores({"devis": 12.0, "facture_achat": 11.0}), r)
    assert net[0] == "devis" and net[1] > 0.9 and proche[1] < 0.3


# --- champs ------------------------------------------------------------------------------------------------------


def test_mentions_de_garantie_et_note():
    assert champs.mention_garantie("Garantie 2 ans pièces et main-d'œuvre.") == 24
    assert champs.mention_garantie("Extension de garantie 3 ans  1  49,99 €") == 36
    assert champs.mention_garantie("Garantieconstructeur12mois.") == 12
    assert champs.mention_garantie("cinq ans de garantie") == 60
    assert champs.mention_garantie("garantie légale de conformité de 2 ans") is None
    assert champs.mention_garantie("Garantie : voir conditions") is None
    assert champs.garantie_de_la_note("garantie 3 ans") == 36 and champs.garantie_de_la_note(None) is None


def test_produits_durables_et_consommables():
    texte = """Casque Sony WH-1000XM6  1  249,99 €  249,99 €
Cartouches d'encre HP 963 XL (pack de 4)  1  89,99 €  89,99 €
Coque iPhone 15  19,99 €
iPhone 15 128 Go reconditionné  529,00 €
Total TTC  888,97 €"""
    p = champs.produits(texte)
    assert [(x.durable, x.occasion) for x in p] == [(True, False), (False, False), (False, False), (True, True)]
    assert p[0].libelle == "Casque Sony WH-1000XM6" and p[0].prix == Decimal("249.99")
    assert champs.detail("facture_achat", texte, p) == "iPhone 15 128"
    assert champs.detail("facture_achat", "", []) == ""


def test_numero_en_ligne_detail():
    assert champs.numero("Facture n° : FA2026-12345") == "FA2026-12345"
    assert champs.numero("N° de facture 6118144472") == "6118144472" and champs.numero("Facture du jour") is None
    assert champs.achat_en_ligne("Commande n° 402-1234567\nLivrée le 05/10/2026", None)
    assert not champs.achat_en_ligne("Date d'achat 03/10/2026", "commerce")
    assert champs.detail("avis_imposition", "AVIS DE TAXE FONCIÈRE", []) == "Taxe foncière"
    assert champs.detail("identite", "PASSEPORT", []) == "Passeport"
    assert champs.detail("sante", "ORDONNANCE", []) == "Ordonnance"
    assert champs.detail("assurance", "AVIS D'ÉCHÉANCE", []) == "Échéance"
    assert champs.detail("attestation", "ATTESTATION DE SCOLARITÉ", []) == "Scolarite"
    assert champs.detail("bulletin_paie", "", []) == "Salaire" and champs.detail("devis", "", []) == ""


# --- classer -----------------------------------------------------------------------------------------------------

FACTURE = """FNAC
Fnac Paris Ternes · 75017 Paris
FACTURE
Date d'achat : 03/10/2026
Facture n° : F2026-12345
Imprimé le : 20/10/2026
Désignation  Qté  Prix unitaire  Montant
Casque Sony WH-1000XM6  1  249,99 €  249,99 €
Total HT  208,33 €
TVA 20 %  41,66 €
Total TTC  249,99 €
Garantie constructeur 12 mois.
www.fnac.com"""


def test_classer_une_facture(reglages):
    c = classer(FACTURE, reglages)
    assert (c.type, c.emetteur, c.date, c.montant, c.numero) == (
        "facture_achat",
        "Fnac",
        date(2026, 10, 3),
        Decimal("249.99"),
        "F2026-12345",
    )
    assert c.confiance >= 0.75 and c.emetteur_connu and c.sur and c.raisons
    assert [(g.fin, g.source) for g in c.garanties] == [(date(2028, 10, 3), "légale")]  # 12 mois < légale
    note = classer(FACTURE, reglages, note="garantie 3 ans")
    assert note.garanties[0].fin == date(2029, 10, 3) and note.garanties[0].source == "note"
    assert issue(c, "pdf", 80, None, reglages) == "classe"


def test_classer_en_ligne_et_occasion(reglages):
    texte = """Back Market
FACTURE
Commande n° : 452-3730852
Date de la commande : 16/05/2026
Date de facture : 17/05/2026
Livrée le : 20/05/2026
Désignation  Qté  Prix unitaire  Montant
iPhone 15 128 Go - reconditionné  1  529,00 €  529,00 €
Total TTC  529,00 €
Garantie Back Market : 24 mois.
www.backmarket.fr"""
    c = classer(texte, reglages)
    assert c.en_ligne and c.retractation == date(2026, 5, 31) and c.date == date(2026, 5, 17)
    assert [(g.fin, g.source, g.occasion) for g in c.garanties] == [(date(2028, 5, 17), "facture", True)]


def test_facture_emise_et_apprentissage(reglages):
    reglages["identite"] = {"nom": "Atelier Démo", "siret": "123 456 789 00012"}
    texte = ("Atelier Démo\nMicro-entrepreneur\nFACTURE\nDate : 03/10/2026\nClient : Mairie\nTotal  450,00 €\n"
             "TVA non applicable, art. 293 B du CGI.")  # fmt: skip
    c = classer(texte, reglages)
    assert c.type == "facture_emise" and c.emetteur == "Atelier Démo"
    siret = classer(texte.replace("Atelier Démo", "Mon atelier\nSIRET 123 456 789 00012"), reglages)
    assert siret.type == "facture_emise"
    # Ce que les corrections ont appris : « Plomberie Martin » envoie des devis.
    devis = "Plomberie Martin\nFACTURE PROFORMA\nDate : 03/10/2026\nTotal TTC 480,00 €"
    appris = {emetteurs.cle("Plomberie Martin"): {"devis": 12.0}}
    assert classer(devis, reglages, appris=appris).type == "devis"


def test_autre_et_issues(reglages):
    c = classer("Recette : tarte aux pommes\nIngrédients : 4 pommes, du sucre.", reglages)
    assert c.type == "autre" and c.emetteur is None and c.date is None and not c.sur
    assert issue(c, "pdf", 10, None, reglages) == "a_verifier"
    assert issue(None, "image", 2, None, reglages) == "photos"
    assert issue(None, "pdf", 0, "protege", reglages) == "a_verifier"
    assert issue(None, "image", 40, None, reglages) == "a_verifier"


# --- garanties, nommage ------------------------------------------------------------------------------------------


def test_duree_et_retractation(reglages):
    assert duree.duree(36, 12, False, reglages) == duree.Duree(36, "note")
    assert duree.duree(None, 12, False, reglages) == duree.Duree(24, "légale")
    assert duree.duree(None, 24, True, reglages) == duree.Duree(24, "facture")
    assert duree.duree(None, None, True, reglages) == duree.Duree(12, "légale")
    assert duree.ajouter_mois(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert duree.rappel_retractation(date(2026, 5, 20), date(2026, 5, 16), reglages) == date(2026, 5, 31)
    assert duree.rappel_retractation(None, date(2026, 5, 16), reglages) == date(2026, 5, 27)
    assert duree.rappel_retractation(None, None, reglages) is None
    reglages["garanties"]["retractation"] = False
    assert duree.rappel_retractation(date(2026, 5, 20), None, reglages) is None


def test_nom_de_fichier(reglages, tmp_path):
    c = Classement("facture_achat", 0.9, "Facture", emetteur="Leroy Merlin", date=date(2026, 10, 3),
                   montant=Decimal("249.9"), detail="Perceuse Makita 18 V")  # fmt: skip
    assert nommage.nom(c, ".PDF", reglages) == "2026-10-03_Leroy-Merlin_Facture_Perceuse-Makita-18-V_249,90€.pdf"
    sans = Classement("autre", 0.1, "Document")
    assert nommage.nom(sans, "pdf", reglages) == "sans-date_Document.pdf"
    long_ = Classement("facture_achat", 0.9, "Facture", emetteur="E" * 80, date=date(2026, 1, 1), detail="D" * 80,
                       montant=Decimal("1"))  # fmt: skip
    assert len(nommage.nom(long_, ".pdf", reglages)) <= 120 and nommage.nom(long_, ".pdf", reglages).endswith(".pdf")
    assert nommage.propre('a/b:c*"d" & l’été 🎧') == "a-b-c-d-et-l-été-🎧"
    (tmp_path / "x.pdf").write_bytes(b"1")
    (tmp_path / "x-2.pdf").write_bytes(b"2")
    assert nommage.libre(tmp_path, "x.pdf") == tmp_path / "x-3.pdf" and nommage.libre(tmp_path, "y.pdf").name == "y.pdf"


def test_dossier_de_rangement(reglages):
    c = Classement("releve_bancaire", 0.9, emetteur="BNP Paribas", date=date(2026, 9, 30))
    assert nommage.dossier(c, reglages) == Path("Banque/BNP Paribas/2026")
    assert nommage.dossier(Classement("facture_achat", 0.9), reglages) == Path("Factures/Sans date")
    assert nommage.dossier(c, reglages, "a_verifier") == Path("À vérifier")
    reglages["arborescence"]["devis"] = "../{emetteur}/.."
    assert nommage.dossier(Classement("devis", 0.9, emetteur="A/B"), reglages) == Path("A B")
    reglages["arborescence"]["devis"] = "{rien}"
    assert nommage.dossier(Classement("devis", 0.9), reglages) == Path("Divers")
