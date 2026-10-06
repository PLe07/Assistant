"""La chaîne de traitement : file, doublons, déplacement sûr, destinations, annuler, corriger, apprendre."""

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from modules.trieur import rangement, traitement
from modules.trieur.classement import emetteurs
from tests.trieur.outils import DEVIS_AMBIGU, FACTURE, FauxOCR, pdf, photo


def _entree(o, nom: str) -> Path:
    return Path(o.reglages["chemins"]["icloud"]) / "BoiteMac" / nom


def _traiter(o, chemin: Path, source: str = "boite", note: str | None = None):
    return traitement.traiter(o, o.base.ajouter(chemin, source, note))


def test_file_idempotente(outils, tmp_path):
    f = pdf(tmp_path / "a.pdf", FACTURE)
    a = outils.base.ajouter(f, "cli")
    assert outils.base.ajouter(f, "cli", note="garantie 3 ans") == a
    assert outils.base.element(a).note == "garantie 3 ans" and outils.base.compter() == {"en_attente": 1}
    assert outils.base.prendre(a) and not outils.base.prendre(a)
    assert traitement.traiter(outils, a) is None  # déjà pris
    assert outils.base.relacher_les_interrompus() == 1 and outils.base.en_attente()[0].id == a


def test_facture_rangee_et_source_supprimee(outils, faux_mac):
    source = pdf(_entree(outils, "Scan 12.pdf"), FACTURE)
    el = _traiter(outils, source)
    attendu = outils.classes / "Factures/2026/2026-10-03_Fnac_Facture_Casque-Sony-WH-1000XM6_249,99€.pdf"
    assert el.etat == "classe" and el.destination == str(attendu) and attendu.exists() and not source.exists()
    assert (el.type, el.emetteur, el.date, el.montant, el.par) == (
        "facture_achat",
        "Fnac",
        "2026-10-03",
        "249.99",
        "règles",
    )
    assert faux_mac.tags[str(attendu)] == ["Facture", "Garantie"]
    genres = [a["genre"] for a in outils.base.actions(el.id)]
    assert (
        genres == ["range", "supprime_source", "tag", "alias", "rappel", "rappel"]
        and el.details["numero"] == "F2026-12345"
    )
    assert not outils.travail(el.id).exists()  # le dossier de travail est nettoyé


def test_jamais_d_ecrasement(outils):
    dossier = outils.classes / "Factures/2026"
    dossier.mkdir(parents=True)
    occupe = dossier / "2026-10-03_Fnac_Facture_Casque-Sony-WH-1000XM6_249,99€.pdf"
    occupe.write_bytes(b"un fichier qui etait la avant")
    el = _traiter(outils, pdf(_entree(outils, "a.pdf"), FACTURE))
    assert occupe.read_bytes() == b"un fichier qui etait la avant"
    assert el.destination.endswith("_249,99€-2.pdf")


def test_doublons(outils, tmp_path):
    premier = _traiter(outils, pdf(_entree(outils, "a.pdf"), FACTURE))
    copie = _entree(outils, "a (copie).pdf")
    copie.write_bytes(Path(premier.destination).read_bytes())
    assert rangement.empreinte(copie) == premier.empreinte
    d = _traiter(outils, copie)
    assert d.etat == "doublon" and d.details["de"] == premier.id and "Doublons" in d.destination and not copie.exists()
    ailleurs = tmp_path / "Bureau/facture.pdf"
    ailleurs.parent.mkdir()
    ailleurs.write_bytes(Path(premier.destination).read_bytes())
    d2 = _traiter(outils, ailleurs, "cli")
    assert d2.etat == "doublon" and ailleurs.exists() and d2.destination is None  # demandé à la main : ne bouge pas
    pj = tmp_path / "pieces/facture.pdf"
    pj.parent.mkdir()
    pj.write_bytes(Path(premier.destination).read_bytes())
    assert _traiter(outils, pj, "courriel").etat == "doublon" and not pj.exists()  # une copie à nous


def test_erreurs_reessayees_puis_abandonnees(outils, monkeypatch):
    source = pdf(_entree(outils, "a.pdf"), FACTURE)
    monkeypatch.setattr(traitement, "extraire", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("panne")))
    el = outils.base.ajouter(source, "boite")
    for attendu in ("en_attente", "en_attente", "erreur"):
        assert traitement.traiter(outils, el).etat == attendu
    assert source.exists() and "panne" in outils.base.element(el).erreur
    disparu = _entree(outils, "parti.pdf")
    perdu = outils.base.ajouter(disparu, "boite")
    assert traitement.traiter(outils, perdu).erreur == "fichier introuvable"


def test_copie_incorrecte_rien_ne_bouge(outils, monkeypatch):
    source = pdf(_entree(outils, "a.pdf"), FACTURE)
    vraie = rangement.empreinte

    def fausse(chemin: Path) -> str:
        return "0" * 64 if "Classés" in str(chemin) else vraie(chemin)

    monkeypatch.setattr(rangement, "empreinte", fausse)
    el = _traiter(outils, source)
    assert el.etat == "en_attente" and "copie" in el.erreur and source.exists()
    assert not list((outils.classes / "Factures").rglob("*.pdf"))


def test_fichier_modifie_pendant_le_traitement(outils, monkeypatch):
    source = pdf(_entree(outils, "a.pdf"), FACTURE)
    vraie_extraction = traitement.extraire

    def puis_modifier(chemin, *a, **k):
        e = vraie_extraction(chemin, *a, **k)
        with chemin.open("ab") as f:
            f.write(b"\n% ajout")
        return e

    monkeypatch.setattr(traitement, "extraire", puis_modifier)
    el = _traiter(outils, source)
    assert el.etat == "en_attente" and "changé" in el.erreur and source.exists()


def test_photo_de_document_puis_annuler(reglages, faux_mac):
    texte = FACTURE.replace("FACTURE", "FACTURE\nDate de facture : 03/10/2026")
    o = traitement.outils(reglages, systeme_=faux_mac, moteur=FauxOCR({(600, 800): texte}), ia=None)
    source = photo(_entree(o, "IMG_4001.JPG"))
    contenu = source.read_bytes()
    el = _traiter(o, source)
    rangee = Path(el.destination)
    assert el.etat == "classe" and rangee.suffix == ".pdf" and rangee.parent == o.classes / "Factures/2026"
    original = Path(el.details["original"])
    assert original.parent == o.classes / "Originaux/2026" and original.read_bytes() == contenu
    import pymupdf

    with pymupdf.open(rangee) as d:
        assert "Total TTC" in d[0].get_text()  # cherchable
    faits = traitement.annuler(o, el.id)
    assert source.read_bytes() == contenu and not rangee.exists() and not original.exists()
    assert any("remis" in f for f in faits) and o.base.element(el.id).etat == "annule"
    with pytest.raises(traitement.Refus, match="déjà annulé"):
        traitement.annuler(o, el.id)
    # Revenu dans la boîte par l'annulation : il n'est pas repris tout seul.
    assert _traiter(o, source).etat == "ignore" and source.exists()
    o.base.fermer()


def test_destinations_selon_la_nature(outils, tmp_path):
    paysage = _traiter(outils, photo(_entree(outils, "IMG_5101.JPG")))
    assert paysage.etat == "photos" and Path(paysage.destination).parent == Path(outils.reglages["chemins"]["photos"])
    protege = _entree(outils, "facture_protegee.pdf")
    import pymupdf

    with pymupdf.open(pdf(_entree(outils, "s.pdf"), FACTURE)) as d:
        d.save(protege, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    p = _traiter(outils, protege)
    assert p.etat == "a_verifier" and p.destination.endswith("À vérifier/facture_protegee.pdf")
    lien = _entree(outils, "lien.url")
    lien.write_text("[InternetShortcut]\nURL=https://exemple.fr\n")
    assert "/Liens/" in _traiter(outils, lien).destination
    zip_ = _entree(outils, "archive.zip")
    zip_.write_bytes(b"PK\x03\x04 rien")
    assert _traiter(outils, zip_).destination.endswith("Fichiers/zip/archive.zip")
    note = _entree(outils, "idee.txt")
    note.write_text("penser à rappeler le plombier")
    assert "Notes reçues" in _traiter(outils, note).destination


def test_courriel_et_piece_jointe(outils, tmp_path):
    facture = pdf(tmp_path / "f.pdf", FACTURE)
    m = EmailMessage()
    m["Subject"], m["From"] = "Votre facture", "factures@boutique.example"
    m.set_content("Bonjour, voici votre facture.")
    m.add_attachment(facture.read_bytes(), maintype="application", subtype="pdf", filename="Facture-123.pdf")
    eml = _entree(outils, "Votre facture.eml")
    eml.parent.mkdir(parents=True)
    eml.write_bytes(m.as_bytes())
    faits = traitement.traiter_la_file(outils) if outils.base.ajouter(eml, "boite") else []
    assert len(faits) == 2 and outils.ajoutes
    piece = outils.base.element(outils.ajoutes[0])
    assert piece.parent == faits[0].id and piece.etat == "classe" and "Fnac" in piece.destination
    assert not Path(piece.chemin).exists()


def test_telechargements_seulement_si_sur(outils, reglages):
    dl = Path(reglages["chemins"]["telechargements"])
    flou = pdf(dl / "doc.pdf", "Bonjour\nquelques mots sans rapport")
    assert _traiter(outils, flou, "telechargements").etat == "ignore" and flou.exists()
    sur = pdf(dl / "facture.pdf", FACTURE)
    assert _traiter(outils, sur, "telechargements").etat == "classe" and not sur.exists()


def test_annuler_place_prise_et_refus(outils):
    source = pdf(_entree(outils, "a.pdf"), FACTURE)
    el = _traiter(outils, source)
    source.write_bytes(b"un autre fichier arrive depuis au meme nom")
    traitement.annuler(outils, el.id)
    assert source.read_bytes().startswith(b"un autre") and _entree(outils, "a-2.pdf").exists()
    with pytest.raises(traitement.Refus, match="aucun élément"):
        traitement.annuler(outils, 999)
    vide = outils.base.ajouter(_entree(outils, "x.pdf"), "boite")
    with pytest.raises(traitement.Refus, match="rien à annuler"):
        traitement.annuler(outils, vide)


def test_corriger_et_apprendre(outils, reglages):
    premier = _traiter(outils, pdf(_entree(outils, "a.pdf"), DEVIS_AMBIGU))
    assert premier.etat == "a_verifier"
    corrige = traitement.corriger(outils, premier.id, "devis", emetteur="Plomberie Martin")
    assert corrige.type == "devis" and corrige.par == "correction" and corrige.etat == "classe"
    assert Path(corrige.destination).parent == outils.classes / "Devis/2026" and Path(corrige.destination).exists()
    assert outils.base.appris()[emetteurs.cle("Plomberie Martin")]["devis"] == traitement.POINTS_APPRIS
    # Le suivant du même artisan est reconnu tout seul.
    second = _traiter(outils, pdf(_entree(outils, "b.pdf"), DEVIS_AMBIGU.replace("05/10", "07/10")))
    assert second.type == "devis" and second.etat == "classe"
    # Annuler après une correction : retour à la boîte, en deux sauts.
    traitement.annuler(outils, corrige.id)
    assert _entree(outils, "a.pdf").exists()
    with pytest.raises(traitement.Refus, match="type inconnu"):
        traitement.corriger(outils, second.id, "pas_un_type")
    with pytest.raises(traitement.Refus, match="pas un document rangé"):
        traitement.corriger(outils, corrige.id, "devis")


def test_corriger_l_emetteur_retenu(outils, reglages):
    texte = ("SARL LES TROIS CHENES\nFACTURE\nDate de facture : 02/10/2026\nTable de jardin  1  320,00 €\n"
             "Total TTC  320,00 €")  # fmt: skip
    el = _traiter(outils, pdf(_entree(outils, "a.pdf"), texte))
    assert el.emetteur == "Sarl les Trois Chenes"
    traitement.corriger(outils, el.id, "facture_achat", emetteur="Les Trois Chênes")
    perso = json.loads((Path(reglages["dossier"]) / "emetteurs_perso.json").read_text())
    assert (
        perso["emetteurs"][0]["nom"] == "Les Trois Chênes"
        and "sarl les trois chenes" in perso["emetteurs"][0]["motifs"]
    )
    suivant = _traiter(outils, pdf(_entree(outils, "b.pdf"), texte.replace("02/10", "04/10")))
    assert suivant.emetteur == "Les Trois Chênes"


def test_deplacement_a_la_main(outils):
    el = _traiter(outils, pdf(_entree(outils, "a.pdf"), FACTURE))
    ancien = Path(el.destination)
    nouveau = outils.classes / "Devis/2026" / ancien.name
    nouveau.parent.mkdir(parents=True)
    ancien.rename(nouveau)
    assert traitement.apprendre_deplacement(outils, ancien, nouveau) == "devis"
    assert outils.base.element(el.id).destination == str(nouveau)
    assert outils.base.appris()["fnac"] == {"devis": traitement.POINTS_APPRIS}
    dehors = outils.classes.parent / "ailleurs.pdf"
    nouveau.rename(dehors)
    assert traitement.apprendre_deplacement(outils, nouveau, dehors) is None
    assert outils.base.element(el.id).destination == str(dehors)
    assert traitement.apprendre_deplacement(outils, Path("/nulle/part.pdf"), dehors) is None


def test_type_du_dossier(reglages):
    assert traitement.type_du_dossier(Path("Banque/LCL/2026"), reglages) == "releve_bancaire"
    assert traitement.type_du_dossier(Path("Factures/2026"), reglages) is None  # trois types de factures
    assert traitement.type_du_dossier(Path("Devis/Sans date"), reglages) == "devis"
    assert traitement.type_du_dossier(Path("Vacances"), reglages) is None


def test_api_ajouter(reglages, tmp_path, monkeypatch):
    from modules import trieur
    from modules.trieur import systeme

    monkeypatch.setattr(systeme, "choisir", lambda: __import__("tests.trieur.outils", fromlist=["x"]).FauxSysteme())
    reglages["ia"]["actif"] = False
    f = pdf(tmp_path / "facture.pdf", FACTURE)
    r = trieur.ajouter(f, source="api", reglages=reglages)
    assert r["etat"] == "classe" and r["type"] == "facture_achat" and Path(r["destination"]).exists()
    with pytest.raises(ValueError, match="source inconnue"):
        trieur.ajouter(f, source="pigeon", reglages=reglages)
    with pytest.raises(FileNotFoundError):
        trieur.ajouter(tmp_path / "absent.pdf", reglages=reglages)
