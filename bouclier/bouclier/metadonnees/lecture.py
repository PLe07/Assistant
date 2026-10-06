"""Ce qu'une photo révèle avant nettoyage, dit simplement : « position GPS (Bordeaux), appareil (Apple iPhone 15),
numéro de série, auteur… ». Le lieu est trouvé sans réseau, dans une petite liste de villes françaises."""

from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image

from bouclier.metadonnees.formats.image import IFD_EXIF, ouvrir_heif

IFD_GPS = 0x8825
# Villes françaises (latitude, longitude approximatives du centre).
VILLES = (
    ("Paris", 48.857, 2.352), ("Marseille", 43.296, 5.370), ("Lyon", 45.764, 4.836), ("Toulouse", 43.605, 1.444),
    ("Nice", 43.710, 7.262), ("Nantes", 47.218, -1.554), ("Montpellier", 43.611, 3.877),
    ("Strasbourg", 48.573, 7.752), ("Bordeaux", 44.838, -0.579), ("Lille", 50.629, 3.057), ("Rennes", 48.117, -1.678),
    ("Reims", 49.258, 4.032), ("Toulon", 43.124, 5.928), ("Saint-Étienne", 45.440, 4.387), ("Le Havre", 49.494, 0.108),
    ("Grenoble", 45.188, 5.724), ("Dijon", 47.322, 5.041), ("Angers", 47.478, -0.563), ("Nîmes", 43.837, 4.360),
    ("Clermont-Ferrand", 45.778, 3.087), ("Le Mans", 48.006, 0.199), ("Aix-en-Provence", 43.529, 5.447),
    ("Brest", 48.390, -4.486), ("Tours", 47.394, 0.685), ("Amiens", 49.894, 2.296), ("Limoges", 45.834, 1.262),
    ("Annecy", 45.899, 6.129), ("Perpignan", 42.699, 2.895), ("Metz", 49.119, 6.176), ("Besançon", 47.238, 6.024),
    ("Orléans", 47.903, 1.909), ("Rouen", 49.443, 1.100), ("Caen", 49.183, -0.371), ("Nancy", 48.692, 6.184),
    ("Avignon", 43.949, 4.806), ("Poitiers", 46.580, 0.340), ("La Rochelle", 46.160, -1.151), ("Pau", 43.295, -0.371),
    ("Bayonne", 43.493, -1.475), ("Biarritz", 43.483, -1.559), ("Arcachon", 44.659, -1.168),
    ("Mérignac", 44.842, -0.646), ("Pessac", 44.806, -0.631), ("Périgueux", 45.184, 0.721),
    ("Angoulême", 45.648, 0.156), ("Agen", 44.203, 0.616), ("Mont-de-Marsan", 43.893, -0.500),
    ("Libourne", 44.915, -0.244), ("Ajaccio", 41.919, 8.738), ("Bastia", 42.697, 9.450),
)  # fmt: skip


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def lieu(lat: float, lon: float) -> str:
    ville, d = min(((v, _km(lat, lon, la, lo)) for v, la, lo in VILLES), key=lambda x: x[1])
    if d <= 10:
        return ville
    if d <= 30:
        return f"près de {ville}"
    return f"{abs(lat):.2f} {'N' if lat >= 0 else 'S'}, {abs(lon):.2f} {'E' if lon >= 0 else 'O'}".replace(".", ",")


def _degres(valeur: Any, ref: Any) -> float | None:
    try:
        d, m, s = (float(x) for x in valeur)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    signe = -1 if str(ref).upper().startswith(("S", "W")) else 1
    return signe * (d + m / 60 + s / 3600)


def position(gps: dict[int, Any]) -> tuple[float, float] | None:
    lat, lon = _degres(gps.get(2), gps.get(1)), _degres(gps.get(4), gps.get(3))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    return lat, lon


def lire_image(donnees: bytes) -> list[str]:
    ouvrir_heif()
    trouves: list[str] = []
    try:
        img = Image.open(io.BytesIO(donnees))
        exif = img.getexif()
    except Exception:  # noqa: BLE001 - image illisible : la suite le dira
        return trouves
    gps = exif.get_ifd(IFD_GPS)
    if gps:
        pos = position(dict(gps))
        trouves.append(f"position GPS ({lieu(*pos)})" if pos else "position GPS")
    marque, modele = str(exif.get(0x010F) or "").strip(), str(exif.get(0x0110) or "").strip()
    if marque or modele:
        appareil = modele if marque and modele.lower().startswith(marque.lower()) else f"{marque} {modele}".strip()
        trouves.append(f"appareil ({appareil})")
    detail = exif.get_ifd(IFD_EXIF)
    if detail.get(0xA431) or detail.get(0xA435):
        trouves.append("numéro de série")
    if exif.get(0x013B) or exif.get(0x8298) or exif.get(0x9C9D) or img.info.get("Author"):
        trouves.append("auteur")
    if exif.get(0x0131) or img.info.get("Software"):
        trouves.append("logiciel")
    if detail.get(0x9003) or exif.get(0x0132) or img.info.get("Creation Time"):
        trouves.append("date de prise de vue")
    if detail.get(0x927C):
        trouves.append("notes du fabricant")
    if exif.get(0x010E) or detail.get(0x9286) or img.info.get("Comment") or img.info.get("Description"):
        trouves.append("description ou commentaire")
    if b"<x:xmpmeta" in donnees or b"http://ns.adobe.com/xap/1.0/" in donnees or img.info.get("xmp"):
        trouves.append("données XMP")
    if b"Photoshop 3.0\x008BIM" in donnees:
        trouves.append("données IPTC")
    if not trouves and len(exif):
        trouves.append("données EXIF")
    return trouves
