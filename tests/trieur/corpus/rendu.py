"""Dessiner un document : PDF texte (plusieurs mises en page), scan dégradé, photo de ticket, HEIC, et les pièges.

Tout est déterministe (même graine, mêmes octets) : les doublons sont exacts et l'OCR peut être mis en cache.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from tests.trieur.corpus.modele import Doc

# Les polices de base des PDF (sans fichier, sur Linux comme sur le Mac) ne couvrent que l'encodage Windows-1252.
_REMPLACER = {"→": "-", " ": " ", "’": "'", "≤": "<=", "≥": ">="}


def _propre(texte: str) -> str:
    for a, b in _REMPLACER.items():
        texte = texte.replace(a, b)
    return texte.encode("cp1252", "replace").decode("cp1252")


def _logo_png(texte: str, couleur: tuple[float, float, float]) -> bytes:
    """Le nom de l'émetteur dessiné comme une image : il n'existe pas en texte dans le PDF."""
    import pymupdf

    doc = pymupdf.open()
    largeur = max(260.0, pymupdf.get_text_length(texte, fontname="hebo", fontsize=26) + 28)
    page = doc.new_page(width=largeur, height=60)
    page.draw_rect(page.rect, color=couleur, fill=couleur)
    page.insert_text((14, 40), texte, fontsize=26, fontname="hebo", color=(1, 1, 1))
    png = page.get_pixmap(dpi=150).tobytes("png")
    doc.close()
    return bytes(png)


def pdf_texte(doc: Doc, chemin: Path, mise_en_page: str, r: random.Random) -> None:
    from reportlab import rl_config
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    rl_config.invariant = 1
    if doc.ticket:
        _ticket_pdf(doc, chemin)
        return
    police = {"classique": "Helvetica", "moderne": "Helvetica", "logo": "Helvetica", "lettre": "Times-Roman",
              "colonnes": "Helvetica", "compact": "Courier", "serif": "Times-Roman"}[mise_en_page]  # fmt: skip
    gras = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[police]
    largeur, hauteur = A4
    c = canvas.Canvas(str(chemin), pagesize=A4, invariant=1)
    c.setTitle(_propre(doc.titre)[:60] or "Document")
    y = hauteur - 50
    couleur = r.choice([(0.85, 0.35, 0.1), (0.1, 0.3, 0.6), (0.2, 0.5, 0.3), (0.5, 0.1, 0.3)])

    def ligne(texte: str, x: float, taille: float = 10, fonte: str = police) -> None:
        nonlocal y
        c.setFont(fonte, taille)
        c.drawString(x, y, _propre(texte))
        y -= taille * 1.45

    # L'en-tête : l'émetteur.
    if doc.entete:
        if mise_en_page == "moderne":
            c.setFillColorRGB(*couleur)
            c.rect(0, hauteur - 80, largeur, 80, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1)
            c.setFont(gras, 22)
            c.drawString(40, hauteur - 50, _propre(doc.entete[0]))
            c.setFont(police, 8)
            for i, t in enumerate(doc.entete[1:3]):
                c.drawString(40, hauteur - 66 - 10 * i, _propre(t))
            c.setFillColorRGB(0, 0, 0)
            y = hauteur - 110
        elif mise_en_page == "logo":
            logo = ImageReader(io.BytesIO(_logo_png(_propre(doc.entete[0]), couleur)))
            lw, lh = logo.getSize()
            c.drawImage(logo, 40, hauteur - 100, 46 * lw / lh, 46)
            y = hauteur - 115
            for t in doc.entete[1:]:
                ligne(t, 40, 8)
        elif mise_en_page == "colonnes":
            c.setFont(gras, 16)
            c.drawRightString(largeur - 40, y, _propre(doc.entete[0]))
            y -= 18
            for t in doc.entete[1:]:
                c.setFont(police, 8)
                c.drawRightString(largeur - 40, y, _propre(t))
                y -= 11
        else:
            ligne(doc.entete[0], 40, 18 if mise_en_page != "compact" else 13, gras)
            for t in doc.entete[1:]:
                ligne(t, 40, 8)
    # Le destinataire, à droite.
    if doc.destinataire:
        yd = hauteur - 140
        for t in doc.destinataire:
            c.setFont(police, 10)
            c.drawString(largeur - 230, yd, _propre(t))
            yd -= 13
        y = min(y, yd) - 10
    else:
        y -= 10
    # Lieu et date d'un courrier, en haut à droite.
    meta = list(doc.meta)
    if doc.lettre and meta and meta[0][0] == "":
        c.setFont(police, 10)
        c.drawRightString(largeur - 40, y, _propre(meta.pop(0)[1]))
        y -= 26
    if doc.titre:
        c.setFont(gras, 14)
        if doc.lettre:
            c.drawString(40, y, _propre(doc.titre))
        else:
            c.drawCentredString(largeur / 2, y, _propre(doc.titre))
        y -= 26
    for etiquette, valeur in meta:
        texte = f"{etiquette} : {valeur}" if etiquette else valeur
        if mise_en_page == "colonnes" and etiquette:
            c.setFont(police, 9)
            c.drawString(40, y, _propre(etiquette))
            c.drawString(200, y, _propre(valeur))
            y -= 13
        else:
            ligne(texte, 40, 10)
    y -= 8
    # Le tableau.
    if doc.tableau:
        colonnes = len(doc.tableau[0])
        xs = [40] + [40 + 300 + i * ((largeur - 380) / max(1, colonnes - 1)) for i in range(colonnes - 1)]
        if colonnes == 2:
            xs = [40, largeur - 140]
        for i, rang in enumerate(doc.tableau):
            c.setFont(gras if i == 0 else police, 9)
            for x, cellule in zip(xs, rang, strict=False):
                c.drawString(x, y, _propre(cellule)[:60])
            if i == 0 and mise_en_page in ("classique", "logo"):
                c.line(40, y - 4, largeur - 40, y - 4)
            y -= 15
            if y < 120:
                c.showPage()
                y = hauteur - 60
        y -= 8
    for etiquette, valeur in doc.totaux:
        c.setFont(gras if etiquette == doc.totaux[-1][0] else police, 11)
        c.drawRightString(largeur - 160, y, _propre(etiquette))
        c.drawRightString(largeur - 40, y, _propre(valeur))
        y -= 16
    y -= 10
    for p in doc.paragraphes:
        for morceau in _couper(p, 95 if police != "Courier" else 80):
            ligne(morceau, 40, 10)
        y -= 4
    c.setFont(police, 7)
    for i, t in enumerate(doc.pied):
        c.drawCentredString(largeur / 2, 40 - 9 * i + 9 * (len(doc.pied) - 1), _propre(t))
    c.save()


def _couper(texte: str, largeur: int) -> list[str]:
    mots, lignes, courante = texte.split(), [], ""
    for m in mots:
        if len(courante) + len(m) + 1 > largeur:
            lignes.append(courante)
            courante = m
        else:
            courante = f"{courante} {m}".strip()
    if courante:
        lignes.append(courante)
    return lignes


def _ticket_pdf(doc: Doc, chemin: Path) -> None:
    from reportlab.pdfgen import canvas

    lignes: list[tuple[str, str, bool]] = []  # (gauche, droite, gras)
    for t in doc.entete:
        lignes.append((t, "", True))
    if doc.titre:
        lignes.append((doc.titre, "", False))
    lignes.append(("", "", False))
    for etiquette, valeur in doc.meta:
        lignes.append((f"{etiquette} {valeur}".strip(), "", False))
    lignes.append(("-" * 34, "", False))
    for rang in doc.tableau[1:]:
        lignes.append((rang[0], rang[-1], False))
    lignes.append(("-" * 34, "", False))
    for etiquette, valeur in doc.totaux:
        lignes.append((etiquette, valeur, True))
    lignes.append(("", "", False))
    for p in doc.paragraphes + doc.pied:
        lignes.append((p, "", False))
    largeur, hauteur = 230, 30 + 13 * len(lignes)
    c = canvas.Canvas(str(chemin), pagesize=(largeur, hauteur), invariant=1)
    y = hauteur - 22
    for gauche, droite, gras in lignes:
        c.setFont("Courier-Bold" if gras else "Courier", 8.5)
        c.drawString(10, y, _propre(gauche)[:36])
        if droite:
            c.drawRightString(largeur - 10, y, _propre(droite))
        y -= 13
    c.save()


# --- images ----------------------------------------------------------------------------------------------------


def page_en_image(pdf: Path, dpi: int = 150) -> Image.Image:
    import pymupdf

    with pymupdf.open(pdf) as d:
        pix = d[0].get_pixmap(dpi=dpi)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def degrader(img: Image.Image, r: random.Random, force: float = 1.0) -> Image.Image:
    """Un scan : de travers (± 7°), flou, bruit, contraste faible."""
    gris = img.convert("L")
    angle = r.uniform(-7, 7) * force
    gris = gris.rotate(angle, expand=True, fillcolor=r.randint(225, 250), resample=Image.Resampling.BICUBIC)
    gris = gris.filter(ImageFilter.GaussianBlur(r.uniform(0.3, 1.0) * force))
    gris = ImageEnhance.Contrast(gris).enhance(1 - r.uniform(0.15, 0.4) * force)
    tableau = np.asarray(gris, dtype=np.float32)
    bruit = np.random.default_rng(r.randint(0, 10**6)).normal(0, 9 * force, tableau.shape)
    return Image.fromarray(np.clip(tableau + bruit, 0, 255).astype(np.uint8)).convert("RGB")


def photo_ticket(ticket_pdf: Path, r: random.Random) -> Image.Image:
    """Un ticket thermique photographié sur une table : de travers, une ombre, un fond."""
    ticket = page_en_image(ticket_pdf, dpi=220).convert("L")
    ticket = ImageEnhance.Contrast(ticket).enhance(0.75)  # le papier thermique pâlit
    fond_l, fond_h = int(ticket.width * 1.6), int(ticket.height * 1.25)
    fond = Image.new("L", (fond_l, fond_h), r.randint(70, 120))
    tableau = np.asarray(fond, dtype=np.float32) + np.random.default_rng(r.randint(0, 10**6)).normal(
        0, 12, (fond_h, fond_l)
    )
    fond = Image.fromarray(np.clip(tableau, 0, 255).astype(np.uint8))
    ticket = ticket.rotate(r.uniform(-6, 6), expand=True, fillcolor=0, resample=Image.Resampling.BICUBIC)
    masque = ticket.point(lambda v: 255 if v > 8 else 0)
    fond.paste(ticket, ((fond_l - ticket.width) // 2, (fond_h - ticket.height) // 2), masque)
    ombre = Image.linear_gradient("L").resize((fond_l, fond_h)).rotate(r.choice([90, -90, 0, 180]), expand=False)
    ombre = ombre.point(lambda v: int(255 - v * 0.35))
    photo = Image.composite(fond, Image.new("L", fond.size, 0), ombre).filter(ImageFilter.GaussianBlur(0.6))
    return photo.convert("RGB")


def avec_orientation_exif(img: Image.Image, chemin: Path, qualite: int = 85) -> None:
    """Enregistre l'image tournée de 90° avec l'étiquette EXIF qui dit de la remettre droite (comme un iPhone)."""
    exif = Image.Exif()
    exif[0x0112] = 6  # « tourner de 90° dans le sens horaire pour afficher »
    img.rotate(90, expand=True).save(chemin, "JPEG", quality=qualite, exif=exif)


def en_pdf_image(img: Image.Image, chemin: Path) -> None:
    """Un scan livré en PDF : une page qui ne contient qu'une image, sans texte."""
    import pymupdf

    tampon = io.BytesIO()
    img.save(tampon, "JPEG", quality=80)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=tampon.getvalue())
    doc.save(chemin, garbage=3, deflate=True, no_new_id=True)
    doc.close()


def en_heic(img: Image.Image, chemin: Path) -> bool:
    """Un HEIC (pillow-heif hors Mac, sips sur le Mac). False si aucun des deux n'est là."""
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        img.save(chemin, "HEIF", quality=80)
        return True
    except ImportError:
        pass
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("sips"):
        return False
    with tempfile.TemporaryDirectory() as d:
        jpg = Path(d) / "x.jpg"
        img.save(jpg, "JPEG", quality=90)
        subprocess.run(
            ["sips", "-s", "format", "heic", str(jpg), "--out", str(chemin)], capture_output=True, check=True
        )
    return chemin.exists()


def paysage(r: random.Random) -> Image.Image:
    """Une photo de vacances : ciel, soleil, montagnes, lac. Aucun texte."""
    larg, h = 1600, 1200
    img = Image.new("RGB", (larg, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (larg, y)], fill=(int(90 + 120 * t), int(150 + 70 * t), int(230 - 60 * t)))
    d.ellipse([1150, 120, 1330, 300], fill=(255, 230, 150))
    for i in range(4):
        x0 = r.randint(-200, 1200)
        d.polygon([(x0, 900), (x0 + 350 + 60 * i, 380 + 50 * i), (x0 + 800, 900)], fill=(70 + 20 * i, 90 + 15 * i, 80))
    d.rectangle([0, 880, larg, h], fill=(40, 90, 130))
    tableau = np.asarray(img, dtype=np.float32) + np.random.default_rng(r.randint(0, 10**6)).normal(0, 6, (h, larg, 3))
    return Image.fromarray(np.clip(tableau, 0, 255).astype(np.uint8))


# --- pièges ----------------------------------------------------------------------------------------------------


def pdf_protege(source: Path, chemin: Path) -> None:
    import pymupdf

    with pymupdf.open(source) as d:
        d.save(chemin, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="motdepasse", owner_pw="proprietaire")


def pdf_corrompu(source: Path, chemin: Path) -> None:
    donnees = source.read_bytes()
    chemin.write_bytes(donnees[: len(donnees) * 2 // 5])


def pdf_300_pages(premiere: Path, chemin: Path) -> None:
    import pymupdf

    doc = pymupdf.open(premiere)
    for i in range(299):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 80), f"Conditions générales de vente — article {i + 1}", fontsize=12)
        page.insert_text(
            (50, 110), "Les présentes conditions s'appliquent à toute commande passée sur le site.", fontsize=9
        )
    doc.save(chemin, garbage=3, deflate=True, no_new_id=True)
    doc.close()


def courriel_avec_piece_jointe(pdf: Path, nom_piece: str, expediteur: str, chemin: Path) -> None:
    from datetime import datetime, timezone
    from email.message import EmailMessage
    from email.utils import format_datetime

    m = EmailMessage()
    m["From"] = expediteur
    m["To"] = "moi@exemple-mail.fr"
    m["Subject"] = "Votre facture est disponible"
    m["Date"] = format_datetime(datetime(2026, 9, 14, 10, 32, tzinfo=timezone.utc))
    m.set_content("Bonjour,\n\nVous trouverez ci-joint la facture de votre commande.\n\nÀ bientôt.\n")
    m.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=nom_piece)
    chemin.write_bytes(bytes(m))
