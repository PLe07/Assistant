"""L'extraction (§4) : le texte d'un document, localement et gratuitement, quel que soit son format.

extraire(chemin, ...) renvoie une Extraction : la nature du fichier, son texte (lignes de haut en bas), les morceaux
reconnus par l'OCR (pour fabriquer un PDF cherchable), les pièces jointes d'un courriel, une adresse web, et l'erreur
éventuelle (protégé, abîmé, vide, illisible, sans OCR).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from modules.trieur.extraction import formats, image, pdf
from modules.trieur.extraction.ocr import Morceau, Moteur, OCRImpossible, en_lignes

Coins = Callable[[Path], list[tuple[float, float]] | None]
TEXTE = {".txt", ".md", ".csv", ".text"}
LIENS = {".url", ".webloc"}


@dataclass
class Extraction:
    nature: str  # pdf, scan, image, docx, texte, courriel, lien, fichier
    texte: str = ""
    erreur: str | None = None  # protege, abime, vide, illisible, sans_ocr
    pages: int = 0
    image: Path | None = None  # l'image préparée (photo, HEIC) : pour le PDF cherchable
    morceaux: list[Morceau] = field(default_factory=list)
    pieces_jointes: list[tuple[str, bytes]] = field(default_factory=list)
    url: str | None = None
    sujet: str = ""
    duree_s: float = 0.0

    @property
    def lignes(self) -> list[str]:
        return [ligne.strip() for ligne in self.texte.splitlines() if ligne.strip()]

    @property
    def mots(self) -> int:
        return len(re.findall(r"[A-Za-zÀ-ÿ]{2,}|\d+", self.texte))


def _ocr(moteur: Moteur | None, img: Path) -> tuple[str, list[Morceau], str | None]:
    if moteur is None:
        return "", [], "sans_ocr"
    try:
        morceaux = moteur.lire(img)
    except OCRImpossible:
        return "", [], "illisible"
    return "\n".join(en_lignes(morceaux)), morceaux, None


def extraire(
    chemin: Path, moteur: Moteur | None, travail: Path, debut: int = 3, coins: Coins | None = None
) -> Extraction:
    """coins(chemin_image) → les coins du document photographié (Vision sur le Mac) ou None."""
    depart = time.perf_counter()
    e = _extraire(chemin, moteur, travail, debut, coins)
    e.duree_s = time.perf_counter() - depart
    return e


def _extraire(chemin: Path, moteur: Moteur | None, travail: Path, debut: int, coins: Coins | None) -> Extraction:
    suffixe = chemin.suffix.lower()
    if chemin.stat().st_size == 0:
        return Extraction("fichier", erreur="vide")
    if suffixe == ".pdf":
        lu = pdf.lire(chemin, travail, debut)
        if not lu.scan:
            logos = [t for img in lu.logos if (t := _ocr(moteur, img)[0].strip())]
            return Extraction("pdf", "\n".join(logos + [lu.texte]), lu.erreur, lu.pages)
        textes, tous = [], []
        erreur = None
        for page in lu.images:
            t, m, erreur = _ocr(moteur, page)
            textes.append(t)
            tous += m
        return Extraction("scan", "\n".join(textes), erreur, lu.pages, morceaux=tous)
    if suffixe in image.EXTENSIONS:
        try:
            img = image.ouvrir(chemin)
        except image.ImageIllisible:
            return Extraction("image", erreur="illisible")
        brute = image.preparer(img, travail, f"{chemin.stem[:40]}-brute")
        img = image.recadrer(img, coins(brute) if coins else None)
        prete = image.preparer(img, travail, chemin.stem[:40])
        t, m, erreur = _ocr(moteur, prete)
        return Extraction("image", t, erreur, 1, image=prete, morceaux=m)
    if suffixe == ".docx":
        try:
            return Extraction("docx", formats.docx(chemin))
        except Exception:
            return Extraction("docx", erreur="abime")
    if suffixe == ".eml":
        try:
            c = formats.courriel(chemin)
        except Exception:
            return Extraction("courriel", erreur="abime")
        return Extraction("courriel", f"{c.sujet}\n{c.expediteur}\n{c.corps}", pieces_jointes=c.pieces, sujet=c.sujet)
    if suffixe in LIENS or suffixe in TEXTE:
        adresse = formats.lien(chemin)
        if adresse:
            return Extraction("lien", adresse, url=adresse)
        if suffixe in TEXTE:
            return Extraction("texte", formats.texte(chemin))
        return Extraction("lien", erreur="abime")
    return Extraction("fichier")
