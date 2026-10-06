"""Fixtures générées : pour chaque format géré, un fichier avec position GPS, appareil, numéro de série, auteur et
XMP ; une photo avec orientation EXIF 6 et un profil couleur « Display P3 »."""

from __future__ import annotations

import io
import struct
import zipfile
from fractions import Fraction

import numpy as np
from PIL import Image, ImageDraw

AUTEUR = "Camille Exemplaire"
SERIE = "SN-4242-ABCD"
XMP = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       b'<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Camille Exemplaire</dc:creator>'
       b"</rdf:Description></rdf:RDF></x:xmpmeta>")  # fmt: skip
BORDEAUX = (44.8378, -0.5792)


def _s15(x: float) -> bytes:
    return struct.pack(">i", round(x * 65536))


def icc_display_p3() -> bytes:
    """Un vrai profil ICC v2 (matrice + courbes) nommé « Display P3 » (primaires P3, blanc D65 adapté en D50)."""

    def xyz(x: float, y: float, z: float) -> bytes:
        return b"XYZ \x00\x00\x00\x00" + _s15(x) + _s15(y) + _s15(z)

    def desc(texte: str) -> bytes:
        a = texte.encode("ascii") + b"\x00"
        return b"desc\x00\x00\x00\x00" + struct.pack(">I", len(a)) + a + b"\x00" * 8 + b"\x00\x00\x00" + b"\x00" * 67

    courbe = b"curv\x00\x00\x00\x00" + struct.pack(">I", 1) + struct.pack(">H", 0x0233) + b"\x00\x00"
    tags = [
        (b"desc", desc("Display P3")),
        (b"cprt", b"text\x00\x00\x00\x00" + b"Bouclier tests\x00\x00"),
        (b"wtpt", xyz(0.9642, 1.0, 0.8249)),
        (b"rXYZ", xyz(0.5151, 0.2412, -0.0011)),
        (b"gXYZ", xyz(0.2920, 0.6922, 0.0419)),
        (b"bXYZ", xyz(0.1571, 0.0666, 0.7841)),
        (b"rTRC", courbe), (b"gTRC", courbe), (b"bTRC", courbe),
    ]  # fmt: skip
    debut = 128 + 4 + 12 * len(tags)
    table, donnees = b"", b""
    for sig, contenu in tags:
        while (debut + len(donnees)) % 4:
            donnees += b"\x00"
        table += sig + struct.pack(">II", debut + len(donnees), len(contenu))
        donnees += contenu
    corps = struct.pack(">I", len(tags)) + table + donnees
    taille = 128 + len(corps)
    date = b"\x07\xea\x00\x0a\x00\x06" + b"\x00" * 6
    blanc = _s15(0.9642) + _s15(1.0) + _s15(0.8249)
    entete = (struct.pack(">I", taille) + b"lcms" + bytes([2, 0x10, 0, 0]) + b"mntrRGB XYZ " + date + b"acspAPPL"
              + b"\x00" * 24 + blanc + b"\x00" * 48)  # fmt: skip
    assert len(entete) == 128
    return entete + corps


def _rationnels(valeur: float) -> tuple[Fraction, Fraction, Fraction]:
    v = abs(valeur)
    d = int(v)
    m = int((v - d) * 60)
    s = round(((v - d) * 60 - m) * 60, 2)
    return Fraction(d), Fraction(m), Fraction(s).limit_denominator(100)


def exif_complet(orientation: int = 1) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0110] = "iPhone 15"
    exif[0x013B] = AUTEUR
    exif[0x0131] = "17.4"
    exif[0x0132] = "2026:09:12 18:30:00"
    exif[0x0112] = orientation
    detail = exif.get_ifd(0x8769)
    detail[0x9003] = "2026:09:12 18:30:00"
    detail[0xA431] = SERIE
    detail[0x927C] = b"Apple iOS\x00\x00\x01MM notes du fabricant"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", _rationnels(BORDEAUX[0])
    gps[3], gps[4] = "W", _rationnels(BORDEAUX[1])
    return exif


def photo(largeur: int = 96, hauteur: int = 64) -> Image.Image:
    """Une image asymétrique (pour voir une rotation ratée) et texturée (pour le calcul de ressemblance)."""
    rng = np.random.default_rng(3)
    base = np.zeros((hauteur, largeur, 3), dtype=np.uint8)
    base[..., 0] = np.linspace(0, 255, largeur, dtype=np.uint8)[None, :]
    base[..., 1] = np.linspace(255, 0, hauteur, dtype=np.uint8)[:, None]
    base[..., 2] = (rng.random((hauteur, largeur)) * 60).astype(np.uint8) + 100
    img = Image.fromarray(base, "RGB")
    d = ImageDraw.Draw(img)
    d.rectangle([4, 4, 30, 20], fill=(255, 255, 255))
    d.ellipse([60, 30, 90, 60], fill=(10, 10, 10))
    return img


def jpeg(orientation: int = 1, avec_annexe: bool = True) -> bytes:
    sortie = io.BytesIO()
    photo().save(sortie, "JPEG", quality=95, exif=exif_complet(orientation).tobytes(), icc_profile=icc_display_p3())
    donnees = sortie.getvalue()
    # XMP (APP1), IPTC (APP13) et commentaire (COM) insérés après SOI ; une image annexe (MPF) après la fin.
    xmp = b"http://ns.adobe.com/xap/1.0/\x00" + XMP
    iptc = b"Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00\x00\x0c\x1c\x02P\x00\x07Camille"
    com = AUTEUR.encode()
    segments = (b"\xff\xe1" + struct.pack(">H", len(xmp) + 2) + xmp + b"\xff\xed" + struct.pack(">H", len(iptc) + 2)
                + iptc + b"\xff\xfe" + struct.pack(">H", len(com) + 2) + com)  # fmt: skip
    donnees = donnees[:2] + segments + donnees[2:]
    if avec_annexe:
        annexe = io.BytesIO()
        photo(16, 16).save(annexe, "JPEG", exif=exif_complet().tobytes())
        donnees += annexe.getvalue()
    return donnees


def png() -> bytes:
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Author", AUTEUR)
    info.add_text("Software", "Appareil Photo 17.4")
    info.add_itxt("XML:com.adobe.xmp", XMP.decode())
    sortie = io.BytesIO()
    photo().save(sortie, "PNG", pnginfo=info, exif=exif_complet().tobytes(), icc_profile=icc_display_p3())
    return sortie.getvalue()


def webp(orientation: int = 1) -> bytes:
    sortie = io.BytesIO()
    photo().save(sortie, "WEBP", quality=95, exif=exif_complet(orientation).tobytes(), xmp=XMP,
                 icc_profile=icc_display_p3())  # fmt: skip
    return sortie.getvalue()


def tiff() -> bytes:
    sortie = io.BytesIO()
    photo().save(sortie, "TIFF", exif=exif_complet().tobytes(), icc_profile=icc_display_p3())
    return sortie.getvalue()


def heic() -> bytes:
    import pillow_heif

    pillow_heif.register_heif_opener()
    sortie = io.BytesIO()
    photo().save(sortie, "HEIF", quality=95, exif=exif_complet().tobytes(), xmp=XMP, icc_profile=icc_display_p3())
    return sortie.getvalue()


def pdf_() -> bytes:
    import pikepdf

    doc = pikepdf.new()
    doc.add_blank_page(page_size=(200, 200))
    with doc.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
        meta["dc:creator"] = [AUTEUR]
    doc.docinfo["/Author"] = AUTEUR
    doc.docinfo["/Creator"] = "Microsoft Word"
    doc.docinfo["/Producer"] = "macOS Quartz PDFContext"
    doc.docinfo["/Title"] = "Facture"
    page = doc.pages[0]
    page.obj["/Annots"] = doc.make_indirect(pikepdf.Array([pikepdf.Dictionary(
        Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Text, Rect=[10, 10, 30, 30],
        Contents=pikepdf.String("à revoir"), T=pikepdf.String(AUTEUR))]))  # fmt: skip
    sortie = io.BytesIO()
    doc.save(sortie)
    return sortie.getvalue()


def docx(commentaires: bool = True) -> bytes:
    sortie = io.BytesIO()
    with zipfile.ZipFile(sortie, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/'
                                          '2006/content-types"/>')  # fmt: skip
        document = ('<w:document xmlns:w="w"><w:body><w:p><w:ins w:author="Camille Exemplaire"><w:r><w:t>Bonjour'
                    "</w:t></w:r></w:ins></w:p></w:body></w:document>")  # fmt: skip
        z.writestr("word/document.xml", document)
        z.writestr("docProps/core.xml", f'<cp:coreProperties xmlns:cp="cp" xmlns:dc="dc"><dc:creator>{AUTEUR}'
                                        f"</dc:creator><cp:lastModifiedBy>{AUTEUR}</cp:lastModifiedBy>"
                                        "<dc:title>Contrat</dc:title></cp:coreProperties>")  # fmt: skip
        app = ("<Properties><Application>Microsoft Office Word</Application><Company>Ma Société SARL</Company>"
               "<Manager>Chef</Manager><Pages>1</Pages></Properties>")  # fmt: skip
        z.writestr("docProps/app.xml", app)
        z.writestr("docProps/custom.xml", '<Properties><property name="client">Dupont</property></Properties>')
        if commentaires:
            z.writestr("word/comments.xml", '<w:comments><w:comment w:author="Camille Exemplaire"/></w:comments>')
    return sortie.getvalue()


def ssim(a: Image.Image, b: Image.Image) -> float:
    """Ressemblance structurelle moyenne (fenêtres 7×7), de -1 à 1 (1 = identiques)."""
    x = np.asarray(a.convert("L"), dtype=np.float64)
    y = np.asarray(b.convert("L"), dtype=np.float64)
    assert x.shape == y.shape, (x.shape, y.shape)
    k = 7

    def moyenne(m: np.ndarray) -> np.ndarray:
        c = np.cumsum(np.cumsum(np.pad(m, ((1, 0), (1, 0))), axis=0), axis=1)
        return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)

    mx, my = moyenne(x), moyenne(y)
    vx, vy, cxy = moyenne(x * x) - mx**2, moyenne(y * y) - my**2, moyenne(x * y) - mx * my
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    carte = ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx**2 + my**2 + c1) * (vx + vy + c2))
    return float(carte.mean())
