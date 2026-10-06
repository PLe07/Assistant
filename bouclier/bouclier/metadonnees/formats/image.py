"""Photos : JPEG, PNG, WebP, TIFF, HEIC.

Principe : on garde les pixels et le profil couleur (ICC), on retire tout le reste (EXIF dont la position GPS,
l'appareil et son numéro de série, XMP, IPTC, notes du fabricant, commentaires, vignettes, images annexes).

- JPEG, PNG, WebP **sans rotation à appliquer** : nettoyage sans perte, segment par segment (les pixels ne sont
  pas recompressés).
- Photo **tournée** par la balise d'orientation (ex. 6 = « tourner de 90° ») : la rotation est appliquée aux pixels
  AVANT de retirer la balise (sinon la photo serait de travers), puis l'image est réenregistrée en haute qualité.
- TIFF et HEIC : réenregistrés à partir des pixels (haute qualité), profil ICC conservé.
- Option « garder la date de prise de vue » : une seule information EXIF est remise, la date.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

TAG_ORIENTATION = 0x0112
TAG_DATE_ORIGINE = 0x9003
IFD_EXIF = 0x8769


@dataclass
class ResultatImage:
    donnees: bytes
    sans_perte: bool
    notes: list[str] = field(default_factory=list)


def ouvrir_heif() -> bool:
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        return True
    except ImportError:  # pragma: no cover - dépendance du projet
        return False


def format_image(donnees: bytes) -> str | None:
    if donnees[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if donnees[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if donnees[:4] == b"RIFF" and donnees[8:12] == b"WEBP":
        return "webp"
    if donnees[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if donnees[4:8] == b"ftyp" and donnees[8:12] in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim"):
        return "heic"
    return None


def orientation(img: Image.Image) -> int:
    try:
        return int(img.getexif().get(TAG_ORIENTATION, 1) or 1)
    except Exception:  # noqa: BLE001 - un EXIF abîmé : pas de rotation connue
        return 1


def date_origine(img: Image.Image) -> str | None:
    try:
        exif = img.getexif()
        valeur = exif.get_ifd(IFD_EXIF).get(TAG_DATE_ORIGINE) or exif.get(0x0132)
        return str(valeur) if valeur else None
    except Exception:  # noqa: BLE001
        return None


def exif_date_seule(date: str) -> bytes:
    """Un EXIF qui ne contient que la date de prise de vue."""
    exif = Image.Exif()
    exif.get_ifd(IFD_EXIF)[TAG_DATE_ORIGINE] = date
    return exif.tobytes()


# --- JPEG sans perte ------------------------------------------------------------------------------------------------


def _segments_jpeg(donnees: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """(segments avant l'image : (marqueur, octets complets), image compressée jusqu'à la fin EOI comprise)."""
    if donnees[:2] != b"\xff\xd8":
        raise ValueError("pas un JPEG")
    i, segments = 2, list[tuple[int, bytes]]()
    while i < len(donnees):
        if donnees[i] != 0xFF:
            raise ValueError("JPEG abîmé")
        marqueur = donnees[i + 1]
        if marqueur == 0xFF:
            i += 1
            continue
        if marqueur == 0xDA:  # début de l'image : on cherche la fin (EOI) en sautant les données compressées
            fin = _fin_image(donnees, i)
            return segments, donnees[i:fin]
        longueur = struct.unpack(">H", donnees[i + 2 : i + 4])[0]
        segments.append((marqueur, donnees[i : i + 2 + longueur]))
        i += 2 + longueur
    raise ValueError("JPEG sans image")


def _fin_image(donnees: bytes, i: int) -> int:
    """La position juste après le premier EOI ; tout ce qui suit (images annexes MPF et leurs EXIF) est jeté."""
    j = i
    while j < len(donnees) - 1:
        if donnees[j] == 0xFF:
            suivant = donnees[j + 1]
            if suivant == 0xD9:
                return j + 2
            if suivant == 0x00 or 0xD0 <= suivant <= 0xD7 or suivant == 0xFF:
                j += 2 if suivant != 0xFF else 1
                continue
            longueur = struct.unpack(">H", donnees[j + 2 : j + 4])[0]  # DHT, SOS… d'un JPEG progressif
            j += 2 + longueur
            continue
        j += 1
    return len(donnees)


def _garder_segment_jpeg(marqueur: int, octets: bytes) -> bool:
    if marqueur == 0xE0:  # JFIF
        return octets[4:9] == b"JFIF\x00"
    if marqueur == 0xE2:  # seulement le profil couleur (pas MPF : images annexes)
        return octets[4:16] == b"ICC_PROFILE\x00"
    if marqueur == 0xEE:  # Adobe (transformation des couleurs)
        return octets[4:9] == b"Adobe"
    if 0xE0 <= marqueur <= 0xEF or marqueur == 0xFE:  # autres APPn (EXIF, XMP, IPTC, fabricants), commentaires
        return False
    return True  # tables de quantification, de Huffman, SOF…


def jpeg_sans_perte(donnees: bytes, date: str | None = None) -> bytes:
    segments, image = _segments_jpeg(donnees)
    gardes = [octets for marqueur, octets in segments if _garder_segment_jpeg(marqueur, octets)]
    if date:
        exif = b"Exif\x00\x00" + exif_date_seule(date)
        position = 1 if gardes and gardes[0][1] == 0xE0 else 0  # juste après JFIF, s'il est là
        gardes.insert(position, b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif)
    return b"\xff\xd8" + b"".join(gardes) + image


# --- PNG sans perte -------------------------------------------------------------------------------------------------

_PNG_GARDES = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"cHRM", b"gAMA", b"iCCP", b"sBIT", b"sRGB", b"bKGD",
               b"pHYs", b"hIST", b"cICP", b"mDCv", b"cLLi", b"acTL", b"fcTL", b"fdAT"}  # fmt: skip


def png_sans_perte(donnees: bytes) -> bytes:
    sortie, i = [donnees[:8]], 8
    while i + 8 <= len(donnees):
        longueur = struct.unpack(">I", donnees[i : i + 4])[0]
        genre = donnees[i + 4 : i + 8]
        morceau = donnees[i : i + 12 + longueur]
        if genre in _PNG_GARDES:
            sortie.append(morceau)
        i += 12 + longueur
        if genre == b"IEND":
            break
    return b"".join(sortie)


# --- WebP sans perte ------------------------------------------------------------------------------------------------


def webp_sans_perte(donnees: bytes) -> bytes:
    morceaux, i = [], 12
    while i + 8 <= len(donnees):
        genre = donnees[i : i + 4]
        taille = struct.unpack("<I", donnees[i + 4 : i + 8])[0]
        bloc = donnees[i : i + 8 + taille + (taille & 1)]
        if genre == b"VP8X":
            drapeaux = bloc[8] & ~(0x08 | 0x04)  # plus d'EXIF ni de XMP
            bloc = bloc[:8] + bytes([drapeaux]) + bloc[9:]
        if genre not in (b"EXIF", b"XMP "):
            morceaux.append(bloc)
        i += 8 + taille + (taille & 1)
    corps = b"WEBP" + b"".join(morceaux)
    return b"RIFF" + struct.pack("<I", len(corps)) + corps


# --- Réenregistrement à partir des pixels ---------------------------------------------------------------------------


def _reenregistrer(img: Image.Image, genre: str, date: str | None, original: Image.Image) -> bytes:
    icc = original.info.get("icc_profile")
    options: dict[str, object] = {}
    if icc:
        options["icc_profile"] = icc
    if date and genre in ("jpeg", "webp", "tiff", "heic"):
        options["exif"] = exif_date_seule(date)
    sortie = io.BytesIO()
    if genre == "jpeg":
        if img.mode not in ("RGB", "L", "CMYK"):
            img = img.convert("RGB")
        img.save(sortie, "JPEG", quality=95, subsampling=0, optimize=True, **options)
    elif genre == "png":
        img.save(sortie, "PNG", optimize=True, **options)
    elif genre == "webp":
        img.save(sortie, "WEBP", lossless=original.info.get("lossless", False) or False, quality=95, **options)
    elif genre == "tiff":
        compression = original.info.get("compression", "tiff_lzw")
        img.save(sortie, "TIFF", compression=compression if compression != "raw" else None, **options)
    elif genre == "heic":
        img.save(sortie, "HEIF", quality=95, **options)
    return sortie.getvalue()


def nettoyer(donnees: bytes, genre: str, garder_date: bool = False) -> ResultatImage:
    if genre == "heic":
        ouvrir_heif()
    with Image.open(io.BytesIO(donnees)) as original:
        sens = orientation(original)
        date = date_origine(original) if garder_date else None
        animee = bool(getattr(original, "is_animated", False))
        if genre in ("jpeg", "png", "webp") and sens == 1 and not animee:
            if genre == "jpeg":
                return ResultatImage(jpeg_sans_perte(donnees, date), True)
            if genre == "png":
                return ResultatImage(png_sans_perte(donnees), True)
            if not date:
                return ResultatImage(webp_sans_perte(donnees), True)
        if animee:
            notes = ["image animée : seule la première image est gardée"]
        else:
            notes = []
        tournee = ImageOps.exif_transpose(original.copy()) if sens != 1 else original.copy()
        # Pillow et pillow-heif recopient sinon d'office ce qu'ils trouvent ici (commentaire, EXIF, XMP…).
        tournee.info.clear()
        if sens != 1:
            notes.append("photo remise à l'endroit (rotation appliquée)")
        return ResultatImage(_reenregistrer(tournee, genre, date, original), False, notes)


def extension_pour(genre: str) -> str:
    return {"jpeg": ".jpg", "png": ".png", "webp": ".webp", "tiff": ".tif", "heic": ".heic"}[genre]


def est_image(chemin: Path) -> bool:
    try:
        with chemin.open("rb") as f:
            return format_image(f.read(32)) is not None
    except OSError:
        return False
