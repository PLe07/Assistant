"""Un document du corpus, décrit par blocs (avant d'être dessiné), et sa vérité terrain."""

from __future__ import annotations

import calendar
import random
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from tests.trieur.corpus.donnees import MOIS

MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


@dataclass
class Doc:
    entete: list[str]  # l'émetteur : nom puis adresse
    titre: str
    meta: list[tuple[str, str]] = field(default_factory=list)  # « Date de facture : 03/10/2026 »
    destinataire: list[str] = field(default_factory=list)
    tableau: list[list[str]] = field(default_factory=list)  # 1re ligne : les titres de colonnes
    totaux: list[tuple[str, str]] = field(default_factory=list)
    paragraphes: list[str] = field(default_factory=list)
    pied: list[str] = field(default_factory=list)  # mentions légales, SIRET, site
    logo_en_image: bool = False  # le nom de l'émetteur dessiné (pas de texte à extraire)
    ticket: bool = False  # ticket de caisse : étroit, police à chasse fixe
    lettre: bool = False  # courrier : lieu et date en haut à droite, « Objet : »


@dataclass
class Verite:
    fichier: str
    type: str | None  # None pour un piège qui n'est pas un document
    issue: str  # classe, photos, a_verifier, doublon, piece_jointe
    support: str  # pdf_texte, scan_pdf, scan_jpg, photo_ticket, heic, piege, eml
    emetteur: str | None = None
    date: str | None = None  # AAAA-MM-JJ
    montant: str | None = None  # « 249.99 »
    garanties: list[dict[str, str]] = field(default_factory=list)  # [{"produit", "fin", "source"}]
    retractation: str | None = None  # la date du rappel « fin du délai de rétractation » (AAAA-MM-JJ)
    sensible: bool = False
    note: str | None = None  # la note envoyée avec (variante « + note »)
    lot: str = ""
    accepte: list[str] = field(default_factory=list)  # d'autres issues acceptables (piège santé : classe ou à vérifier)

    def vers_dict(self) -> dict[str, Any]:
        return asdict(self)


def ajouter_mois(d: date, mois: int) -> date:
    """Le même jour, n mois plus tard ; le 29 février d'une année non bissextile devient le 28."""
    total = d.month - 1 + mois
    annee, m = d.year + total // 12, total % 12 + 1
    return date(annee, m, min(d.day, calendar.monthrange(annee, m)[1]))


def date_fr(d: date, r: random.Random, styles: list[str] | None = None) -> str:
    style = r.choice(styles or ["num", "num", "num", "tiret", "point", "long", "court", "iso", "an2"])
    if style == "num":
        return d.strftime("%d/%m/%Y")
    if style == "tiret":
        return d.strftime("%d-%m-%Y")
    if style == "point":
        return d.strftime("%d.%m.%Y")
    if style == "long":
        return f"{d.day} {MOIS[d.month - 1]} {d.year}"
    if style == "court":
        return f"{d.day:02d} {MOIS_COURTS[d.month - 1]} {d.year}"
    if style == "iso":
        return d.isoformat()
    return d.strftime("%d/%m/%y")


def milliers(entier: str, sep: str) -> str:
    morceaux = []
    while len(entier) > 3:
        morceaux.insert(0, entier[-3:])
        entier = entier[:-3]
    morceaux.insert(0, entier)
    return sep.join(morceaux)


def montant_fr(x: float, r: random.Random, styles: list[str] | None = None) -> str:
    entier, decimales = f"{x:.2f}".split(".")
    style = r.choice(styles or ["espace", "espace", "insecable", "colle", "point_milliers", "eur_avant", "eur_apres"])
    if style == "espace":
        return f"{milliers(entier, ' ')},{decimales} €"
    if style == "insecable":
        return f"{milliers(entier, chr(0xA0))},{decimales}\u00a0€"
    if style == "colle":
        return f"{entier},{decimales}€"
    if style == "point_milliers":
        return f"{milliers(entier, '.')},{decimales} €"
    if style == "eur_avant":
        return f"EUR {milliers(entier, ' ')},{decimales}"
    return f"{milliers(entier, ' ')},{decimales} EUR"


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def euros(x: float | None) -> str | None:
    return None if x is None else f"{x:.2f}"
