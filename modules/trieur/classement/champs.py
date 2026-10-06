"""Les champs d'un document, au-delà du type : numéro, produits achetés, mention de garantie, occasion, achat en
ligne, et le petit « détail » du nom de fichier.

Un produit est une ligne qui porte un prix. Il est durable (il mérite une fiche de garantie) s'il contient un mot
d'objet durable (casque, lave-linge, vélo…) et aucun mot de consommable ou de service (cartouche, piles, livraison,
extension de garantie…).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from modules.trieur.classement import montants
from modules.trieur.classement.texte import normaliser

# Les mots longs comptent même collés au mot suivant (l'OCR perd des espaces : « CasqueSonyWH ») ; les mots courts
# (« lit », « four », « tv ») doivent être entiers.
DURABLES = re.compile(
    r"\b(?:casque|ecouteur|airpods|televiseur|moniteur|lave-?linge|lave-?vaisselle|seche-?linge|refrigerateur|"
    r"frigo|congelateur|micro-?ondes|cuisiniere|aspirateur|ordinateur|laptop|macbook|imac|ipad|tablette|iphone|"
    r"smartphone|telephone|galaxy|enceinte|barre de son|amplificateur|console|playstation|xbox|montre|smartwatch|"
    r"perceuse|visseuse|ponceuse|tondeuse|nettoyeur|velo|trottinette|canape|matelas|sommier|armoire|commode|"
    r"fauteuil|machine a cafe|cafetiere|expresso|bouilloire|grille-?pain|mixeur|blender|thermomix|friteuse|"
    r"imprimante|scanner|appareil photo|camera|drone|gopro|climatiseur|radiateur|chauffe-?eau|liseuse|kindle|"
    r"routeur|disque dur|videoprojecteur|projecteur|fer a repasser|centrale vapeur|seche-?cheveux|lisseur|rasoir|"
    r"airfryer|purificateur)"
    r"|\b(?:tv|tele|ecran|four|plaque|hotte|robot|pc portable|pixel|ampli|ps5|switch|scie|lit|bureau|table|poele|"
    r"nas|ssd|mac mini)\b"
)
CONSOMMABLES = re.compile(
    r"\b(?:cartouche|encre|toner|cafe en grains|cafe moulu|capsule|t-?shirt|vetement|chaussette|filtre|cable|"
    r"coque|protection d'?ecran|croquette|ampoule|papier|lessive|extension de garantie|garantie|livraison|"
    r"frais de port|frais d'envoi|eco-?participation|ecotaxe|remise|abonnement|housse|adaptateur|consommable|"
    r"accessoire|main-?d'?oeuvre|installation|mise en service|reprise)"
    r"|\b(?:piles?|sacs?|recharge)\b"
)
OCCASION = re.compile(r"reconditionn|\boccasion\b|seconde main|remis a neuf|refurbished")
EXCLUES = re.compile(
    r"total|tva|\bht\b|net a payer|sous-total|montant|solde|\bcb\b|rendu|especes|carte|paiement|reglement|"
    r"acompte|\bdont\b|economie|loyer|charges|salaire|cotisation|prix\b"
)
_NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
            "neuf": 9, "dix": 10}  # fmt: skip
_DUREE = (
    r"(?:(?<!\d)(\d{1,3})|(?<![a-z])(un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix))\s*"
    r"(ans?|annees?|mois)\b"
)
_MENTIONS = [  # tolérantes aux espaces perdus par l'OCR (« Garantieconstructeur12mois »)
    re.compile(rf"garanti(?:e|es)?(?![a-z]*\s*(?:legale|de conformite))[^.\n]{{0,45}}?{_DUREE}"),
    re.compile(rf"{_DUREE}\s*de\s*garantie"),
]


@dataclass(frozen=True)
class Produit:
    libelle: str  # tel qu'écrit (accents et majuscules gardés)
    prix: Decimal | None
    durable: bool
    occasion: bool


def mois(nombre: str, unite: str) -> int:
    n = _NOMBRES.get(nombre) or int(nombre)
    return n if unite.startswith("mois") else n * 12


def mention_garantie(texte: str) -> int | None:
    """La plus longue durée de garantie écrite sur le document, en mois (« garantie 2 ans » → 24)."""
    n = normaliser(texte)
    vus = [mois(m.group(1) or m.group(2), m.group(3)) for motif in _MENTIONS for m in motif.finditer(n)]
    vus = [v for v in vus if 1 <= v <= 120]
    return max(vus) if vus else None


def garantie_de_la_note(note: str | None) -> int | None:
    """« garantie 3 ans », « 5 ans de garantie », « garantie : 18 mois » dans la note envoyée avec le document."""
    return mention_garantie(note or "") if note else None


def produits(texte: str) -> list[Produit]:
    """Les lignes de produits : un libellé suivi d'au moins un prix (le premier est le prix unitaire)."""
    sortie: list[Produit] = []
    for brute in texte.splitlines():
        n = normaliser(brute, colonnes=True)
        trouves = montants.dans(n)
        if not trouves or EXCLUES.search(n):
            continue
        colonne = re.search(r"  (?=\d|eur\b|€)", n)  # la colonne « Qté » ou « Prix » qui suit le libellé
        coupe = min(colonne.start(), trouves[0].debut) if colonne else trouves[0].debut
        libelle_n = re.sub(r"\s+", " ", n[: max(0, coupe)]).strip(" -:|")
        if len(re.sub(r"[^a-z]", "", libelle_n)) < 4:
            continue
        libelle = _meme_morceau(brute, libelle_n)
        durable = bool(DURABLES.search(libelle_n)) and not CONSOMMABLES.search(libelle_n)
        sortie.append(Produit(libelle, trouves[0].valeur, durable, bool(OCCASION.search(libelle_n))))
    return sortie


def _meme_morceau(brute: str, normalise: str) -> str:
    """Le début de la ligne d'origine qui correspond au libellé normalisé (pour garder accents et majuscules)."""
    propre = re.sub(r"\s+", " ", brute.replace(" ", " ")).strip()
    return propre[: len(normalise)].strip(" -:|") or normalise


def occasion(texte: str) -> bool:
    return bool(OCCASION.search(normaliser(texte)))


_NUMERO = re.compile(
    r"(?:facture|devis|avis|commande|invoice|bon de commande|ticket)\s*(?:n°|no|numero|nr|#|n\.)\s*:?\s*"
    r"([a-z0-9][a-z0-9\-/_.]{2,24})|(?:n°|numero|no) de facture\s*:?\s*([a-z0-9][a-z0-9\-/_.]{2,24})"
)


def numero(texte: str) -> str | None:
    """Le numéro de facture (ou de devis) : « Facture n° FA2026-12345 » → « FA2026-12345 »."""
    n = normaliser(texte)
    for m in _NUMERO.finditer(n):
        valeur = (m.group(1) or m.group(2) or "").strip(".-/")
        if re.search(r"\d", valeur):
            return valeur.upper()
    return None


def achat_en_ligne(texte: str, categorie: str | None) -> bool:
    n = normaliser(texte)
    commande = bool(
        re.search(r"commande\s*(?:n°|no|numero)|date de (?:la )?commande|commande (?:passee|effectuee) le", n)
    )
    return commande and (categorie == "ecommerce" or bool(re.search(r"livr|expedi|colis", n)))


def detail(type_: str, texte: str, produits_: list[Produit]) -> str:
    """Le petit mot du nom de fichier : le produit principal d'un achat, l'impôt d'un avis, etc."""
    n = normaliser(texte)
    if type_ in ("facture_achat", "ticket_caisse"):
        durables = [p for p in produits_ if p.durable]
        if durables:
            principal = max(durables, key=lambda p: p.prix or Decimal(0))
            return " ".join(principal.libelle.split()[:3])[:30]
        return ""
    if type_ == "avis_imposition":
        for motif, mot in (("taxe fonciere", "Taxe foncière"), ("taxe d'habitation", "Taxe d'habitation"),
                           ("revenu", "Revenus")):  # fmt: skip
            if motif in n:
                return mot
    if type_ == "bulletin_paie":
        return "Salaire"
    if type_ == "identite":
        for motif, mot in (("passeport", "Passeport"), ("permis", "Permis"), ("identite", "CNI")):
            if motif in n:
                return mot
    if type_ == "sante":
        for motif, mot in (("ordonnance", "Ordonnance"), ("decompte", "Décompte"), ("rembourse", "Remboursements")):
            if motif in n:
                return mot
    if type_ == "assurance":
        for motif, mot in (("echeance", "Échéance"), ("conditions particulieres", "Conditions")):
            if motif in n:
                return mot
    if type_ == "attestation":
        m = re.search(r"attestation (?:de |d')?([a-z]+)", n)
        if m and m.group(1) not in ("la", "le", "l", "paiement"):
            return m.group(1).capitalize()
    return ""
