"""Les nombres dits en lettres, en français : « trente », « vingt et un », « quatre-vingt-dix-neuf », « deux cents ».

Travaille sur des **jetons** déjà en minuscules et sans accents (`vingt`, `et`, `un`). Les traits d'union ont été
remplacés par des espaces à la normalisation. « un » et « une » restent des articles, sauf devant une unité
(« une minute ») ou après « le » / « numéro » (« ouvre le un »).
"""

from __future__ import annotations

UNITES = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
    "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
}  # fmt: skip
DIZAINES = {"vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
CENT = {"cent", "cents"}
MILLE = {"mille"}
MOTS = set(UNITES) | set(DIZAINES) | CENT | MILLE | {"et"}

ORDINAUX = {
    "premier": 1, "premiere": 1, "1er": 1, "1re": 1, "1ere": 1,
    "deuxieme": 2, "second": 2, "seconde": 2, "2e": 2, "2eme": 2,
    "troisieme": 3, "3e": 3, "3eme": 3, "quatrieme": 4, "4e": 4, "4eme": 4, "cinquieme": 5, "5e": 5, "5eme": 5,
    "sixieme": 6, "6e": 6, "6eme": 6, "septieme": 7, "7e": 7, "7eme": 7, "huitieme": 8, "8e": 8, "8eme": 8,
    "neuvieme": 9, "9e": 9, "9eme": 9, "dixieme": 10, "10e": 10, "10eme": 10, "dernier": -1, "derniere": -1,
}  # fmt: skip

# Après ces mots, « un » / « une » est un nombre (« une minute », « un pour cent », « le un »).
UNITES_APRES = {
    "minute", "minutes", "min", "mn", "seconde", "secondes", "sec", "s", "heure", "heures", "h", "pourcent",
    "jour", "jours", "quart", "demi", "demie",
}  # fmt: skip
AVANT_NOMBRE = {"le", "numero", "no", "n"}


def _valeur(groupe: list[str]) -> int | None:
    """La valeur d'une suite de mots-nombres, ou None si la suite n'est pas un nombre bien formé.

    « deux trois » n'est pas un nombre (deux nombres dits à la suite) ; « quatre vingt dix » vaut 90 ;
    « soixante et onze » vaut 71 ; « deux cent trente » vaut 230 ; « mille deux cents » vaut 1200."""
    total = 0
    courant = 0
    dernier: str | None = None  # unite, dizaine, cent, mille
    derniere_valeur = 0
    for i, mot in enumerate(groupe):
        if mot == "et":
            suivant = groupe[i + 1] if i + 1 < len(groupe) else ""
            if (
                dernier != "dizaine"
                or derniere_valeur not in (20, 30, 40, 50, 60)
                or suivant not in ("un", "une", "onze")
            ):
                return None
            continue
        if mot in UNITES:
            v = UNITES[mot]
            if dernier == "unite" and not (derniere_valeur == 10 and 7 <= v <= 9):
                return None  # « deux trois » : deux nombres ; mais « dix sept » = 17
            if dernier == "dizaine" and v >= 10 and derniere_valeur not in (60, 80):
                return None
            if dernier == "dizaine" and v == 0:
                return None
            courant += v
            dernier, derniere_valeur = "unite", v
        elif mot in DIZAINES:
            v = DIZAINES[mot]
            if dernier == "unite" and derniere_valeur == 4 and v == 20:
                courant += 80 - 4  # quatre-vingt(s)
                dernier, derniere_valeur = "dizaine", 80
                continue
            if dernier in ("unite", "dizaine"):
                return None
            courant += v
            dernier, derniere_valeur = "dizaine", v
        elif mot in CENT:
            if dernier == "dizaine" or (dernier == "unite" and derniere_valeur < 2) or courant >= 100:
                return None
            courant = (courant or 1) * 100
            dernier, derniere_valeur = "cent", 100
        elif mot in MILLE:
            if total:
                return None
            total = (courant or 1) * 1000
            courant = 0
            dernier, derniere_valeur = "mille", 1000
        else:
            return None
    if dernier is None:
        return None
    return total + courant


def plages(jetons: list[str]) -> list[tuple[int, int, int]]:
    """Les suites de mots-nombres à convertir : (début, fin exclue, valeur)."""
    resultat: list[tuple[int, int, int]] = []
    i = 0
    while i < len(jetons):
        mot = jetons[i]
        if mot not in MOTS or mot == "et":
            i += 1
            continue
        # La plus longue suite de mots-nombres qui forme un nombre valide.
        fin = i
        while fin < len(jetons) and jetons[fin] in MOTS:
            fin += 1
        meilleur = None
        for j in range(fin, i, -1):
            v = _valeur(jetons[i:j])
            if v is not None:
                meilleur = (j, v)
                break
        if meilleur is None:
            i += 1
            continue
        j, v = meilleur
        if j - i == 1 and mot in ("un", "une"):
            suivant = jetons[j] if j < len(jetons) else ""
            precedent = jetons[i - 1] if i > 0 else ""
            if suivant not in UNITES_APRES and precedent not in AVANT_NOMBRE:
                i += 1  # un article : « lance une playlist »
                continue
        resultat.append((i, j, v))
        i = j
    return resultat


def convertir(jetons: list[str]) -> list[str]:
    """Remplace chaque suite de mots-nombres par ses chiffres : ['volume', 'a', 'trente'] → ['volume', 'a', '30']."""
    sortie = list(jetons)
    for debut, fin, valeur in reversed(plages(jetons)):
        sortie[debut:fin] = [str(valeur)]
    return sortie


def ordinal(mot: str) -> int | None:
    """« deuxième » → 2, « 3e » → 3, « dernier » → -1 ; sinon None."""
    return ORDINAUX.get(mot)
