"""Les cas trouvés à la revue hostile (P11) : chacun a son test."""

from __future__ import annotations

import zipfile
from pathlib import Path

from modules.trieur import config, rangement, traitement
from modules.trieur.base import Base
from modules.trieur.classement import issue
from modules.trieur.entrees.surveillance import Entrees
from modules.trieur.extraction import extraire, formats
from tests.trieur.outils import FACTURE, FauxOCR, FauxSysteme, pdf, photo


def _boite(reglages) -> Path:
    b = config.chemin(reglages, "boite")
    b.mkdir(parents=True, exist_ok=True)
    return b


def test_photo_de_document_archive_en_echec_pas_de_pdf_en_trop(reglages, monkeypatch):
    texte = FACTURE.replace("FACTURE", "FACTURE\nDate de facture : 03/10/2026")
    o = traitement.outils(reglages, systeme_=FauxSysteme(), moteur=FauxOCR({(600, 800): texte}), ia=None)
    source = photo(_boite(reglages) / "IMG_1.JPG")
    vrai = rangement.deplacer

    def archive_cassee(*a, **k):
        if k.get("genre") == "archive":
            raise rangement.DeplacementImpossible("disque plein")
        return vrai(*a, **k)

    monkeypatch.setattr(rangement, "deplacer", archive_cassee)
    el = traitement.traiter(o, o.base.ajouter(source, "boite"))
    assert el.etat == "en_attente" and source.exists() and not list(o.classes.rglob("*.pdf"))
    monkeypatch.setattr(rangement, "deplacer", vrai)
    el = traitement.traiter(o, el.id)
    assert el.etat == "classe" and len(list((o.classes / "Factures").rglob("*.pdf"))) == 1
    assert not el.destination.endswith("-2.pdf")
    o.base.fermer()


def test_garantie_en_echec_le_document_reste_range(outils, monkeypatch):
    monkeypatch.setattr(outils.coffre, "enregistrer", lambda *a: (_ for _ in ()).throw(RuntimeError("Rappels muet")))
    source = pdf(_boite(outils.reglages) / "a.pdf", FACTURE)
    el = traitement.traiter(outils, outils.base.ajouter(source, "boite"))
    assert el.etat == "classe" and Path(el.destination).exists() and "Rappels muet" in el.erreur
    assert traitement.traiter_la_file(outils) == []  # pas de nouvel essai : il est rangé


def test_sans_ocr_une_photo_va_a_verifier(reglages):
    assert issue(None, "image", 0, "sans_ocr", reglages) == "a_verifier"
    assert issue(None, "image", 0, "illisible", reglages) == "a_verifier"
    assert issue(None, "image", 0, None, reglages) == "photos"
    o = traitement.outils(reglages, systeme_=FauxSysteme(), moteur=None, ia=None)
    el = traitement.traiter(o, o.base.ajouter(photo(_boite(reglages) / "IMG_2.JPG"), "boite"))
    assert el.etat == "a_verifier"
    o.base.fermer()


def test_fantome_icloud_sur_le_bureau(reglages, tmp_path):
    base = Base(tmp_path / "t.db")
    faux = FauxSysteme()
    e = Entrees(reglages, base, faux, lambda: 1_000.0)
    a_trier = config.chemin(reglages, "a_trier")
    e.creer_les_dossiers()
    (a_trier / ".scan.pdf.icloud").write_bytes(b"bplist")
    e.regarder()
    assert faux.telecharges == [a_trier / "scan.pdf"]
    base.fermer()


def test_docx_piege_refuse(tmp_path, monkeypatch):
    with zipfile.ZipFile(tmp_path / "piege.docx", "w") as z:
        z.writestr("word/document.xml", "<w:p><w:t>" + "a" * 100 + "</w:t></w:p>")
    monkeypatch.setattr(formats, "TAILLE_MAX_XML", 50)
    assert extraire(tmp_path / "piege.docx", None, tmp_path).erreur == "abime"


def test_annuler_apres_un_deplacement_a_la_main(outils):
    source = pdf(_boite(outils.reglages) / "a.pdf", FACTURE)
    el = traitement.traiter(outils, outils.base.ajouter(source, "boite"))
    ancien = Path(el.destination)
    nouveau = outils.classes / "Mes papiers" / ancien.name
    nouveau.parent.mkdir()
    ancien.rename(nouveau)
    traitement.apprendre_deplacement(outils, ancien, nouveau)
    traitement.annuler(outils, el.id)
    assert source.exists() and not nouveau.exists()


def test_reponse_hors_limite_mais_pas_la_nuit(monkeypatch):
    from modules.trieur import notifications

    appels = []
    monkeypatch.setattr("core.notifications.notifier", lambda t, m, **k: appels.append(k["urgent"]))
    monkeypatch.setattr("core.notifications.en_heures_silencieuses", lambda r: False)
    notifications._envoyer_vraiment("🗂 Rangé", "x")
    notifications._envoyer_vraiment("🛡 Garantie", "x", reponse=False)
    monkeypatch.setattr("core.notifications.en_heures_silencieuses", lambda r: True)
    notifications._envoyer_vraiment("🗂 Rangé", "x")
    assert appels == [True, False, False]
    n = notifications.Notifieur({"mode_test": False, "notifications": {"grouper_au_dela": 3}})
    n.echeance("Four", 7, "13/10/2026")
    assert appels[-1] is False
