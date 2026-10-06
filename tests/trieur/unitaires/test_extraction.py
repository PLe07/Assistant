"""L'extraction : chaque format, chaque cas limite, et l'OCR avec un moteur imité (rapide, déterministe)."""

from __future__ import annotations

import io
import plistlib
import zipfile
from email.message import EmailMessage
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

from modules.trieur.extraction import extraire, formats, image, ocr, pdf
from modules.trieur.extraction.ocr import Morceau


class FauxOCR:
    nom = "faux"

    def __init__(self, morceaux: list[Morceau] | None = None, erreur: bool = False):
        self.morceaux = morceaux if morceaux is not None else [Morceau("TOTAL  12,50", 0.1, 0.5, 0.3, 0.02)]
        self.erreur, self.lus = erreur, []

    def lire(self, img: Path) -> list[Morceau]:
        self.lus.append(img)
        if self.erreur:
            raise ocr.OCRImpossible("illisible")
        return list(self.morceaux)


def _pdf(chemin: Path, lignes: list[str], pages: int = 1, logo: bool = False) -> Path:
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page()
        if logo and n == 0:
            buf = io.BytesIO()
            Image.new("RGB", (300, 60), "navy").save(buf, "PNG")
            page.insert_image(pymupdf.Rect(40, 30, 240, 70), stream=buf.getvalue())
        for i, ligne in enumerate(lignes):
            page.insert_text((50, 100 + 14 * i), f"{ligne} (page {n + 1})" if pages > 1 else ligne)
    doc.save(chemin)
    doc.close()
    return chemin


LIGNES = ["FACTURE n° FA-2026-001", "Date de facture : 03/10/2026", "Casque audio  1  249,99 €", "Total TTC 249,99 €"]


# --- PDF ---------------------------------------------------------------------------------------------------------


def test_pdf_texte_et_pages_lues(tmp_path):
    lu = pdf.lire(_pdf(tmp_path / "f.pdf", LIGNES), tmp_path / "t")
    assert lu.erreur is None and not lu.scan and lu.pages == 1 and "Total TTC" in lu.texte
    assert pdf.pages_a_lire(2) == [0, 1] and pdf.pages_a_lire(4) == [0, 1, 2, 3]
    assert pdf.pages_a_lire(300) == [0, 1, 2, 299] and pdf.pages_a_lire(10, debut=1) == [0, 9]


def test_pdf_long_lit_debut_et_fin(tmp_path):
    lu = pdf.lire(_pdf(tmp_path / "long.pdf", ["Contrat"], pages=8), tmp_path / "t")
    assert "(page 1)" in lu.texte and "(page 3)" in lu.texte and "(page 8)" in lu.texte
    assert "(page 4)" not in lu.texte and lu.pages == 8


def test_pdf_vide_protege_abime(tmp_path):
    (tmp_path / "vide.pdf").write_bytes(b"")
    assert pdf.lire(tmp_path / "vide.pdf", tmp_path).erreur == "vide"
    source = _pdf(tmp_path / "s.pdf", LIGNES)
    with pymupdf.open(source) as d:
        d.save(tmp_path / "protege.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="o")
    assert pdf.lire(tmp_path / "protege.pdf", tmp_path).erreur == "protege"
    (tmp_path / "abime.pdf").write_bytes(source.read_bytes()[:300])
    assert pdf.lire(tmp_path / "abime.pdf", tmp_path).erreur == "abime"
    (tmp_path / "pas_un.pdf").write_bytes(b"%PDF-1.4 ceci n'est pas un pdf")
    assert pdf.lire(tmp_path / "pas_un.pdf", tmp_path).erreur == "abime"


def test_pdf_scanne_rendu_en_images_et_lu(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(buf, "PNG")
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(tmp_path / "scan.pdf")
    lu = pdf.lire(tmp_path / "scan.pdf", tmp_path / "t")
    assert lu.scan and len(lu.images) == 1 and lu.images[0].exists()
    moteur = FauxOCR()
    e = extraire(tmp_path / "scan.pdf", moteur, tmp_path / "t")
    assert e.nature == "scan" and "TOTAL  12,50" in e.texte and e.morceaux and e.duree_s >= 0
    assert extraire(tmp_path / "scan.pdf", None, tmp_path / "t").erreur == "sans_ocr"
    assert extraire(tmp_path / "scan.pdf", FauxOCR(erreur=True), tmp_path / "t").erreur == "illisible"


def test_pdf_logo_lu_par_l_ocr(tmp_path):
    chemin = _pdf(tmp_path / "logo.pdf", LIGNES, logo=True)
    moteur = FauxOCR([Morceau("MA BOUTIQUE", 0.1, 0.2, 0.6, 0.3)])
    e = extraire(chemin, moteur, tmp_path / "t")
    assert e.nature == "pdf" and e.texte.startswith("MA BOUTIQUE") and len(moteur.lus) == 1
    assert extraire(chemin, None, tmp_path / "t").texte.startswith("FACTURE")


def test_pdftotext_en_repli(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf.shutil, "which", lambda _: None)
    assert pdf._pdftotext(tmp_path / "x.pdf", 3) == ""
    monkeypatch.setattr(pdf.shutil, "which", lambda _: "/usr/bin/pdftotext")

    class R:
        returncode, stdout = 0, "texte lu par poppler " * 5

    monkeypatch.setattr(pdf.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(pymupdf, "open", lambda *_: (_ for _ in ()).throw(RuntimeError("cassé")))
    (tmp_path / "x.pdf").write_bytes(b"%PDF")
    lu = pdf.lire(tmp_path / "x.pdf", tmp_path)
    assert lu.erreur is None and "poppler" in lu.texte

    def lent(*a, **k):
        raise pdf.subprocess.TimeoutExpired("pdftotext", 30)

    monkeypatch.setattr(pdf.subprocess, "run", lent)
    assert pdf.lire(tmp_path / "x.pdf", tmp_path).erreur == "abime"


# --- images ------------------------------------------------------------------------------------------------------


def _photo(chemin: Path, orientation: int | None = None) -> Path:
    img = Image.new("RGB", (400, 300), (60, 60, 60))
    ImageDraw.Draw(img).rectangle((100, 50, 300, 250), fill="white")
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    img.save(chemin, "JPEG", exif=exif.tobytes())
    return chemin


def test_image_exif_recadrage_et_ocr(tmp_path):
    tournee = image.ouvrir(_photo(tmp_path / "p.jpg", orientation=6))
    assert tournee.size == (300, 400)  # remise droite
    droite = image.ouvrir(_photo(tmp_path / "d.jpg"))
    coupee = image.recadrer(droite)
    assert coupee.size[0] < 400 and coupee.size[1] < 300  # le papier blanc seul
    assert image.recadrer(droite, [(0.25, 0.2), (0.75, 0.2), (0.75, 0.8), (0.25, 0.8)]).size[0] < 400
    assert image.recadrer(Image.new("RGB", (100, 100), "white")).size == (100, 100)  # un scan : rien à couper
    assert image.recadrer(Image.new("RGB", (100, 100), "black")).size == (100, 100)
    e = extraire(tmp_path / "d.jpg", FauxOCR(), tmp_path / "t", coins=lambda _: None)
    assert e.nature == "image" and e.image is not None and e.image.exists() and e.pages == 1
    (tmp_path / "casse.jpg").write_bytes(b"pas une image")
    assert extraire(tmp_path / "casse.jpg", FauxOCR(), tmp_path / "t").erreur == "illisible"


def test_heic_sans_sips_ni_pillow_heif(tmp_path, monkeypatch):
    monkeypatch.setattr(image.shutil, "which", lambda _: None)
    monkeypatch.setitem(__import__("sys").modules, "pillow_heif", None)
    (tmp_path / "x.heic").write_bytes(b"\x00\x00\x00\x18ftypheic")
    with pytest.raises(image.ImageIllisible):
        image.ouvrir(tmp_path / "x.heic")


def test_heic_par_sips(tmp_path, monkeypatch):
    def faux_sips(cmd, **k):
        Image.new("RGB", (20, 10), "white").save(cmd[-1], "JPEG")

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(image.shutil, "which", lambda _: "/usr/bin/sips")
    monkeypatch.setattr(image.subprocess, "run", faux_sips)
    (tmp_path / "x.heic").write_bytes(b"heic")
    assert image.ouvrir(tmp_path / "x.heic").size == (20, 10)


def test_pdf_cherchable_texte_invisible(tmp_path):
    png = tmp_path / "ticket.png"
    Image.new("RGB", (400, 600), "white").save(png)
    morceaux = [Morceau("CARREFOUR", 0.1, 0.05, 0.5, 0.04), Morceau("TOTAL 23,45 €", 0.1, 0.8, 0.6, 0.04),
                Morceau("emoji 🎧", 0.1, 0.9, 0.3, 0.03)]  # fmt: skip
    image.pdf_cherchable(png, morceaux, tmp_path / "ticket.pdf")
    with pymupdf.open(tmp_path / "ticket.pdf") as d:
        texte = d[0].get_text()
    assert "CARREFOUR" in texte and "23,45" in texte


# --- OCR ---------------------------------------------------------------------------------------------------------


def test_en_lignes_colonnes_et_pente():
    droite = [Morceau("Total TTC", 0.1, 0.50, 0.2, 0.02), Morceau("249,99 €", 0.7, 0.505, 0.15, 0.02),
              Morceau("FACTURE", 0.4, 0.1, 0.2, 0.03)]  # fmt: skip
    assert ocr.en_lignes(droite) == ["FACTURE", "Total TTC  249,99 €"]
    # Une page de travers (pente 0,06) : le prix de la 1re ligne est plus bas que le début de la 2e.
    penche = [Morceau("Net a payer", 0.05, 0.403, 0.3, 0.033, pente=0.06),
              Morceau("88,00", 0.75, 0.445, 0.1, 0.021, pente=0.06),
              Morceau("TVA 20 %", 0.05, 0.433, 0.25, 0.03, pente=0.06),
              Morceau("14,67", 0.75, 0.475, 0.1, 0.021, pente=0.06)]  # fmt: skip
    assert ocr.en_lignes(penche) == ["Net a payer  88,00", "TVA 20 %  14,67"]
    a_plat = [Morceau(m.texte, m.x, m.y, m.largeur, m.hauteur) for m in penche]
    assert ocr.en_lignes(a_plat) != ["Net a payer  88,00", "TVA 20 %  14,67"]  # sans redresser : mélangé
    assert ocr.pente_mediane([]) == 0.0


def test_tesseract_tsv(monkeypatch, tmp_path):
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "1\t1\t0\t0\t0\t0\t0\t0\t1000\t2000\t-1\t\n"
           "5\t1\t1\t1\t1\t1\t100\t200\t150\t30\t96.5\tTotal\n"
           "5\t1\t1\t1\t1\t2\t300\t200\t100\t30\t91\t12,50\n"
           "5\t1\t1\t1\t1\t3\t300\t200\t100\t30\t91\t \n"
           "bad\n")  # fmt: skip
    morceaux = ocr.analyser_tsv(tsv)
    assert [m.texte for m in morceaux] == ["Total", "12,50"] and morceaux[0].x == 0.1 and morceaux[0].confiance == 0.965
    assert ocr.analyser_tsv("") == []

    class R:
        returncode, stdout, stderr = 0, tsv, ""

    monkeypatch.setattr(ocr.subprocess, "run", lambda *a, **k: R())
    assert len(ocr.Tesseract().lire(tmp_path / "x.png")) == 2
    R.returncode, R.stderr = 1, "erreur"
    with pytest.raises(ocr.OCRImpossible):
        ocr.Tesseract().lire(tmp_path / "x.png")


def test_rapidocr_adaptateur(monkeypatch, tmp_path):
    png = tmp_path / "x.png"
    Image.new("RGB", (1000, 500), "white").save(png)
    monkeypatch.setattr(
        ocr.RapidOCR,
        "_moteur",
        lambda chemin: ([[[[100, 100], [300, 110], [300, 140], [100, 130]], "Total", 0.9]], 0.1),
    )
    m = ocr.RapidOCR().lire(png)[0]
    assert m.texte == "Total" and m.x == 0.1 and m.y == 0.2 and m.pente == pytest.approx(0.1)


def test_cache_de_l_ocr(tmp_path):
    png = tmp_path / "x.png"
    Image.new("RGB", (10, 10), "white").save(png)
    moteur = FauxOCR()
    cache = ocr.AvecCache(moteur, tmp_path / "cache")
    assert cache.lire(png) == cache.lire(png) and len(moteur.lus) == 1


def test_choisir_un_moteur(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda _: "/usr/bin/tesseract")
    assert ocr.choisir("tesseract").nom == "tesseract"
    monkeypatch.setattr(ocr.shutil, "which", lambda _: None)
    monkeypatch.setitem(__import__("sys").modules, "rapidocr_onnxruntime", None)
    assert ocr.choisir("auto") is None and ocr.choisir("aucun") is None
    monkeypatch.delenv("TRIEUR_CACHE_OCR", raising=False)
    assert ocr.avec_cache_si_demande(None) is None
    assert isinstance(ocr.avec_cache_si_demande(FauxOCR()), FauxOCR)


# --- autres formats ----------------------------------------------------------------------------------------------


def test_docx_texte_lien(tmp_path):
    xml = ('<w:document><w:body><w:p><w:r><w:t>Devis n° 12</w:t></w:r></w:p><w:p></w:p>'
           '<w:p><w:r><w:t xml:space="preserve">Total &amp; TTC </w:t></w:r><w:r><w:t>480,00 €</w:t></w:r></w:p>'
           '</w:body></w:document>')  # fmt: skip
    with zipfile.ZipFile(tmp_path / "d.docx", "w") as z:
        z.writestr("word/document.xml", xml)
    assert extraire(tmp_path / "d.docx", None, tmp_path).texte == "Devis n° 12\nTotal & TTC 480,00 €"
    (tmp_path / "casse.docx").write_bytes(b"pas un zip")
    assert extraire(tmp_path / "casse.docx", None, tmp_path).erreur == "abime"
    (tmp_path / "n.txt").write_bytes("Reçu de loyer".encode("cp1252"))
    assert extraire(tmp_path / "n.txt", None, tmp_path).texte == "Reçu de loyer"
    assert formats.texte(tmp_path / "n.txt") == "Reçu de loyer"
    (tmp_path / "l.txt").write_text("  https://exemple.fr/facture/12  \n")
    e = extraire(tmp_path / "l.txt", None, tmp_path)
    assert e.nature == "lien" and e.url == "https://exemple.fr/facture/12"
    (tmp_path / "w.url").write_text("[InternetShortcut]\nURL=https://exemple.fr/x\n")
    assert formats.lien(tmp_path / "w.url") == "https://exemple.fr/x"
    (tmp_path / "w2.url").write_text("https://exemple.fr/y")
    assert formats.lien(tmp_path / "w2.url") == "https://exemple.fr/y"
    (tmp_path / "m.webloc").write_bytes(plistlib.dumps({"URL": "https://exemple.fr/z"}))
    assert extraire(tmp_path / "m.webloc", None, tmp_path).url == "https://exemple.fr/z"
    (tmp_path / "casse.webloc").write_bytes(b"pas un plist")
    assert extraire(tmp_path / "casse.webloc", None, tmp_path).erreur == "abime"
    (tmp_path / "x.zip").write_bytes(b"PK")
    assert extraire(tmp_path / "x.zip", None, tmp_path).nature == "fichier"
    (tmp_path / "zero.jpg").write_bytes(b"")
    assert extraire(tmp_path / "zero.jpg", None, tmp_path).erreur == "vide"


def test_courriel_avec_piece_jointe(tmp_path):
    m = EmailMessage()
    m["Subject"], m["From"] = "Votre facture", "Boutique <factures@boutique.example>"
    m.set_content("Bonjour, votre facture est jointe.")
    m.add_attachment(b"%PDF-1.4 contenu", maintype="application", subtype="pdf", filename="../Facture-12.pdf")
    (tmp_path / "f.eml").write_bytes(m.as_bytes())
    e = extraire(tmp_path / "f.eml", None, tmp_path)
    assert e.nature == "courriel" and e.sujet == "Votre facture" and "facture est jointe" in e.texte
    assert e.pieces_jointes == [("Facture-12.pdf", b"%PDF-1.4 contenu")]  # le nom sans chemin
    h = EmailMessage()
    h["Subject"] = "HTML"
    h.set_content("<p>Total&nbsp;: <b>12 €</b></p>", subtype="html")
    (tmp_path / "h.eml").write_bytes(h.as_bytes())
    assert (
        "Total" in extraire(tmp_path / "h.eml", None, tmp_path).texte
        and "<b>" not in formats.courriel(tmp_path / "h.eml").corps
    )
    (tmp_path / "x.eml").write_bytes(b"\xff\xfe\x00")
    assert extraire(tmp_path / "x.eml", None, tmp_path).nature == "courriel"


def test_extraction_proprietes():
    from modules.trieur.extraction import Extraction

    e = Extraction("texte", "  Ligne 1 \n\n Total 12,50 € ")
    assert e.lignes == ["Ligne 1", "Total 12,50 €"] and e.mots == 5
