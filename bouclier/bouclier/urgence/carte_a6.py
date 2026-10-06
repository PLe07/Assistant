"""La carte A6 (10,5 × 14,8 cm) pour le portefeuille : une seule page, les numéros essentiels en gros."""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from bouclier.urgence.fiche import Fiche

ESSENTIELS = ("samu", "police", "pompiers", "urgence-europe", "urgence-sms", "opposition", "antipoison-bordeaux",
              "33700", "info-escroqueries")  # fmt: skip
COURTS = {"samu": "SAMU", "police": "Police", "pompiers": "Pompiers", "urgence-europe": "Urgence (Europe)",
          "urgence-sms": "Urgence par SMS", "opposition": "Opposition carte (payant)",
          "antipoison-bordeaux": "Antipoison Bordeaux", "33700": "SMS frauduleux",
          "info-escroqueries": "Info escroqueries"}  # fmt: skip


def lignes_carte(fiche: Fiche) -> list[tuple[str, str]]:
    par_id = {ligne.id: ligne for ligne in fiche.lignes()}
    lignes = [(par_id[i].valeur, COURTS[i]) for i in ESSENTIELS if i in par_id]
    for c in fiche.infos.contacts[:2]:
        lignes.append((c.telephone, c.nom or "Contact"))
    if fiche.infos.banque_tel:
        lignes.append((fiche.infos.banque_tel, "Ma banque (carte)"))
    return lignes


def pdf(fiche: Fiche) -> bytes:
    sortie = io.BytesIO()
    c = Canvas(sortie, pagesize=A6)
    c.setTitle("Carte urgence")
    c.setAuthor("")
    c.setCreator("Bouclier")
    largeur, hauteur = A6
    marge = 6 * mm
    bandeau = 20 * mm if fiche.infos.nom else 16 * mm
    c.setFillColor(colors.HexColor("#b71c1c"))
    c.rect(0, hauteur - bandeau, largeur, bandeau, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(marge, hauteur - 10.5 * mm, "EN CAS D'URGENCE")
    if fiche.infos.nom:
        nom, taille_nom = fiche.infos.nom, 10.0
        while c.stringWidth(nom, "Helvetica", taille_nom) > largeur - 2 * marge and taille_nom > 6:
            taille_nom -= 0.5
        c.setFont("Helvetica", taille_nom)
        c.drawString(marge, hauteur - 16.5 * mm, nom)
    lignes = lignes_carte(fiche)
    disponible = hauteur - bandeau - 14 * mm
    pas = min(9.5 * mm, disponible / max(1, len(lignes)))
    taille = max(7.0, min(13.0, pas / mm * 1.45))
    y = hauteur - bandeau - pas
    c.setFillColor(colors.black)
    for numero, libelle in lignes:
        c.setFont("Helvetica-Bold", taille)
        c.drawString(marge, y, numero)
        c.setFont("Helvetica", taille * 0.78)
        c.drawRightString(largeur - marge, y, libelle)
        c.setStrokeColor(colors.HexColor("#dddddd"))
        c.line(marge, y - pas * 0.35, largeur - marge, y - pas * 0.35)
        y -= pas
    c.setFont("Helvetica", 6.5)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(marge, 8 * mm, f"Numéros vérifiés sur les sites officiels — {fiche.generee_le.strftime('%d/%m/%Y')}")
    c.drawString(marge, 5 * mm, "Santé : Fiche médicale de l'app Santé de l'iPhone.")
    c.showPage()
    c.save()
    return sortie.getvalue()
