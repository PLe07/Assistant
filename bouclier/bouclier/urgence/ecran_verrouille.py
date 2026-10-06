"""L'image d'écran verrouillé « En cas d'urgence : … », aux dimensions des iPhone récents (1179 × 2556 : iPhone 14
Pro, 15, 15 Pro, 16). Le texte est placé au milieu, loin de l'heure (en haut) et des boutons (en bas)."""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bouclier.urgence.fiche import Fiche

TAILLE = (1179, 2556)
POLICES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _police(taille: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for chemin in POLICES:
        if Path(chemin).exists():
            try:
                return ImageFont.truetype(chemin, taille)
            except OSError:
                continue
    return ImageFont.load_default(size=taille)


def texte_ecran(fiche: Fiche) -> str | None:
    i = fiche.infos
    if i.ecran:
        return i.ecran
    if i.contacts and i.contacts[0].telephone:
        c = i.contacts[0]
        return f"En cas d'urgence : appeler {c.nom + ' au ' if c.nom else 'le '}{c.telephone}"
    return None


def image(fiche: Fiche) -> bytes | None:
    """None si tu n'as indiqué ni texte ni contact (l'image n'aurait rien de personnel à dire)."""
    texte = texte_ecran(fiche)
    if texte is None:
        return None
    img = Image.new("RGB", TAILLE, (17, 17, 22))
    d = ImageDraw.Draw(img)
    grand, moyen = _police(78), _police(46)
    par_id = {ligne.id: ligne for ligne in fiche.lignes()}
    principaux = (("samu", "SAMU"), ("pompiers", "Pompiers"), ("urgence-europe", "Europe"))
    urgences = [f"{n} {par_id[i].valeur}" for i, n in principaux if i in par_id]
    lignes = [(ligne, grand, (255, 255, 255), 98) for ligne in textwrap.wrap(texte, 24)]
    lignes += [(" · ".join(urgences), moyen, (255, 230, 230), 64)] if urgences else []
    largeur_max = TAILLE[0] - 2 * 110
    for i, (ligne, police, couleur, pas) in enumerate(lignes):  # une ligne trop large rétrécit
        taille = 46 if police is moyen else 78
        while d.textlength(ligne, font=police) > largeur_max and taille > 24:
            taille -= 2
            police = _police(taille)
        lignes[i] = (ligne, police, couleur, pas)
    hauteur_texte = sum(pas for *_, pas in lignes) + 30
    haut = 1450
    d.rounded_rectangle((70, haut - 60, TAILLE[0] - 70, haut + hauteur_texte + 40), radius=48, fill=(150, 25, 25))
    y = haut
    for n, (ligne, police, couleur, pas) in enumerate(lignes):
        if n and police is not lignes[n - 1][1] and pas == 64:
            y += 30
        d.text((TAILLE[0] // 2, y), ligne, font=police, fill=couleur, anchor="ma")
        y += pas
    sortie = io.BytesIO()
    img.save(sortie, "PNG")
    return sortie.getvalue()
