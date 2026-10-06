"""Les images : ouvrir (HEIC compris), remettre droit (EXIF), recadrer un document photographié, et fabriquer un
PDF propre et cherchable (l'image, avec le texte reconnu en calque invisible)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from modules.trieur.extraction.ocr import Morceau

EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".gif", ".bmp", ".webp"}
COTE_MAX = 3000


class ImageIllisible(Exception):
    pass


def ouvrir(chemin: Path) -> Image.Image:
    """L'image, remise droite selon son EXIF (une photo d'iPhone est souvent enregistrée couchée)."""
    if chemin.suffix.lower() in (".heic", ".heif"):
        return ImageOps.exif_transpose(_heic(chemin))
    try:
        with Image.open(chemin) as img:
            img.load()
            return ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise ImageIllisible(f"image illisible ({e.__class__.__name__})") from e


def _heic(chemin: Path) -> Image.Image:
    if shutil.which("sips"):  # sur le Mac : l'outil d'Apple
        with tempfile.TemporaryDirectory() as d:
            jpg = Path(d) / "converti.jpg"
            r = subprocess.run(["sips", "-s", "format", "jpeg", str(chemin), "--out", str(jpg)], capture_output=True,
                               text=True, timeout=60)  # fmt: skip
            if r.returncode == 0 and jpg.exists():
                with Image.open(jpg) as img:
                    img.load()
                    return img.convert("RGB")
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        with Image.open(chemin) as img:
            img.load()
            return img.convert("RGB")
    except Exception as e:
        raise ImageIllisible("HEIC illisible ici (sips absent)") from e


def recadrer(img: Image.Image, coins: list[tuple[float, float]] | None = None) -> Image.Image:
    """Le document seul : les coins donnés par Vision s'il y en a, sinon la zone claire (le papier) sur un fond plus
    sombre. Rien n'est coupé si le document occupe déjà presque toute l'image (un scan)."""
    l_, h_ = img.size
    if coins:
        xs, ys = [x * l_ for x, _ in coins], [y * h_ for _, y in coins]
        boite = (max(0, min(xs) - 10), max(0, min(ys) - 10), min(l_, max(xs) + 10), min(h_, max(ys) + 10))
    else:
        petit = img.convert("L").resize((max(1, l_ // 8), max(1, h_ // 8)))
        clair = petit.point(lambda v: 255 if v > 175 else 0)
        boite_petite = clair.getbbox()
        if not boite_petite:
            return img
        x0, y0, x1, y1 = (v * 8 for v in boite_petite)
        boite = (max(0, x0 - 16), max(0, y0 - 16), min(l_, x1 + 16), min(h_, y1 + 16))
    surface = (boite[2] - boite[0]) * (boite[3] - boite[1]) / (l_ * h_)
    if surface > 0.92 or surface < 0.08:
        return img
    return img.crop(tuple(int(v) for v in boite))  # type: ignore[arg-type]


def preparer(img: Image.Image, travail: Path, nom: str) -> Path:
    """L'image prête pour l'OCR (taille raisonnable), enregistrée dans le dossier de travail."""
    img = img.copy()
    img.thumbnail((COTE_MAX, COTE_MAX))
    travail.mkdir(parents=True, exist_ok=True)
    sortie = travail / f"{nom}.png"
    img.save(sortie, "PNG")
    return sortie


def _cp1252(texte: str) -> str:
    return texte.encode("cp1252", "replace").decode("cp1252")


def pdf_cherchable(image: Path, morceaux: list[Morceau], sortie: Path) -> None:
    """Une page A4 avec l'image, et chaque morceau de texte reconnu à sa place, invisible : le PDF se cherche dans
    Spotlight et dans Aperçu comme un document numérique."""
    import pymupdf

    with Image.open(image) as img:
        largeur_px, hauteur_px = img.size
    largeur = 595.0
    hauteur = largeur * hauteur_px / largeur_px
    doc = pymupdf.open()
    page = doc.new_page(width=largeur, height=hauteur)
    page.insert_image(page.rect, filename=str(image))
    for m in morceaux:
        taille = max(4.0, min(40.0, m.hauteur * hauteur * 0.8))
        try:
            page.insert_text((m.x * largeur, (m.y + m.hauteur) * hauteur - taille * 0.15), _cp1252(m.texte),
                             fontsize=taille, fontname="helv", render_mode=3)  # fmt: skip
        except Exception:  # un caractère que la police ne sait pas écrire : le texte de ce morceau est sauté
            continue
    doc.save(sortie, garbage=3, deflate=True)
    doc.close()
