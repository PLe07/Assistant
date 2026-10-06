"""Le générateur lui-même : assez de documents, tous les types, tous les pièges, des fichiers valides."""

import collections
import hashlib
import json
import random
import re

import pymupdf
from PIL import Image

from tests.trieur.corpus import donnees
from tests.trieur.corpus.generer import generer

TYPES = ["facture_achat", "ticket_caisse", "facture_service", "releve_bancaire", "avis_imposition", "quittance_loyer",
         "bail_contrat", "attestation", "bulletin_paie", "assurance", "billet_transport", "reservation", "sante",
         "identite", "devis", "facture_emise", "garantie_notice", "courrier_admin", "autre"]  # fmt: skip
PIEGES = ["paysage", "protege", "corrompu", "vide", "doublon", "sante_illisible", "collision", "emoji", "fantome",
          "300_pages", "eml"]  # fmt: skip


def test_assez_de_documents_de_tous_les_types(corpus1):
    v = corpus1.verites
    assert len(v) >= 120
    par_type = collections.Counter(x.type for x in v)
    assert all(par_type[t] >= 3 for t in TYPES), par_type
    supports = collections.Counter(x.support for x in v)
    assert supports["pdf_texte"] >= 60 and supports["scan_jpg"] + supports["scan_pdf"] >= 15
    assert supports["photo_ticket"] + supports["photo_exif"] >= 6 and supports["heic"] >= 3
    lots = {x.lot.split(":", 1)[1] for x in v if x.lot.startswith("piege:")}
    assert all(any(lot.startswith(p) for lot in lots) for p in PIEGES), lots
    assert json.loads((corpus1.dossier / "verite.json").read_text())[0]["fichier"] == v[0].fichier


def test_les_fichiers_s_ouvrent(corpus1):
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    for v in corpus1.verites:
        chemin = corpus1.dossier / v.fichier
        if v.support in ("fantome", "piece_jointe", "eml") or v.lot in (
            "piege:protege",
            "piege:corrompu",
            "piege:vide",
        ):
            continue
        if chemin.suffix.lower() == ".pdf":
            with pymupdf.open(chemin) as d:
                assert d.page_count >= 1, v.fichier
        else:
            with Image.open(chemin) as img:
                assert img.width > 300, v.fichier
    with pymupdf.open(corpus1.dossier / "facture_protegee.pdf") as d:
        assert d.needs_pass
    assert (corpus1.dossier / "vide.pdf").stat().st_size == 0
    with pymupdf.open(corpus1.dossier / "contrat-et-facture-300-pages.pdf") as d:
        assert d.page_count == 300


def test_verite_coherente(corpus1):
    for v in corpus1.verites:
        if v.type and v.issue == "classe" and v.type not in ("garantie_notice", "autre"):
            assert v.date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.date), v
        if v.type in (
            "facture_achat",
            "ticket_caisse",
            "facture_service",
            "devis",
            "facture_emise",
            "billet_transport",
        ):
            assert v.montant, v
        for g in v.garanties:
            assert g["fin"] > (v.date or "") and g["source"] in ("note", "facture", "légale")
    sans = [v for v in corpus1.verites if v.type == "facture_achat" and not v.garanties]
    avec = [v for v in corpus1.verites if v.garanties]
    assert sans and len(avec) >= 15  # des consommables seuls, et beaucoup de biens durables
    fevrier = [v for v in corpus1.verites if v.date == "2024-02-29"]
    assert fevrier and fevrier[0].garanties[0]["fin"] == "2027-02-28"  # extension 3 ans depuis un 29 février
    assert any(v.note == "garantie 3 ans" and v.garanties[0]["source"] == "note" for v in corpus1.verites)
    assert any(v.retractation for v in corpus1.verites)
    assert all(
        v.sensible for v in corpus1.verites if v.type in ("sante", "identite", "avis_imposition", "bulletin_paie")
    )


def test_numeros_inventes_mais_valides():
    r = random.Random(3)
    for _ in range(50):
        assert donnees.iban_ok(donnees.iban(r))
        assert donnees.luhn_ok(donnees.carte(r))
        n = donnees.nir(r).replace(" ", "")
        assert int(n[-2:]) == 97 - int(n[:-2]) % 97


def test_deterministe(tmp_path):
    """Même graine, mêmes octets : les doublons sont exacts et l'OCR peut être mis en cache."""
    a, b = generer(tmp_path / "a", graine=7), generer(tmp_path / "b", graine=7)
    for x in a.verites[:40]:
        fa, fb = a.dossier / x.fichier, b.dossier / x.fichier
        if fa.exists() and fa.suffix.lower() in (".pdf", ".jpg"):
            assert hashlib.sha256(fa.read_bytes()).digest() == hashlib.sha256(fb.read_bytes()).digest(), x.fichier
