"""La relecture indépendante du fichier propre : rien ne doit rester (ou seulement la date, si tu l'as demandé).

Elle ne réutilise pas le code de nettoyage : elle relit le résultat comme le ferait n'importe qui (Pillow, pikepdf,
l'archive Office, et `exiftool` s'il est installé sur le Mac), et cherche aussi dans les octets bruts les marques
des blocs de métadonnées (EXIF, XMP, IPTC) et les valeurs vues avant le nettoyage (nom d'auteur, numéro de série…).
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image

from bouclier.metadonnees.formats.image import IFD_EXIF, TAG_DATE_ORIGINE, ouvrir_heif

_MARQUES = {b"<x:xmpmeta": "données XMP", b"http://ns.adobe.com/xap/1.0/": "données XMP",
            b"Photoshop 3.0\x008BIM": "données IPTC"}  # fmt: skip
# Balises qui parlent de toi, de l'appareil ou du lieu (TIFF/EXIF) ; les autres décrivent seulement l'image.
BALISES_SENSIBLES = frozenset({0x010E, 0x010F, 0x0110, 0x0131, 0x0132, 0x013B, 0x8298, 0x8769, 0x8825, 0x02BC, 0x83BB,
                               0x8649, 0x9C9B, 0x9C9C, 0x9C9D, 0x9C9E, 0x9C9F, 0xA005, 0x927C, 0xC4A5})  # fmt: skip
BALISES_STRUCTURE = frozenset({0x00FE, 0x0100, 0x0101, 0x0102, 0x0103, 0x0106, 0x010A, 0x0111, 0x0112, 0x0115,
                               0x0116, 0x0117, 0x011A, 0x011B, 0x011C, 0x0128, 0x013D, 0x0140, 0x0142, 0x0143,
                               0x0144, 0x0145, 0x0152, 0x0153, 0x8773})  # fmt: skip
_EXIFTOOL_SENSIBLES = ("GPS", "Make", "Model", "SerialNumber", "Artist", "Author", "Creator", "Copyright",
                       "Software", "OwnerName", "LastModifiedBy", "Company", "XMP", "IPTC", "MakerNote")  # fmt: skip


def restants_image(donnees: bytes, garder_date: bool) -> list[str]:
    ouvrir_heif()
    restes: list[str] = []
    for marque, nom in _MARQUES.items():
        if marque in donnees and nom not in restes:
            restes.append(nom)
    with Image.open(io.BytesIO(donnees)) as img:
        exif = img.getexif()
        # Un TIFF garde ses balises de structure (taille, compression…) : seules les balises qui disent quelque chose
        # de toi ou de l'appareil comptent.
        sensibles = [t for t in exif if t in BALISES_SENSIBLES or (t not in BALISES_STRUCTURE and img.format != "TIFF")]
        if IFD_EXIF in exif:
            detail = set(exif.get_ifd(IFD_EXIF))
            if detail - ({TAG_DATE_ORIGINE} if garder_date else set()):
                sensibles.append(IFD_EXIF)
            elif garder_date and IFD_EXIF in sensibles:
                sensibles.remove(IFD_EXIF)
        if sensibles:
            restes.append("données EXIF")
        if img.info.get("xmp") and "données XMP" not in restes:
            restes.append("données XMP")
        for cle in ("Author", "Comment", "Software", "Creation Time", "Description", "Title"):
            if img.info.get(cle):
                restes.append(f"texte « {cle} »")
    return restes


def restants_pdf(donnees: bytes) -> list[str]:
    import pikepdf

    restes = []
    with pikepdf.open(io.BytesIO(donnees)) as pdf:
        if len(pdf.docinfo):
            restes.append("informations du document")
        if "/Metadata" in pdf.Root:
            restes.append("données XMP")
        if any("/T" in a for page in pdf.pages for a in page.get("/Annots", [])):
            restes.append("auteurs des annotations")
    return restes


def restants_office(donnees: bytes) -> list[str]:
    from bouclier.metadonnees.formats import office

    with zipfile.ZipFile(io.BytesIO(donnees)) as z:
        z.testzip()
    return office.lire(donnees)[0]


def valeurs_restantes(donnees: bytes, valeurs: list[str]) -> list[str]:
    """Les valeurs vues avant (« Camille Exemple », numéro de série…) retrouvées telles quelles dans les octets."""
    return [v for v in valeurs if len(v) >= 4 and (v.encode() in donnees or v.encode("utf-16-le") in donnees)]


def exiftool(chemin: Path) -> list[str] | None:
    """Relecture par exiftool, s'il est installé (None sinon)."""
    programme = shutil.which("exiftool")
    if not programme:
        return None
    try:
        r = subprocess.run([programme, "-j", "-G1", "-a", str(chemin)], capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout or "[{}]")[0]
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, IndexError):
        return None
    return sorted({k for k in data if any(s.lower() in k.lower() for s in _EXIFTOOL_SENSIBLES)
                   and not k.startswith(("System:", "File:", "ExifTool:", "Composite:"))})  # fmt: skip
