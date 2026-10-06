"""La fiche urgence en PDF (A4), lisible sans réseau, à garder téléchargée dans l'app Fichiers de l'iPhone."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from bouclier.urgence.fiche import Fiche, mention_verification

ROUGE = colors.HexColor("#b71c1c")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=base["Title"], fontSize=20, spaceAfter=2, alignment=0),
        "doux": ParagraphStyle("doux", parent=base["Normal"], fontSize=8.5, textColor=colors.HexColor("#555555")),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=13, textColor=ROUGE, spaceBefore=8, spaceAfter=3),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=10.5, spaceBefore=4, spaceAfter=1),
        "texte": ParagraphStyle("texte", parent=base["Normal"], fontSize=9.5, leading=12),
        "num": ParagraphStyle("num", parent=base["Normal"], fontSize=13, leading=15, fontName="Helvetica-Bold"),
    }


def _table(lignes: list[tuple[str, str]], s: dict[str, ParagraphStyle]) -> Table:
    cellules = [
        [Paragraph(escape(numero), s["num"]), Paragraph(escape(libelle), s["texte"])] for numero, libelle in lignes
    ]
    t = Table(cellules, colWidths=[45 * mm, 125 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)]))  # fmt: skip
    return t


def pdf(fiche: Fiche) -> bytes:
    s = _styles()
    titre = "Fiche urgence" + (f" — {fiche.infos.nom}" if fiche.infos.nom else "")
    elements: list[object] = [
        Paragraph(escape(titre), s["titre"]),
        Paragraph(escape(mention_verification(fiche)), s["doux"]),
    ]
    for titre_groupe, lignes in fiche.groupes:
        elements.append(Paragraph(escape(titre_groupe), s["h2"]))
        elements.append(_table([(x.valeur, x.libelle + (" (payant)" if x.payant else "")) for x in lignes], s))
    i = fiche.infos
    mes = [(c.telephone, c.nom or "Contact") for c in i.contacts]
    if i.operateur_tel:
        mes.append((i.operateur_tel, f"Mon opérateur{f' ({i.operateur})' if i.operateur else ''} : suspendre la ligne"))
    if i.banque_tel:
        mes.append((i.banque_tel, f"Ma banque{f' ({i.banque})' if i.banque else ''} : carte perdue ou volée"))
    if mes:
        elements += [Paragraph("Mes contacts", s["h2"]), _table(mes, s)]
    elements.append(Paragraph("Réflexes pas à pas", s["h2"]))
    for titre_situation, etapes in fiche.situations:
        elements.append(Paragraph(escape(titre_situation), s["h3"]))
        elements.append(ListFlowable([ListItem(Paragraph(escape(e), s["texte"]), leftIndent=12) for e in etapes],
                                     bulletType="1", leftIndent=12, bulletFontSize=9))  # fmt: skip
    elements += [Spacer(1, 4 * mm), Paragraph("Données de santé : utilise la « Fiche médicale » de l'app Santé de"
                                              " l'iPhone (visible depuis l'écran verrouillé).", s["doux"])]  # fmt: skip
    elements.append(Paragraph("Sources officielles", s["h2"]))
    for src in fiche.sources_utilisees:
        elements.append(Paragraph(escape(f"{src.editeur} : {src.url}"), s["doux"]))
    elements.append(Paragraph(escape(f"Générée par Bouclier le {fiche.generee_le.strftime('%d/%m/%Y')}. À relire"
                                     " tous les 6 mois."), s["doux"]))  # fmt: skip
    sortie = io.BytesIO()
    marges = {"leftMargin": 18 * mm, "rightMargin": 18 * mm, "topMargin": 15 * mm, "bottomMargin": 15 * mm}
    doc = SimpleDocTemplate(sortie, pagesize=A4, title="Fiche urgence", author="", creator="", producer="Bouclier",
                            **marges)  # fmt: skip
    doc.build(elements)
    return sortie.getvalue()
