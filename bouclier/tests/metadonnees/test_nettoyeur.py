"""§11.4 : 0 métadonnée sensible restante (relecture indépendante), image identique après orientation (SSIM ≥ 0,99),
profil ICC conservé, original intact (empreinte), pour chaque format géré."""

from __future__ import annotations

import io
import shutil
import subprocess
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pikepdf
import pytest
from PIL import Image, ImageCms, ImageOps

from bouclier import cli
from bouclier.metadonnees import lecture, nettoyeur, verif
from bouclier.metadonnees.formats import image
from bouclier.systeme import Resultat, Systeme
from tests.metadonnees import fixtures as f

SENSIBLES = [f.AUTEUR.encode(), f.SERIE.encode(), b"iPhone 15", b"Apple", b"<x:xmpmeta", b"Photoshop 3.0",
             b"http://ns.adobe.com/xap/1.0/", b"Exif\x00\x00", "Camille".encode("utf-16-le")]  # fmt: skip


def _ecrire(dossier: Path, nom: str, donnees: bytes) -> Path:
    chemin = dossier / nom
    chemin.write_bytes(donnees)
    return chemin


def _relecture_independante(donnees: bytes) -> list[str]:
    """Sans le code de Bouclier : octets bruts + Pillow."""
    restes = [repr(s) for s in SENSIBLES if s in donnees]
    image.ouvrir_heif()
    with Image.open(io.BytesIO(donnees)) as img:
        structure = {256, 257, 258, 259, 262, 273, 274, 277, 278, 279, 282, 283, 284, 296, 317, 338, 339, 34675}
        balises = {t for t in img.getexif() if t not in structure}
        if balises:
            restes.append(f"EXIF {sorted(balises)}")
        for cle in ("xmp", "Author", "Software", "exif"):
            if img.info.get(cle):
                restes.append(cle)
    return restes


def _icc(donnees: bytes) -> str:
    image.ouvrir_heif()
    with Image.open(io.BytesIO(donnees)) as img:
        icc = img.info.get("icc_profile")
        assert icc, "profil ICC perdu"
        return ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip()


@pytest.mark.parametrize(("nom", "fabrique", "sans_perte"), [
    ("photo.jpg", f.jpeg, True), ("capture.png", f.png, True), ("image.webp", f.webp, True),
    ("scan.tif", f.tiff, False), ("IMG_0001.heic", f.heic, False),
])  # fmt: skip
def test_photos_nettoyees(tmp_path: Path, nom: str, fabrique: object, sans_perte: bool) -> None:
    original = _ecrire(tmp_path, nom, fabrique())  # type: ignore[operator]
    avant = nettoyeur.empreinte(original)
    r = nettoyeur.nettoyer(original)
    assert r.erreur is None and r.propre == tmp_path / nom.replace(".", " (propre).", 1)
    assert "position GPS (Bordeaux)" in r.supprime and "appareil (Apple iPhone 15)" in r.supprime
    assert "numéro de série" in r.supprime and "auteur" in r.supprime
    assert r.restants == []
    propre = r.propre.read_bytes()
    assert _relecture_independante(propre) == []
    assert _icc(propre) == "Display P3"
    assert nettoyeur.empreinte(original) == avant
    with Image.open(io.BytesIO(fabrique())) as a, Image.open(r.propre) as b:  # type: ignore[operator]
        assert f.ssim(a, b) >= 0.99
        if sans_perte:
            assert a.tobytes() == b.convert(a.mode).tobytes()  # pixels identiques : rien n'a été recompressé
    assert "Supprimé : position GPS (Bordeaux)" in r.texte()


@pytest.mark.parametrize("fabrique", [f.jpeg, f.webp])
def test_orientation_6_appliquee_avant_de_retirer_la_balise(tmp_path: Path, fabrique: object) -> None:
    donnees = fabrique(orientation=6)  # type: ignore[operator]
    original = _ecrire(tmp_path, "tournee.jpg" if donnees[:2] == b"\xff\xd8" else "tournee.webp", donnees)
    r = nettoyeur.nettoyer(original)
    assert r.erreur is None and r.restants == [] and "photo remise à l'endroit (rotation appliquée)" in r.avertissements
    with Image.open(io.BytesIO(donnees)) as a, Image.open(r.propre) as b:  # type: ignore[arg-type]
        attendu = ImageOps.exif_transpose(a)
        assert b.size == (64, 96) and attendu.size == (64, 96)
        assert f.ssim(attendu, b) >= 0.99
        assert f.ssim(a.resize(b.size), b) < 0.9  # sans la rotation, l'image serait bien différente
        assert int(b.getexif().get(0x0112, 1)) == 1
    assert _icc(r.propre.read_bytes()) == "Display P3"  # type: ignore[union-attr]


def test_garder_la_date(tmp_path: Path) -> None:
    for fabrique, nom in ((f.jpeg, "a.jpg"), (f.tiff, "b.tif")):
        r = nettoyeur.nettoyer(_ecrire(tmp_path, nom, fabrique()), garder_date=True)
        assert r.erreur is None and r.restants == [] and "date de prise de vue" not in r.supprime
        with Image.open(r.propre) as img:  # type: ignore[arg-type]
            exif = img.getexif()
            assert exif.get_ifd(image.IFD_EXIF).get(image.TAG_DATE_ORIGINE) == "2026:09:12 18:30:00"
            assert not exif.get_ifd(0x8825) and 0x010F not in exif and 0x013B not in exif


def test_jpeg_images_annexes_et_segments(tmp_path: Path) -> None:
    donnees = f.jpeg()
    propre = image.jpeg_sans_perte(donnees)
    assert propre.endswith(b"\xff\xd9") and propre.count(b"\xff\xd8") == 1  # l'image annexe (MPF) est partie
    assert b"ICC_PROFILE\x00" in propre and b"JFIF" in propre
    progressive = io.BytesIO()
    f.photo().save(progressive, "JPEG", progressive=True, exif=f.exif_complet().tobytes())
    sortie = image.jpeg_sans_perte(progressive.getvalue())
    with Image.open(io.BytesIO(sortie)) as img:
        img.load()
        assert not len(img.getexif())
    with pytest.raises(ValueError):
        image.jpeg_sans_perte(b"pas un jpeg")


def test_pdf(tmp_path: Path) -> None:
    original = _ecrire(tmp_path, "facture.pdf", f.pdf_())
    avant = nettoyeur.empreinte(original)
    r = nettoyeur.nettoyer(original)
    assert r.erreur is None and r.restants == []
    assert {"auteur", "logiciel", "titre", "données XMP", "auteurs des annotations"} <= set(r.supprime)
    with pikepdf.open(r.propre) as pdf:  # relecture indépendante
        assert len(pdf.docinfo) == 0 and "/Metadata" not in pdf.Root and len(pdf.pages) == 1
        annotation = pdf.pages[0]["/Annots"][0]
        assert "/T" not in annotation and str(annotation["/Contents"]) == "à revoir"
    assert f.AUTEUR.encode() not in r.propre.read_bytes()  # type: ignore[union-attr]
    assert nettoyeur.empreinte(original) == avant


def test_office_et_commentaires_signales(tmp_path: Path) -> None:
    original = _ecrire(tmp_path, "contrat.docx", f.docx())
    r = nettoyeur.nettoyer(original)
    assert r.erreur is None and r.restants == []
    assert {"auteur", "dernier modificateur", "entreprise", "responsable", "propriétés personnalisées"} <= set(
        r.supprime
    )
    assert any("commentaires" in a for a in r.avertissements)
    assert any("modifications suivies" in a for a in r.avertissements)
    with zipfile.ZipFile(r.propre) as z:  # type: ignore[arg-type]
        core, app = z.read("docProps/core.xml").decode(), z.read("docProps/app.xml").decode()
        assert f.AUTEUR not in core and "Société" not in app and "<Pages>1</Pages>" in app
        assert z.read("word/document.xml") == zipfile.ZipFile(original).read("word/document.xml")
        assert z.testzip() is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
def test_video_avec_ffmpeg(tmp_path: Path) -> None:
    video = tmp_path / "film.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=5",
                    "-metadata", "location=+44.8378-000.5792/", "-metadata", f"artist={f.AUTEUR}",
                    "-metadata", "make=Apple", "-pix_fmt", "yuv420p", str(video)], check=True)  # fmt: skip
    r = nettoyeur.nettoyer(video)
    assert r.erreur is None and "position GPS" in r.supprime and "auteur" in r.supprime
    assert f.AUTEUR.encode() not in r.propre.read_bytes()  # type: ignore[union-attr]
    from bouclier.metadonnees.formats import video as v

    assert v.lire(r.propre) == []  # type: ignore[arg-type]


def test_video_sans_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bouclier.metadonnees.formats import video as v

    monkeypatch.setattr(v.shutil, "which", lambda nom: None)
    chemin = _ecrire(tmp_path, "film.mov", b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  ")
    r = nettoyeur.nettoyer(chemin)
    assert r.erreur == "vidéo non nettoyée : ffmpeg n'est pas installé sur ce Mac" and v.lire(chemin) == []


def test_formats_non_geres_et_fichiers_abimes(tmp_path: Path) -> None:
    assert "format non géré" in str(nettoyeur.nettoyer(_ecrire(tmp_path, "note.txt", b"bonjour")).erreur)
    assert nettoyeur.nettoyer(tmp_path / "absent.jpg").erreur == "ce n'est pas un fichier"
    abime = _ecrire(tmp_path, "abime.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 20)
    r = nettoyeur.nettoyer(abime)
    assert r.erreur and r.propre is None and not list(tmp_path.glob("*propre*"))
    assert "❌ abime.jpg" in r.texte()
    lien = tmp_path / "lien.jpg"
    lien.symlink_to(_ecrire(tmp_path, "vrai.jpg", f.jpeg()))
    assert nettoyeur.nettoyer(lien).erreur == "ce n'est pas un fichier"


def test_noms_uniques_et_remplacer(tmp_path: Path) -> None:
    original = _ecrire(tmp_path, "photo.jpg", f.jpeg())
    assert nettoyeur.nettoyer(original).propre == tmp_path / "photo (propre).jpg"
    assert nettoyeur.nettoyer(original).propre == tmp_path / "photo (propre 2).jpg"
    corbeille: list[str] = []

    def executer(args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        corbeille.append(list(args)[-1])
        Path(list(args)[-1]).unlink()  # imitation du Finder : le fichier part à la Corbeille
        return Resultat(0, "")

    r = nettoyeur.nettoyer(original, remplacer=True, systeme=Systeme(executer, mac=True))
    assert r.remplace and r.propre == original and corbeille == [str(original)]
    assert lecture.lire_image(original.read_bytes()) == [] and "Corbeille" in r.texte()
    refus = nettoyeur.nettoyer(_ecrire(tmp_path, "b.jpg", f.jpeg()), remplacer=True,
                               systeme=Systeme(lambda a, e, d: Resultat(1, ""), mac=True))  # fmt: skip
    assert not refus.remplace and (tmp_path / "b.jpg").exists() and "Corbeille" in refus.avertissements[0]


def test_lieu_sans_reseau() -> None:
    assert lecture.lieu(44.838, -0.579) == "Bordeaux"
    assert lecture.lieu(44.70, -0.40) == "près de Bordeaux"
    assert lecture.lieu(46.0, -3.0) == "46,00 N, 3,00 O"


def test_relecture_exiftool_si_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    faux = tmp_path / "exiftool"
    faux.write_text('#!/bin/sh\necho \'[{"SourceFile":"x","File:FileSize":"1","IFD0:Make":"Apple"}]\'\n')
    faux.chmod(0o755)
    monkeypatch.setattr(verif.shutil, "which", lambda nom: str(faux) if nom == "exiftool" else None)
    assert verif.exiftool(tmp_path / "x.jpg") == ["IFD0:Make"]
    r = nettoyeur.nettoyer(_ecrire(tmp_path, "c.jpg", f.jpeg()))
    assert r.restants == ["exiftool : IFD0:Make"]


def test_cli_nettoyer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = _ecrire(tmp_path, "photo.jpg", f.jpeg())
    b = _ecrire(tmp_path, "texte.txt", b"x")
    mac = Systeme(lambda x, e, d: Resultat(0, ""), mac=False)
    assert cli.main(["nettoyer", str(a), str(b)], mac) == 1  # un fichier non géré : code 1, l'autre est fait
    sortie = capsys.readouterr().out
    assert "✅ photo.jpg → photo (propre).jpg" in sortie and "❌ texte.txt" in sortie
    assert cli.main(["nettoyer", str(a)], mac) == 0
