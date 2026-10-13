"""Une clé phonétique française simple : deux écritures qui se prononcent pareil donnent la même clé (ou presque).

« notion » et « nocion » → `nosion` ; « zoom » et « zoum » → `sum` ; « calculette » et « calculète » → `kalkulet` ;
« whatsapp » et « ouatsape » → `uatsap`. Elle ne sert qu'à **comparer** (par ressemblance, pas par égalité) des noms
d'apps, de dossiers et de sites mal transcrits. Les prononciations anglaises qu'elle ne peut pas deviner
(« iTerm » dit « aille terme ») sont des formes parlées explicites du catalogue.
"""

from __future__ import annotations

import re

from voix.nlu.normalisation import sans_accents

# Remplacements dans l'ordre (minuscules, sans accents, sans espaces). Les majuscules notent des sons :
# U = « ou », O = « o/au/eau », E = « é/è/ai/ei », A = « an/en », I = « in/ain/un », N = « on », X = « ch ».
REGLES: list[tuple[str, str]] = [
    (r"[^a-z0-9]", ""),
    (r"sch|sh|ch", "X"),
    (r"ph", "f"),
    (r"th", "t"),
    (r"gn", "ni"),
    (r"qu|q|ck|cc", "k"),
    (r"c(?=[eiy])", "s"),
    (r"c", "k"),
    (r"gu(?=[eiy])", "g"),
    (r"g(?=[eiy])", "j"),
    (r"x", "ks"),
    (r"tion", "sion"),
    (r"w", "U"),
    (r"oo|ou|ue(?=$)", "U"),
    (r"eau|au|o", "O"),
    (r"ee|ea|y", "i"),
    (r"(?<=[aeiouAEIOUNX])ill", "i"),
    (r"ai|ei|et$|ez$|er$|e(?=[a-z]{2})", "E"),
    (r"[ae][nm](?=[^aeiouAEIOUNnm]|$)", "A"),
    (r"[aeiu]i?n(?=[^aeiouAEIOUnm]|$)", "I"),
    (r"O[nm](?=[^aeiouAEIOUnm]|$)", "N"),
    (r"eu", "E"),
    (r"h", ""),
    (r"z", "s"),
    (r"(?<=[a-zA-Z])(e|es|s|t|d|x|ent)$", ""),
    (r"(.)\1+", r"\1"),
]
_REGLES = [(re.compile(motif), remplacement) for motif, remplacement in REGLES]


def cle(texte: str) -> str:
    """La clé phonétique d'un mot ou d'un nom (les espaces sont ignorés)."""
    s = sans_accents(texte.lower())
    for motif, remplacement in _REGLES:
        s = motif.sub(remplacement, s)
    return s
