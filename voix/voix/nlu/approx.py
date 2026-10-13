"""La correspondance approximative des objets : distance d'édition + phonétique française.

`similarite("nocion", "notion")` est élevée (même clé phonétique) ; `similarite("notes", "notion")` ne l'est pas.
Un nom très court (« tv ») doit être dit presque exactement : une lettre de travers sur deux lettres, c'est un autre
mot. Le seuil d'acceptation est réglable (`[comprehension] seuil`, 0,80 par défaut).
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz.distance import Indel

from voix.nlu.normalisation import sans_accents
from voix.nlu.phonetique import cle

POIDS_PHONETIQUE = 0.95  # une ressemblance de prononciation compte un peu moins qu'une ressemblance d'écriture


def forme_normale(texte: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces simples : « l'App Store » → `l app store`."""
    s = sans_accents(texte.lower())
    s = "".join(c if c.isalnum() else " " for c in s)
    return " ".join(s.split())


ARTICLES = ("le ", "la ", "les ", "l ", "un ", "une ", "du ", "des ", "de ", "d ", "mon ", "ma ", "mes ")


def sans_articles(texte: str) -> str:
    """« le figaro » → « figaro » : deux noms ne se ressemblent pas parce qu'ils commencent par le même article."""
    t = texte
    change = True
    while change:
        change = False
        for a in ARTICLES:
            if t.startswith(a) and len(t) > len(a):
                t = t[len(a) :]
                change = True
    return t


@dataclass(frozen=True)
class Forme:
    texte: str
    colle: str  # sans articles ni espaces : « vs code » et « vscode », « le monde » et « monde »
    phon: str
    entier: str  # sans espaces, articles compris : pour l'égalité exacte

    @classmethod
    def de(cls, texte: str) -> Forme:
        t = forme_normale(texte)
        coeur = sans_articles(t)
        return cls(t, coeur.replace(" ", ""), cle(coeur), t.replace(" ", ""))


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(Indel.normalized_similarity(a, b))


def similarite(requete: Forme, forme: Forme) -> float:
    """Entre 0 et 1 ; 1 seulement si les deux formes s'écrivent pareil (aux espaces près)."""
    if requete.entier == forme.entier:
        return 1.0
    if requete.colle == forme.colle:
        return 0.99  # mêmes mots, article en plus ou en moins
    ecrit = _ratio(requete.colle, forme.colle)
    phon = _ratio(requete.phon, forme.phon)
    if requete.phon == forme.phon and len(forme.phon) >= 3:
        phon = 1.0
    score = max(ecrit, POIDS_PHONETIQUE * phon)
    plus_court = min(len(requete.colle), len(forme.colle))
    if plus_court <= 3:
        # Deux ou trois lettres : seule une écriture ou une prononciation identique compte.
        return 0.0 if requete.phon != forme.phon else min(score, 0.9)
    if plus_court <= 5:
        score -= 0.04  # un mot court mal dit reste douteux
    return max(0.0, min(score, 0.999))
