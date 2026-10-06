"""Caviardage : retirer tes données personnelles d'un texte.

Appliqué avant tout envoi à l'IA, dans le journal et dans l'historique. Retire :
- tes nom, téléphone, adresse et e-mail déclarés dans config.toml ([moi]) ;
- tout IBAN, tout numéro de carte (vérifié par la clé de Luhn), tout numéro de téléphone, tout e-mail,
  toute adresse postale reconnaissable, tout code à 4-8 chiffres présenté comme un code ;
- dans les liens : tout ce qui suit le chemin (paramètres, ancre), qui peut contenir un identifiant personnel.

Un numéro surtaxé garde son préfixe (« [TÉLÉPHONE 089…] ») : c'est un indice d'arnaque, pas une donnée à toi.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ \-]?[A-Z0-9]{4}){2,7}(?:[ \-]?[A-Z0-9]{1,4})?\b", re.IGNORECASE)
_CARTE = re.compile(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)")
_TEL = re.compile(
    r"(?<![\w/])(?:(?:\+|00)\s?33\s?\(?0?\)?\s?[1-9]|0[\s.]?[1-9])(?:[\s.\-]?\d){8}(?![\d])"
    r"|(?<![\w/])(?:\+|00)\s?(?!33)\d{2,3}(?:[\s.\-]?\d{2,4}){3,5}(?!\d)"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)\b")
_VILLE = r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'\-]+(?:[ \-][A-ZÀ-Ý][A-Za-zÀ-ÿ'\-]+)*"
_ADRESSE = re.compile(
    r"\b\d{1,4}(?:\s?(?:bis|ter))?,?\s+(?i:rue|avenue|av\.|boulevard|bd|place|allée|allee|impasse|chemin|cours|quai|"
    r"route|square|résidence|residence|lotissement|lieu-dit)\b(?:\s+[A-Za-zÀ-ÿ'\-]+){1,6}"
    r"(?:,?\s*\d{5}\s+" + _VILLE + r")?"
)
_CODE_POSTAL_VILLE = re.compile(r"\b\d{5}\s+" + _VILLE + r"\b")
_CODE = re.compile(
    r"((?:code|otp|mot de passe|pin|cryptogramme|cvv|cvc)[^\d\n]{0,25})(\d{3,8})\b",
    re.IGNORECASE,
)
_URL = re.compile(r"(?i)\b((?:https?|hxxps?)://[^\s<>\"']+)")


def _luhn(chiffres: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _iban_valide(brut: str) -> bool:
    compact = re.sub(r"[ \-]", "", brut).upper()
    if not (15 <= len(compact) <= 34) or not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    tourne = compact[4:] + compact[:4]
    try:
        nombre = int("".join(str(int(ch, 36)) for ch in tourne))
    except ValueError:
        return False
    return nombre % 97 == 1


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def _motif_souple(valeur: str) -> re.Pattern[str] | None:
    """Une donnée déclarée, reconnue même avec d'autres espaces, tirets ou points (et sans accents)."""
    morceaux = [re.escape(m) for m in re.split(r"[\s.\-]+", _sans_accents(valeur).strip()) if m]
    if not morceaux or sum(len(m) for m in morceaux) < 3:
        return None
    return re.compile(r"(?<!\w)" + r"[\s.,\-]*".join(morceaux) + r"(?!\w)", re.IGNORECASE)


def _remplacer_souple(texte: str, valeur: str, jeton: str) -> str:
    motif = _motif_souple(valeur)
    if motif is None:
        return texte
    # On cherche dans la version sans accents, on remplace aux mêmes positions (la longueur NFD/NFC peut différer :
    # on travaille caractère par caractère sur un texte déjà décomposé).
    decompose = unicodedata.normalize("NFD", texte)
    carte: list[int] = []
    sans: list[str] = []
    for i, c in enumerate(decompose):
        if unicodedata.category(c) != "Mn":
            carte.append(i)
            sans.append(c)
    sans_txt = "".join(sans)
    morceaux: list[str] = []
    dernier = 0
    for m in motif.finditer(sans_txt):
        debut = carte[m.start()]
        fin = carte[m.end() - 1] + 1
        while fin < len(decompose) and unicodedata.category(decompose[fin]) == "Mn":
            fin += 1
        morceaux.append(decompose[dernier:debut])
        morceaux.append(jeton)
        dernier = fin
    if not morceaux:
        return texte
    morceaux.append(decompose[dernier:])
    return unicodedata.normalize("NFC", "".join(morceaux))


def _url_sans_parametres(m: re.Match[str]) -> str:
    url = m.group(1)
    coupe = re.split(r"[?#]", url, maxsplit=1)
    return coupe[0] + ("?[…]" if len(coupe) > 1 else "")


def _remplacer_tel(m: re.Match[str]) -> str:
    chiffres = re.sub(r"\D", "", m.group(0))
    if chiffres.startswith("0033"):
        chiffres = "0" + chiffres[4:]
    elif chiffres.startswith("33") and len(chiffres) == 11:
        chiffres = "0" + chiffres[2:]
    if chiffres.startswith(("089", "081", "082", "0899")):
        return f"[TÉLÉPHONE {chiffres[:3]}…]"
    return "[TÉLÉPHONE]"


def _remplacer_carte(m: re.Match[str]) -> str:
    chiffres = re.sub(r"\D", "", m.group(0))
    if 13 <= len(chiffres) <= 19 and _luhn(chiffres):
        return "[CARTE]"
    return m.group(0)


def _remplacer_iban(m: re.Match[str]) -> str:
    return "[IBAN]" if _iban_valide(m.group(0)) else m.group(0)


def caviarder(texte: str, perso: dict[str, Iterable[str]] | None = None) -> str:
    """Le texte sans tes données personnelles. `perso` = section [moi] de config.toml."""
    if not texte:
        return texte
    resultat = texte
    perso = perso or {}
    # 1. Ce que tu as déclaré (le plus précis d'abord : adresses, puis noms…).
    declares = (("adresses", "[ADRESSE]"), ("emails", "[E-MAIL]"), ("telephones", "[TÉLÉPHONE]"), ("noms", "[NOM]"))
    for cle, jeton in declares:
        for valeur in sorted((str(v) for v in perso.get(cle, []) or []), key=len, reverse=True):
            resultat = _remplacer_souple(resultat, valeur, jeton)
    # 2. Les liens perdent leurs paramètres (avant les règles suivantes, qui pourraient les couper).
    resultat = _URL.sub(_url_sans_parametres, resultat)
    # 3. Les formes reconnaissables.
    resultat = _IBAN.sub(_remplacer_iban, resultat)
    resultat = _CARTE.sub(_remplacer_carte, resultat)
    resultat = _EMAIL.sub(lambda m: f"[E-MAIL]@{m.group(1)}", resultat)
    resultat = _TEL.sub(_remplacer_tel, resultat)
    resultat = _ADRESSE.sub("[ADRESSE]", resultat)
    resultat = _CODE_POSTAL_VILLE.sub("[CODE POSTAL] [VILLE]", resultat)
    resultat = _CODE.sub(lambda m: m.group(1) + "[CODE]", resultat)
    return resultat
