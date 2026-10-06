"""Les PDF : le texte avec PyMuPDF (pdftotext en repli), et les cas limites.

- protégé par mot de passe → erreur « protege » (le document va dans « À vérifier ») ;
- abîmé : illisible, ou réparé par MuPDF pour être lu → « abime » ;
- vide (0 octet, 0 page) → « vide » ;
- long (300 pages) : seules les 3 premières pages et la dernière sont lues ;
- scanné (presque pas de texte) : les pages sont rendues en images, puis lues par l'OCR ;
- un logo en haut de la 1re page (le nom de l'émetteur dessiné, pas écrit) : il est rendu à part pour l'OCR.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEXTE_MIN = 40  # en dessous, la page est une image : un scan


@dataclass
class LecturePDF:
    texte: str = ""
    pages: int = 0
    erreur: str | None = None
    scan: bool = False
    images: list[Path] = field(default_factory=list)  # pages rendues, pour l'OCR d'un scan
    logos: list[Path] = field(default_factory=list)  # images du haut de la 1re page, pour l'OCR


def pages_a_lire(total: int, debut: int = 3) -> list[int]:
    if total <= debut + 1:
        return list(range(total))
    return list(range(debut)) + [total - 1]


def lire(chemin: Path, travail: Path, debut: int = 3, pages_ocr: int = 2) -> LecturePDF:
    import pymupdf

    if chemin.stat().st_size == 0:
        return LecturePDF(erreur="vide")
    try:
        doc = pymupdf.open(chemin)
    except Exception:
        texte = _pdftotext(chemin, debut)
        return LecturePDF(texte=texte, erreur=None if len(texte.strip()) >= TEXTE_MIN else "abime")
    with doc:
        if doc.needs_pass:
            return LecturePDF(pages=doc.page_count, erreur="protege")
        if doc.page_count == 0:  # le fichier n'est pas vide (vu plus haut) : il est abîmé
            return LecturePDF(erreur="abime")
        if getattr(doc, "is_repaired", False):
            return LecturePDF(pages=doc.page_count, erreur="abime")
        numeros = pages_a_lire(doc.page_count, debut)
        morceaux = []
        for n in numeros:
            try:
                morceaux.append(doc[n].get_text("text", sort=True))
            except Exception:
                return LecturePDF(pages=doc.page_count, erreur="abime")
        texte = "\n".join(morceaux)
        lecture = LecturePDF(texte=texte, pages=doc.page_count)
        if len(texte.strip()) >= TEXTE_MIN:
            lecture.logos = _logos(doc[0], travail, chemin.stem[:40])
        else:
            lecture.scan = True
            travail.mkdir(parents=True, exist_ok=True)
            for n in numeros[:pages_ocr]:
                pix = doc[n].get_pixmap(dpi=200)
                sortie = travail / f"{chemin.stem[:40]}-page{n + 1}.png"
                pix.save(sortie)
                lecture.images.append(sortie)
        return lecture


def _logos(page: Any, travail: Path, nom: str) -> list[Path]:
    """Les images assez grandes dans le haut de la page (le quart supérieur) : souvent le nom de l'émetteur."""
    import pymupdf

    sortie: list[Path] = []
    try:
        infos = page.get_image_info()
    except Exception:
        return sortie
    hauteur = page.rect.height
    for i, info in enumerate(infos[:3]):
        x0, y0, x1, y1 = info.get("bbox", (0, 0, 0, 0))
        if y1 > hauteur * 0.3 or (x1 - x0) < 60 or (y1 - y0) < 15:
            continue
        travail.mkdir(parents=True, exist_ok=True)
        cible = travail / f"{nom}-logo{i + 1}.png"
        page.get_pixmap(dpi=200, clip=pymupdf.Rect(x0, y0, x1, y1)).save(cible)
        _pas_trop_allonge(cible)
        sortie.append(cible)
    return sortie


def _pas_trop_allonge(png: Path) -> None:
    """Un bandeau très allongé (600 × 120) est agrandi démesurément par certains OCR : une marge blanche en
    haut et en bas le ramène à 2:1 (même texte, 3 à 4 fois moins de calcul)."""
    from PIL import Image

    with Image.open(png) as img:
        largeur, hauteur = img.size
        if largeur <= 2 * hauteur:
            return
        fond = Image.new("RGB", (largeur, largeur // 2), "white")
        fond.paste(img.convert("RGB"), (0, (largeur // 2 - hauteur) // 2))
    fond.save(png)


def _pdftotext(chemin: Path, debut: int) -> str:
    """Le repli (Poppler), s'il est installé : il lit parfois ce que MuPDF refuse."""
    if not shutil.which("pdftotext"):
        return ""
    try:
        r = subprocess.run(["pdftotext", "-l", str(debut), "-layout", str(chemin), "-"], capture_output=True,
                           text=True, timeout=30)  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""
