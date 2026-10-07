"""Ce que tu as dans le frigo, écrit ou dicté en français, compris en local (0 crédit).

« 2 courgettes, feta, œufs, reste de riz », « une demi botte de coriandre », « 500g de steak haché », « une brique
de crème », « des patates », « ognons » → des ingrédients de la base, avec la quantité quand elle est dite.

- Découpage : virgules, points-virgules, retours à la ligne, « et », « + », « avec ».
- Quantités : chiffres (« 2 », « 1,5 kg », « ½ », « 1/2 »), mots (« un », « une demi », « trois »), contenants
  (« une brique de crème » = le format vendu : 20 cl), restes (« un reste de riz », « un fond de crème » : quantité
  inconnue, comptée comme « assez »).
- Noms : synonymes de la base (patate, steak haché, crème…), pluriels, accents, majuscules, puis les fautes
  courantes (une lettre de trop, de moins, inversée ou changée).
- « plus de lait », « pas de beurre » : signalé comme absent, jamais compté.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from quotidien.repas import envies
from quotidien.repas.base import Base, Ingredient

NOMBRES = {
    "un": 1.0, "une": 1.0, "deux": 2.0, "trois": 3.0, "quatre": 4.0, "cinq": 5.0, "six": 6.0, "sept": 7.0,
    "huit": 8.0, "neuf": 9.0, "dix": 10.0, "onze": 11.0, "douze": 12.0, "quinze": 15.0, "vingt": 20.0,
    "demi": 0.5, "demie": 0.5, "moitie": 0.5, "quart": 0.25, "trentaine": 30.0, "dizaine": 10.0, "douzaine": 12.0,
}  # fmt: skip
UNITES = {
    "g": "g", "gr": "g", "grs": "g", "gramme": "g", "grammes": "g", "kg": "kg", "kilo": "kg", "kilos": "kg",
    "kgs": "kg", "ml": "ml", "cl": "cl", "dl": "dl", "l": "l", "litre": "l", "litres": "l",
}  # fmt: skip
# Contenants : « une brique de crème » vaut un format vendu de l'ingrédient (celui dont le libellé le cite).
CONTENANTS = {
    "boite", "boites", "paquet", "paquets", "brique", "briques", "sachet", "sachets", "botte", "bottes", "pot", "pots",
    "barquette", "barquettes", "bocal", "bocaux", "bloc", "blocs", "boule", "boules", "filet", "filets", "tube",
    "tubes", "bouteille", "bouteilles", "sac", "sacs", "conserve", "conserves", "rouleau", "rouleaux", "tablette",
}  # fmt: skip
# Des mots qui ne disent rien de l'ingrédient (« j'ai », « encore », « frais »…), retirés avant de chercher le nom.
VIDES = {
    "j", "ai", "il", "y", "a", "reste", "restes", "encore", "aussi", "mon", "ma", "mes", "le", "la", "les", "l", "de",
    "d", "des", "du", "un", "une", "quelques", "peu", "pas", "mal", "beaucoup", "plein", "bien", "dans", "frigo",
    "placard", "congelateur", "congel", "au", "aux", "en", "tout", "toute", "tous", "toutes", "petit", "petite",
    "petits", "petites", "gros", "grosse", "grosses", "bon", "bonne", "vieux", "vieille", "entame", "entamee",
    "ouvert", "ouverte", "frais", "fraiche", "fraiches", "maison", "environ", "a peu pres", "fond", "bout", "bouts",
    "morceau", "morceaux", "part", "parts", "fin", "nature",
}  # fmt: skip
ABSENT = re.compile(
    r"^\s*(?:(?:ah |oh )?non\s+|en fait\s+|finalement\s+)?(?:(?:je n ai|j ai|il n y a|il y a|y a|on n a|on a|n ai)\s+)?"
    r"(?:plus|pas|plus du tout|pas de|plus de|plus d|pas d|sans|aucun|aucune|zero)\b"
)
RESTE = re.compile(r"\b(?:reste|restes|fond|fin|bout|bouts|un peu)\b")
# La virgule sépare, sauf entre deux chiffres (« 1,5 kg ») ; la barre aussi, sauf dans une fraction (« 1/2 »).
SEPARATEURS = re.compile(
    r"(?:(?<!\d),|,(?!\d))|[;\n•·]+|\s\+\s|(?<!\d)/(?!\d)"
    # « plus » relie deux aliments (« courgettes plus feta »), sauf « plus de lait » qui dit qu'il n'y en a plus.
    r"|\s+(?:et(?!\s+demi)|avec|ainsi que|plus(?!\s+(?:de|d'|du|des|aucun|aucune|rien)\b))\s+"
)
DEBUT_VIDE = re.compile(r"^\s*(?:(?:j'ai|j ai|il (?:me |nous )?reste|il y a|encore|aussi|toujours|plus que)\s+)+")
MULTIPLES = {"douzaine": 12.0, "dizaine": 10.0, "trentaine": 30.0, "demi": 0.5, "demie": 0.5}
QUANTITE = re.compile(
    r"^\s*(?P<n>\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|[½¼¾])\s*(?P<u>kgs?|kilos?|grammes?|grs?|g|ml|cl|dl|litres?|l)?(?![a-z])",
)


@dataclass
class Element:
    texte: str  # le morceau tel que tu l'as écrit
    ingredient: str | None  # identifiant dans la base, None si inconnu
    nom: str  # le nom à afficher
    quantite: float | None  # dans l'unité de base de l'ingrédient (g, ml ou pièces) ; None : inconnue (« assez »)
    unite: str | None
    reste: bool = False
    absent: bool = False
    incertain: bool = False  # deviné (faute de frappe ou photo peu nette) : « à confirmer »
    confiance: float = 1.0


def _sans_accents(texte: str) -> str:
    return envies.normaliser(texte)


_INDEX: dict[int, dict[str, str]] = {}


def index_noms(base: Base) -> dict[str, str]:
    """Nom normalisé (sans accents, au singulier) → identifiant, pour chaque nom, pluriel et synonyme de la base."""
    if id(base) in _INDEX:
        return _INDEX[id(base)]
    index: dict[str, str] = {}
    for ing in base.ingredients.values():
        for nom in (ing.nom, ing.pluriel, ing.id.replace("_", " "), *ing.synonymes):
            for variante in (nom, re.sub(r"\(.*?\)", "", nom)):
                cle = envies._au_singulier(_sans_accents(variante))
                if cle and cle not in index:
                    index[cle] = ing.id
    _INDEX[id(base)] = index
    return index


def distance(a: str, b: str, maximum: int = 2) -> int:
    """Damerau-Levenshtein bornée (transpositions comprises)."""
    if abs(len(a) - len(b)) > maximum:
        return maximum + 1
    precedente2: list[int] = []
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courante = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            courante[j] = min(precedente[j] + 1, courante[j - 1] + 1, precedente[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                courante[j] = min(courante[j], precedente2[j - 2] + 1)
        precedente2, precedente = precedente, courante
    return min(precedente[-1], maximum + 1)


def _chercher(mots: list[str], index: dict[str, str], approche: bool = True,
              exact: bool = True) -> tuple[str | None, bool, list[str]]:  # fmt: skip
    """L'ingrédient nommé par ces mots : (identifiant, deviné ?, mots utilisés). Le plus long groupe de mots d'abord,
    exact puis approché (une faute pour 4 à 7 lettres, deux à partir de 8)."""
    n = len(mots)
    for taille in range(min(n, 5), 0, -1) if exact else ():
        for debut in range(n - taille + 1):
            groupe = " ".join(mots[debut : debut + taille])
            if groupe in index and groupe not in VIDES:
                return index[groupe], False, mots[debut : debut + taille]
    if not approche:
        return None, False, []
    meilleur: tuple[int, int, str, list[str]] | None = None
    for taille in range(min(n, 4), 0, -1):
        for debut in range(n - taille + 1):
            groupe = " ".join(mots[debut : debut + taille])
            if len(groupe) < 4 or groupe in VIDES:
                continue
            seuil = 1 if len(groupe) < 8 else 2
            for cle, id_ in index.items():
                if abs(len(cle) - len(groupe)) > seuil or cle[0] != groupe[0] and len(groupe) < 8:
                    continue
                d = distance(groupe, cle, seuil)
                if d <= seuil and (meilleur is None or (d, -len(cle)) < (meilleur[0], -meilleur[1])):
                    meilleur = (d, len(cle), id_, mots[debut : debut + taille])
        if meilleur is not None:
            return meilleur[2], True, meilleur[3]
    return None, False, []


def _nombre(texte: str) -> float | None:
    t = texte.replace(",", ".").replace(" ", "")
    t = {"½": "0.5", "¼": "0.25", "¾": "0.75"}.get(t, t)
    try:
        if "/" in t:
            a, b = t.split("/")
            return float(a) / float(b) if float(b) else None
        return float(t)
    except ValueError:
        return None


def _vers_unite(ing: Ingredient, quantite: float, unite: str) -> float | None:
    from quotidien.repas import unites

    try:
        return unites.convertir(quantite, unite, ing.unite, ing.poids_piece_g)
    except unites.UniteIncompatible:
        return None


def _morceau(texte: str, base: Base, index: dict[str, str]) -> Element | None:
    brut = texte.strip(" .!?:-*\t\"'«»")
    if not brut:
        return None
    t = brut.lower().replace("’", "'").replace("œ", "oe")
    absent = bool(ABSENT.match(_sans_accents(t)))
    t = DEBUT_VIDE.sub("", t)  # « j'ai encore 2 courgettes » : la quantité vient après les petits mots
    quantite: float | None = None
    unite: str | None = None
    m = QUANTITE.match(t)
    if m:
        quantite = _nombre(m.group("n"))
        unite = UNITES.get(m.group("u") or "", None)
        t = t[m.end() :]
    mots_bruts = _sans_accents(t).split()
    # Nombres écrits en lettres : « une demi botte », « deux », « une douzaine d'œufs ».
    article = False  # « un reste de… » : le « un » n'est pas une quantité
    if quantite is None and mots_bruts and mots_bruts[0] in NOMBRES:
        article = mots_bruts[0] in ("un", "une")
        quantite = NOMBRES[mots_bruts[0]]
        mots_bruts = mots_bruts[1:]

    def demi() -> bool:
        return len(mots_bruts) > 1 and mots_bruts[0] == "et" and mots_bruts[1] in ("demi", "demie")

    if quantite is not None and mots_bruts and envies._singulier(mots_bruts[0]) in MULTIPLES:
        # « une douzaine », « deux douzaines », « une demi botte »
        quantite, mots_bruts = quantite * MULTIPLES[envies._singulier(mots_bruts[0])], mots_bruts[1:]
        article = False
    elif quantite is not None and demi():  # « un et demi litre »
        quantite, mots_bruts, article = quantite + 0.5, mots_bruts[2:], False
    if mots_bruts and mots_bruts[0] in UNITES and quantite is not None and unite is None:
        unite, mots_bruts, article = UNITES[mots_bruts[0]], mots_bruts[1:], False
        if quantite is not None and demi():  # « un litre et demi »
            quantite, mots_bruts = quantite + 0.5, mots_bruts[2:]
    if quantite is not None and len(mots_bruts) > 2 and mots_bruts[-2:] in (["et", "demi"], ["et", "demie"]):
        quantite, mots_bruts = quantite + 0.5, mots_bruts[:-2]  # « un oignon et demi »
    reste = bool(RESTE.search(" ".join(mots_bruts)))
    if reste and article:
        quantite = None
    contenant = next((w for w in mots_bruts[:3] if w in CONTENANTS), None)
    mots = [envies._singulier(w) for w in mots_bruts if w not in CONTENANTS]
    # Le nom exact d'abord, sur tous les mots (« pomme de terre », « crème fraîche » contiennent des petits mots),
    # puis l'approché, sur les mots utiles seulement.
    id_, devine, pris = _chercher(mots, index, approche=False)
    restants = [w for w in mots if w not in VIDES and w not in pris]
    if id_ is not None and restants and len(" ".join(mots)) >= 8:
        # « pomme de tere » : « pomme » existe, mais « pomme de terre » à une lettre près explique tous les mots.
        long_id, long_devine, long_pris = _chercher(mots, index, exact=False)
        if long_id is not None and len(long_pris) > len(pris):
            id_, devine = long_id, long_devine
    if id_ is None:
        utiles = [w for w in mots if w not in VIDES] or mots
        id_, devine, _ = _chercher(utiles, index)
    if id_ is None:
        return Element(brut, None, brut, None, None, reste, absent)
    ing = base.ingredients[id_]
    q_base: float | None = None
    if reste and quantite is None:
        q_base = None  # un reste : quantité inconnue, comptée comme « assez »
    elif quantite is not None and unite is not None:
        q_base = _vers_unite(ing, quantite, unite)
    elif quantite is not None and contenant is not None:
        format_ = next((f for f in ing.formats if contenant.rstrip("sx") in _sans_accents(f.libelle)),
                       ing.formats[0])  # fmt: skip
        q_base = quantite * format_.quantite
    elif quantite is not None:
        q_base = quantite if ing.unite == "p" else (quantite * ing.poids_piece_g if ing.poids_piece_g else None)
    return Element(brut, id_, ing.nom, q_base, ing.unite, reste, absent, devine, 0.75 if devine else 1.0)


def decouper(texte: str) -> list[str]:
    t = texte.replace("\r", "\n")
    # Une liste à puces ou à tirets en début de ligne : chaque ligne est un élément.
    t = re.sub(r"(?m)^\s*[-*•]\s*", "\n", t)
    return [m for m in SEPARATEURS.split(t) if m and m.strip()]


def analyser(texte: str, base: Base) -> list[Element]:
    """Le texte → les éléments du frigo (dans l'ordre), un même ingrédient réuni une seule fois."""
    index = index_noms(base)
    elements: list[Element] = []
    for morceau in decouper(texte[:2000]):
        e = _morceau(morceau, base, index)
        if e is None:
            continue
        deja = next((x for x in elements if x.ingredient and x.ingredient == e.ingredient), None)
        if deja is not None:
            if deja.absent != e.absent:  # « du lait… ah non, plus de lait » : la dernière phrase gagne
                elements[elements.index(deja)] = e
            elif deja.quantite is not None and e.quantite is not None:
                deja.quantite += e.quantite
            else:
                deja.quantite = None
            continue
        elements.append(e)
    return elements


def disponibles(elements: list[Element]) -> dict[str, Element]:
    return {e.ingredient: e for e in elements if e.ingredient and not e.absent}
