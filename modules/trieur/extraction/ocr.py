"""La reconnaissance de texte (OCR) : une interface, plusieurs moteurs.

- Vision (sur ton Mac, `natif.py`) : fr-FR et en-US, précision maximale. C'est le moteur normal.
- tesseract (s'il est installé) : le repli.
- RapidOCR : seulement là où Vision n'existe pas (les tests dans le conteneur, D-05).
- Aucun : mode dégradé, le document part dans « À vérifier ».

Chaque moteur renvoie des morceaux de texte avec leur cadre ; `en_lignes` les remet en lignes, de haut en bas et de
gauche à droite, en gardant les colonnes séparées par deux espaces (« Total TTC  249,99 € »).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Morceau:
    texte: str
    x: float  # bord gauche, 0 à 1
    y: float  # bord haut, 0 à 1 (depuis le haut)
    largeur: float
    hauteur: float
    confiance: float = 1.0
    pente: float = 0.0  # inclinaison de la ligne (Δy / Δx, en coordonnées 0 à 1) : un scan un peu de travers


class Moteur(Protocol):
    nom: str

    def lire(self, image: Path) -> list[Morceau]: ...


class OCRImpossible(Exception):
    """Aucun moteur n'a pu lire l'image."""


def pente_mediane(morceaux: list[Morceau]) -> float:
    """L'inclinaison de la page, d'après les morceaux assez longs pour la mesurer."""
    pentes = sorted(m.pente for m in morceaux if m.largeur > 0.08 and abs(m.pente) < 0.3)
    return pentes[len(pentes) // 2] if pentes else 0.0


def en_lignes(morceaux: list[Morceau]) -> list[str]:
    """Regroupe les morceaux qui se chevauchent verticalement en une ligne, triée de gauche à droite.
    Sur un scan de travers, la hauteur de chaque morceau est d'abord redressée (sinon les lignes se mélangent)."""
    pente = pente_mediane(morceaux)

    def centre(m: Morceau) -> float:
        return m.y + m.hauteur / 2 - (m.x + m.largeur / 2) * pente

    def epaisseur(m: Morceau) -> float:
        return max(0.004, m.hauteur - abs(m.largeur * pente))  # la boîte d'un morceau penché est plus haute

    lignes: list[list[Morceau]] = []
    for m in sorted(morceaux, key=lambda m: (centre(m), m.x)):
        for ligne in lignes:
            ref = sum(centre(x) for x in ligne) / len(ligne)
            if abs(ref - centre(m)) < max(epaisseur(ligne[0]), epaisseur(m)) * 0.55:
                ligne.append(m)
                break
        else:
            lignes.append([m])
    sortie = []
    for ligne in sorted(lignes, key=lambda li: min(centre(m) for m in li)):
        sortie.append("  ".join(m.texte.strip() for m in sorted(ligne, key=lambda m: m.x) if m.texte.strip()))
    return [s for s in sortie if s]


class Tesseract:
    nom = "tesseract"

    def __init__(self, binaire: str = "tesseract"):
        self.binaire = binaire

    def lire(self, image: Path) -> list[Morceau]:
        r = subprocess.run([self.binaire, str(image), "stdout", "-l", "fra+eng", "--psm", "4", "tsv"],
                           capture_output=True, text=True, timeout=120)  # fmt: skip
        if r.returncode != 0:
            raise OCRImpossible(r.stderr.strip()[:200] or "tesseract a échoué")
        return analyser_tsv(r.stdout)


def analyser_tsv(tsv: str) -> list[Morceau]:
    """La sortie TSV de tesseract : un mot par ligne, avec sa boîte en pixels."""
    lignes = tsv.splitlines()
    if not lignes:
        return []
    mots, largeur, hauteur = [], 1.0, 1.0
    for ligne in lignes[1:]:
        champs = ligne.split("\t")
        if len(champs) < 12:
            continue
        niveau, gauche, haut, l_, h_, conf, texte = champs[0], *champs[6:12]
        if niveau == "1":
            largeur, hauteur = float(l_) or 1.0, float(h_) or 1.0
            continue
        if niveau != "5" or not texte.strip():
            continue
        mots.append((float(gauche), float(haut), float(l_), float(h_), float(conf), texte))
    return [
        Morceau(t, g / largeur, h / hauteur, l_ / largeur, hh / hauteur, max(0.0, c) / 100)
        for g, h, l_, hh, c, t in mots
    ]


class RapidOCR:
    """Moteur des tests hors Mac (D-05), jamais utilisé sur le Mac où Vision existe."""

    nom = "rapidocr"
    _moteur: Any = None

    def lire(self, image: Path) -> list[Morceau]:
        from PIL import Image

        if RapidOCR._moteur is None:
            from rapidocr_onnxruntime import RapidOCR as _R

            # Sans le classifieur d'orientation : les images arrivent déjà droites (EXIF appliqué), et il retourne
            # parfois un prix (« 699,00 » lu « 00'669 »), ce que Vision ne fait pas.
            RapidOCR._moteur = _R(use_cls=False)
        with Image.open(image) as img:
            largeur, hauteur = img.size
        resultat, _ = RapidOCR._moteur(str(image))
        morceaux = []
        for boite, texte, score in resultat or []:
            xs, ys = [p[0] for p in boite], [p[1] for p in boite]
            (x0, y0), (x1, y1) = boite[0], boite[1]  # le bord haut : haut-gauche → haut-droit
            pente = ((y1 - y0) / hauteur) / ((x1 - x0) / largeur) if x1 - x0 > 1 else 0.0
            morceaux.append(Morceau(texte, min(xs) / largeur, min(ys) / hauteur, (max(xs) - min(xs)) / largeur,
                                    (max(ys) - min(ys)) / hauteur, float(score), pente))  # fmt: skip
        return morceaux


VERSION_CACHE = 2  # à augmenter quand le réglage d'un moteur change : l'ancien cache n'est plus relu


class AvecCache:
    """Garde le résultat de l'OCR par empreinte de l'image (les tests relisent le même corpus)."""

    def __init__(self, moteur: Moteur, dossier: Path):
        self.moteur, self.dossier, self.nom = moteur, dossier, moteur.nom

    def lire(self, image: Path) -> list[Morceau]:
        cle = hashlib.sha256(image.read_bytes()).hexdigest()
        fichier = self.dossier / f"{self.nom}-{VERSION_CACHE}-{cle}.json"
        if fichier.exists():
            return [Morceau(**m) for m in json.loads(fichier.read_text(encoding="utf-8"))]
        morceaux = self.moteur.lire(image)
        self.dossier.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps([asdict(m) for m in morceaux], ensure_ascii=False), encoding="utf-8")
        return morceaux


def choisir(preference: str = "auto") -> Moteur | None:
    """Le meilleur moteur disponible ici : Vision, puis tesseract, puis RapidOCR. None : aucun (mode dégradé)."""
    if preference in ("auto", "vision"):
        try:
            from modules.trieur import natif

            if natif.vision_disponible():
                return natif.Vision()
        except Exception:  # pas sur un Mac, ou pyobjc absent
            pass
    if preference in ("auto", "tesseract") and shutil.which("tesseract"):
        return Tesseract()
    if preference in ("auto", "rapidocr"):
        try:
            import rapidocr_onnxruntime  # noqa: F401

            return RapidOCR()
        except ImportError:
            pass
    return None


def avec_cache_si_demande(moteur: Moteur | None) -> Moteur | None:
    dossier = os.getenv("TRIEUR_CACHE_OCR")
    return AvecCache(moteur, Path(dossier)) if moteur is not None and dossier else moteur
