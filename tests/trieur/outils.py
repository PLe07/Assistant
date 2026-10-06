"""Les imitations communes aux tests : le Mac (tags, alias, rappels, iCloud) et l'OCR."""

from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path

import pymupdf
from PIL import Image

from modules.trieur.extraction.ocr import Morceau, OCRImpossible


class FauxSysteme:
    nom = "faux"

    def __init__(self) -> None:
        self.tags: dict[str, list[str]] = {}
        self.alias: dict[str, str] = {}
        self.rappels: dict[str, tuple[str, str, datetime, str]] = {}
        self.supprimes: list[str] = []
        self.telecharges: list[Path] = []
        self.rappels_en_panne = False

    def poser_tags(self, chemin: Path, tags: list[str]) -> bool:
        self.tags[str(chemin)] = list(tags)
        return True

    def creer_alias(self, cible: Path, alias: Path) -> bool:
        alias.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(cible, alias)
        self.alias[str(alias)] = str(cible)
        return True

    def coins(self, image: Path) -> list[tuple[float, float]] | None:
        return None

    def rappel_creer(self, liste: str, titre: str, quand: datetime, note: str = "") -> str | None:
        if self.rappels_en_panne:
            return None
        identifiant = f"x-apple-reminder://{len(self.rappels) + 1}"
        self.rappels[identifiant] = (liste, titre, quand, note)
        return identifiant

    def rappel_supprimer(self, liste: str, identifiant: str) -> bool:
        self.supprimes.append(identifiant)
        return self.rappels.pop(identifiant, None) is not None

    def telecharger_icloud(self, chemin: Path) -> bool:
        self.telecharges.append(chemin)
        return True

    def quarantaine(self, chemin: Path) -> str:
        return ""


class FauxOCR:
    """Lit dans chaque image le texte qu'on lui a donné pour elle (par la taille de l'image), sinon rien."""

    nom = "faux"

    def __init__(self, textes: dict[tuple[int, int], str] | None = None, erreur: bool = False):
        self.textes = textes or {}
        self.erreur = erreur
        self.lus: list[Path] = []

    def lire(self, image: Path) -> list[Morceau]:
        self.lus.append(image)
        if self.erreur:
            raise OCRImpossible("illisible")
        with Image.open(image) as img:
            texte = self.textes.get(img.size, "")
        lignes = [x for x in texte.splitlines() if x.strip()]
        return [Morceau(x, 0.05, 0.05 + i * 0.04, 0.8, 0.03) for i, x in enumerate(lignes)]


def pdf(chemin: Path, texte: str) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page()
    for i, ligne in enumerate(texte.splitlines()):
        page.insert_text((50, 60 + 14 * i), ligne, fontsize=10)
    doc.save(chemin)
    doc.close()
    return chemin


def photo(chemin: Path, taille: tuple[int, int] = (600, 800)) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", taille, (240, 240, 235)).save(chemin, "JPEG")
    return chemin


def png_bytes(taille: tuple[int, int] = (10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", taille, "white").save(buf, "PNG")
    return buf.getvalue()


FACTURE = """FNAC
Fnac Paris Ternes · 75017 Paris
FACTURE
Date d'achat : 03/10/2026
Facture n° : F2026-12345
Désignation  Qté  Prix unitaire  Montant
Casque Sony WH-1000XM6  1  249,99 €  249,99 €
Total HT  208,33 €
TVA 20 %  41,66 €
Total TTC  249,99 €
www.fnac.com"""

DEVIS_AMBIGU = """Plomberie Martin
12 rue des Artisans · 44000 Nantes
PROPOSITION
Date : 05/10/2026
Remplacement chauffe-eau  1  480,00 €
Total TTC  528,00 €"""
