"""Les dates françaises d'un document, avec ce qui les précède (« Date d'achat », « Imprimé le », « du … au … »).

Formats : 03/10/2026, 03-10-2026, 03.10.2026, 03/10/26, 3 octobre 2026, 03 oct. 2026, 1er mars 2026, 2026-10-03.
Une date est toujours jour/mois (03/04 = 3 avril). Chaque date reçoit une catégorie d'après son étiquette ; la date
du document se choisit ensuite selon le type (date d'achat d'abord, fin de la période d'un relevé, départ d'un
billet…).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from modules.trieur.classement.texte import normaliser

MOIS = {"janvier": 1, "janv": 1, "jan": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "mar": 3, "avril": 4, "avr": 4,
        "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9, "sep": 9, "octobre": 10,
        "oct": 10, "novembre": 11, "nov": 11, "decembre": 12, "dec": 12}  # fmt: skip
_NOMS_MOIS = "|".join(sorted(MOIS, key=len, reverse=True))
_NUM = re.compile(r"(?<![\d/.\-])(\d{1,2})\s?[/.\-]\s?(\d{1,2})\s?[/.\-]\s?(\d{4}|\d{2})(?![\d/])")
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_LONG = re.compile(rf"(?<!\d)(\d{{1,2}})(?:er)?\s*({_NOMS_MOIS})\.?\s*(\d{{4}})(?!\d)")

# L'étiquette (ce qui précède la date sur sa ligne), de la plus précise à la plus générale. Elle est comparée sans
# espaces : l'OCR en perd souvent (« Faità Lyon,le »).
CATEGORIES: list[tuple[str, re.Pattern[str]]] = [
    (
        "exclue",
        re.compile(
            r"imprime|editele|edition|echeance|limite|prelev|valable|expiration|n[ée]+\(?e?\)?le|"
            r"naissance|depuisle|reservee?le|datedessoins|jusqu'?au"
        ),
    ),  # fmt: skip
    ("achat", re.compile(r"dated'?achat|achetele|datedelavente|datedel'achat")),
    ("delivrance", re.compile(r"delivrance|delivrele|delivrepar")),
    ("fait", re.compile(r"fait(?:a[^,]+,?)?le|delivreele|,le$|^le:?$|[a-z]+,le$")),
    ("commande", re.compile(r"commande")),
    ("livraison", re.compile(r"(?<!de)livr|datedelivraison|expedi")),
    ("depart", re.compile(r"allerle|departle|datedu?voyage|depart:?$|aller:?$|datededepart")),
    ("arrivee", re.compile(r"arrivee|check-?in")),
    ("paiement", re.compile(r"datedepaiement|payele|paiementle")),
    ("recouvrement", re.compile(r"miseenrecouvrement|dated'?etablissement|etablissement")),
    ("effet", re.compile(r"dated'?effet|prised'?effet")),
    ("emission", re.compile(r"emisle|emisele|dated'?emission")),
    ("facture", re.compile(r"datede(?:la)?facture|facturedu|datedudevis|etablile|datedureleve|datedudecompte")),
    ("generique", re.compile(r"date:?$|^le:?$|^date")),
]


@dataclass(frozen=True)
class DateTrouvee:
    valeur: date
    categorie: str  # une des CATEGORIES, « periode_debut », « periode_fin » ou « sans_etiquette »
    ligne: int
    contexte: str


def _annee(texte: str) -> int:
    n = int(texte)
    return 2000 + n if n < 100 else n


def _valide(j: int, m: int, a: int) -> date | None:
    if not (1990 <= a <= 2100):
        return None
    try:
        return date(a, m, j)
    except ValueError:
        return None


def _trouver(ligne: str) -> list[tuple[int, int, date]]:
    """(début, fin, date) de chaque date de la ligne (déjà normalisée)."""
    vus: list[tuple[int, int, date]] = []
    for m in _ISO.finditer(ligne):
        d = _valide(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            vus.append((m.start(), m.end(), d))
    for m in _NUM.finditer(ligne):
        if any(a <= m.start() < b for a, b, _ in vus):
            continue
        d = _valide(int(m.group(1)), int(m.group(2)), _annee(m.group(3)))
        if d:
            vus.append((m.start(), m.end(), d))
    for m in _LONG.finditer(ligne):
        d = _valide(int(m.group(1)), MOIS[m.group(2)], int(m.group(3)))
        if d:
            vus.append((m.start(), m.end(), d))
    return sorted(vus, key=lambda x: x[0])


def categorie(contexte: str) -> str:
    c = re.sub(r"\s+", "", normaliser(contexte)).rstrip(":")
    for nom, motif in CATEGORIES:
        if motif.search(c):
            return nom
    return "sans_etiquette"


def toutes(texte: str) -> list[DateTrouvee]:
    lignes = normaliser(texte).splitlines()
    sortie: list[DateTrouvee] = []
    for i, ligne in enumerate(lignes):
        trouvees = _trouver(ligne)
        for k, (debut, fin, d) in enumerate(trouvees):
            avant = ligne[trouvees[k - 1][1] if k else 0 : debut]
            if k and re.fullmatch(r"\s*au\s*", avant):
                sortie.append(DateTrouvee(d, "periode_fin", i, avant))
                continue
            apres = ligne[fin : trouvees[k + 1][0]] if k + 1 < len(trouvees) else ""
            if re.fullmatch(r"\s*au\s*", apres) and re.search(r"\bdu\s*$", avant):
                sortie.append(DateTrouvee(d, "periode_debut", i, avant))
                continue
            contexte = avant[-50:]
            cat = categorie(contexte)
            if cat == "sans_etiquette" and not avant.strip() and i:
                cat = categorie(lignes[i - 1][-50:])  # l'étiquette sur la ligne du dessus (tableau, OCR)
                if cat in ("generique", "fait"):
                    cat = "sans_etiquette"
            sortie.append(DateTrouvee(d, cat, i, contexte))
    return sortie


PRIORITES: dict[str, list[str]] = {
    "defaut": ["achat", "facture", "emission", "generique", "fait", "recouvrement", "delivrance", "effet",
               "sans_etiquette"],
    "facture_achat": ["achat", "facture", "generique", "emission", "sans_etiquette", "fait"],
    "ticket_caisse": ["achat", "sans_etiquette", "generique", "facture"],
    "releve_bancaire": ["periode_fin", "facture", "generique"],
    "billet_transport": ["depart", "generique", "sans_etiquette", "emission"],
    "reservation": ["arrivee", "generique", "sans_etiquette"],
    "bulletin_paie": ["paiement", "periode_fin", "generique"],
    "avis_imposition": ["recouvrement", "facture", "emission", "generique", "fait"],
    "identite": ["delivrance", "generique"],
    "quittance_loyer": ["fait", "generique", "facture", "emission", "periode_fin"],
    "assurance": ["emission", "facture", "effet", "generique", "fait", "sans_etiquette"],
    "sante": ["facture", "generique", "fait", "sans_etiquette"],
    "attestation": ["fait", "generique", "facture", "emission", "sans_etiquette"],
    "bail_contrat": ["fait", "generique", "effet", "sans_etiquette"],
    "courrier_admin": ["fait", "generique", "facture", "sans_etiquette"],
    "garantie_notice": ["achat", "generique", "facture"],
}  # fmt: skip


def date_du_document(dates: list[DateTrouvee], type_: str) -> date | None:
    ordre = PRIORITES.get(type_, PRIORITES["defaut"])
    for cat in ordre:
        candidates = [d for d in dates if d.categorie == cat]
        if candidates:
            return candidates[0].valeur
    return None


def premiere(dates: list[DateTrouvee], categorie_: str) -> date | None:
    return next((d.valeur for d in dates if d.categorie == categorie_), None)
