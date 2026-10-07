"""Le caviardage : ce qui ne doit jamais sortir du Mac, ni entrer dans un journal.

- `caviarder(texte)` retire numéros de téléphone, adresses e-mail, IBAN, numéros de carte, adresses postales et URL ;
- `noms_retires(texte, noms)` retire en plus des noms précis (noms de famille des Contacts) ;
- le journal passe tout par `caviarder` avant d'écrire.

Pour les anniversaires (§6), ce n'est pas le caviardage qui protège d'abord : la demande à l'IA est **construite**
avec quatre champs seulement (prénom, relation, ton, âge) plus tes notes, elles-mêmes caviardées.
"""

from __future__ import annotations

import re

TELEPHONE = re.compile(
    r"(?<![\w+])(?:(?:\+|00)\s?\d{1,3}[\s.\-]?(?:\(0\)\s?)?\d(?:[\s.\-]?\d{2}){4}"
    r"|0\s?[1-9](?:[\s.\-]?\d{2}){4}"
    r"|\+?\d[\d\s.\-]{8,}\d)(?![\w])"
)
EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
CARTE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")
URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.IGNORECASE)
ADRESSE = re.compile(
    r"\b\d{1,4}\s?(?:bis|ter)?,?\s+(?:rue|avenue|av\.?|boulevard|bd|place|impasse|allée|allee|chemin|route|cours|quai|"
    r"square|passage|résidence|residence|lotissement|lieu-dit)\b[^\n,;]{0,60}",
    re.IGNORECASE,
)
CODE_POSTAL_VILLE = re.compile(r"\b\d{5}\s+[A-ZÀ-Ÿ][\w\-'À-ÿ]+(?:\s+[A-ZÀ-Ÿ][\w\-'À-ÿ]+)*")


def caviarder(texte: str) -> str:
    if not texte:
        return ""
    t = URL.sub("[lien]", texte)
    t = EMAIL.sub("[e-mail]", t)
    t = IBAN.sub("[iban]", t)
    t = ADRESSE.sub("[adresse]", t)
    t = CODE_POSTAL_VILLE.sub("[adresse]", t)
    t = CARTE.sub("[numéro]", t)
    t = TELEPHONE.sub("[téléphone]", t)
    return t


def noms_retires(texte: str, noms: list[str]) -> str:
    """Retire chaque nom (insensible à la casse, mot entier) puis caviarde le reste."""
    t = texte or ""
    for nom in sorted({n.strip() for n in noms if n and len(n.strip()) >= 2}, key=len, reverse=True):
        t = re.sub(rf"(?<!\w){re.escape(nom)}(?!\w)", "[nom]", t, flags=re.IGNORECASE)
    return caviarder(t)
