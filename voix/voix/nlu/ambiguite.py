"""Répondre à « Notes ou Notion ? » (ou choisir une des suggestions) : par le nom, par l'ordre, ou « aucun ».

- « Notion », « l'app Notion », « Notion s'il te plaît » → le choix dont le nom ressemble le plus (et nettement) ;
- « la deuxième », « le 2 », « le second » → par l'ordre ;
- « aucun », « non », « ni l'un ni l'autre », « annule » → abandon.
Sinon : « inconnu » (la phrase est alors comprise comme une nouvelle commande).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TypeVar

from voix.nlu.approx import Forme, similarite
from voix.nlu.nombres import ordinal
from voix.nlu.normalisation import normaliser

T = TypeVar("T")
SEUIL_NOM = 0.75
ABANDON = re.compile(
    r"aucun|aucune|non|ni l un ni l autre|ni l une ni l autre|annule|laisse tomber|rien|stop|personne|"
    r"aucun des deux|aucune des deux|aucun des trois|aucune des trois|oublie|oublie ca"
)
_ORDRE = re.compile(
    r"(?:(?:{p}) )?(?:numero )?(?P<rang>\d{{1,2}}|premier|premiere|deuxieme|second|seconde|troisieme|1er|1re|1ere|"
    r"2e|2eme|3e|3eme|dernier|derniere)(?: (?:choix|option|proposition))?".format(
        p="le|la|l|prends le|prends la|choisis le|choisis la|ouvre le|ouvre la|c est le|c est la|plutot le|plutot la"
    )
)


def choisir(texte: str, libelles: Sequence[str]) -> tuple[str, int | None]:
    """("choisi", index) | ("abandon", None) | ("inconnu", None)."""
    t = normaliser(texte).texte
    if not t:
        return "inconnu", None
    if ABANDON.fullmatch(t):
        return "abandon", None
    m = _ORDRE.fullmatch(t)
    if m:
        rang_brut = m.group("rang")
        rang = int(rang_brut) if rang_brut.isdigit() else ordinal(rang_brut)
        if rang == -1:
            rang = len(libelles)
        if rang is not None and 1 <= rang <= len(libelles):
            return "choisi", rang - 1
        return "inconnu", None
    t = re.sub(r"^(?:(?:plutot|c est|prends|choisis|ouvre|lance|va sur) )+", "", t)
    t = re.sub(r"^(?:l app|l application|le site|le dossier|le|la|les|l) ", "", t)
    requete = Forme.de(t)
    scores = sorted(((similarite(requete, Forme.de(lib)), i) for i, lib in enumerate(libelles)), reverse=True)
    if not scores or scores[0][0] < SEUIL_NOM:
        return "inconnu", None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.08:
        return "inconnu", None  # pas plus clair que la première fois
    return "choisi", scores[0][1]
