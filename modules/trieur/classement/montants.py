"""Les montants français : « 1 249,99 € », « 1.249,99 € », « 249,99€ », « EUR 249,99 », « 1 234 € » (espaces
insécables compris), et le montant TTC d'un document, d'après son étiquette (« Total TTC », « Net à payer »…).

Les lignes sont lues avec leurs colonnes (texte.normaliser(colonnes=True)) : deux espaces séparent deux colonnes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from modules.trieur.classement.texte import normaliser

# Un nombre décimal (« 249,99 », « 1 249,99 », « 1.249,99 ») ou un entier suivi d'une monnaie (« 1 234 € »).
_MONTANT = re.compile(
    r"(?<![\d,.])(?:eur\s*)?"
    r"(?P<entier>\d{1,3}(?:[ .]\d{3})+|\d+)"
    r"(?:[,.](?P<dec>\d{2}))?"
    r"(?!\d)"
    r"\s*(?P<monnaie>€|eur\b|euros?\b)?"
)


def _etiquettes(*phrases: str) -> re.Pattern[str]:
    """Des étiquettes dont les mots peuvent être séparés par plusieurs espaces (police large, colonnes)."""
    return re.compile("|".join(p.replace(" ", r"\s+") for p in phrases))


TOTAL_FORT = _etiquettes("total ttc", "net a payer", "montant ttc", "total a payer", "montant total ttc",
                         "total de votre facture", "montant a payer", "reste a payer", "montant de votre impot",
                         "cotisation annuelle", "net paye", "montant a regler", "total a regler", "solde a payer",
                         "montant du")  # fmt: skip
TOTAL_FAIBLE = _etiquettes("montant total", "total paye", "prix total", "montant paye", r"\btotal\b", r"\bprix\b",
                           "a payer", r"\bmontant\b")  # fmt: skip
EXCLU = _etiquettes(r"\bht\b", "hors taxe", "tva", "sous-total", "sous total", r"\bsolde\b", r"\bdont\b", "remise",
                    "economie", r"\bbrut\b", "ancien", "acompte", "eco-?participation")  # fmt: skip


@dataclass(frozen=True)
class MontantTrouve:
    valeur: Decimal
    debut: int
    monnaie: bool


def en_decimal(entier: str, decimales: str | None) -> Decimal:
    return Decimal(re.sub(r"[ .]", "", entier) + "." + (decimales or "00"))


def dans(ligne: str) -> list[MontantTrouve]:
    """Les montants d'une ligne normalisée : un décimal, ou un entier avec une monnaie."""
    sortie = []
    for m in _MONTANT.finditer(ligne):
        if not m.group("dec") and not m.group("monnaie") and not ligne[m.start() : m.start() + 3] == "eur":
            continue
        entier = m.group("entier")
        # « 1 249,99 » : un seul espace entre les milliers ; « Qté 1  249,99 » (deux espaces, deux colonnes) non.
        valeur = en_decimal(entier, m.group("dec"))
        sortie.append(MontantTrouve(valeur, m.start(), bool(m.group("monnaie"))))
    return sortie


def montant_ttc(texte: str) -> Decimal | None:
    """Le montant d'après son étiquette : « Total TTC » et ses équivalents d'abord, puis « Total », « Prix »…
    Une étiquette seule sur sa ligne prend le montant de la ligne suivante (ticket lu par l'OCR)."""
    lignes = normaliser(texte, colonnes=True).splitlines()
    for motif in (TOTAL_FORT, TOTAL_FAIBLE):
        trouve: Decimal | None = None
        for i, ligne in enumerate(lignes):
            m = motif.search(ligne)
            if not m or EXCLU.search(ligne):
                continue
            montants = [x for x in dans(ligne[m.end() :])]
            if not montants and i + 1 < len(lignes) and not EXCLU.search(lignes[i + 1]):
                suivants = dans(lignes[i + 1])
                montants = suivants[:1] if suivants and suivants[0].debut < 4 else []
            if montants:
                trouve = montants[0].valeur
        if trouve is not None:
            return trouve
    return None


def le_plus_grand(texte: str) -> Decimal | None:
    lignes = normaliser(texte, colonnes=True).splitlines()
    valeurs = [x.valeur for ligne in lignes if not EXCLU.search(ligne) for x in dans(ligne)]
    return max(valeurs) if valeurs else None


def en_francais(x: Decimal) -> str:
    """249.99 → « 249,99 » ; 1249.9 → « 1249,90 » (pas d'espace : le nom de fichier reste compact)."""
    return f"{x:.2f}".replace(".", ",")
