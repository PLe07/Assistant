"""Le caviardage : rien de personnel ne sort d'un journal vers la page, l'iPhone ou une notification.

`caviarder(texte)` retire les adresses e-mail, les chemins personnels (`/Users/<toi>/…` devient `~/…`), les jetons et
clés (Anthropic, Google, porteurs, longues suites aléatoires), les IBAN, numéros de carte et de téléphone, et les URL
avec paramètres. `contient_sensible(texte)` dit s'il reste quelque chose : la page iPhone n'est jamais écrite sinon.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
CHEMIN_PERSO = re.compile(r"(?:/Users|/home)/[^/\s'\"]+")
CHEMIN_PRIVE = re.compile(r"/(?:private/)?var/folders/[^\s'\"]+")
CLE_ANTHROPIC = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")
CLE_GOOGLE = re.compile(r"\b(?:AIza[0-9A-Za-z_\-]{20,}|ya29\.[0-9A-Za-z_\-]{20,}|1//[0-9A-Za-z_\-]{20,})")
PORTEUR = re.compile(r"(?i)\b(bearer|token|jeton|password|mot de passe|secret|api[_-]?key|cle|clé)\b(\s*[:=]\s*|\s+)"
                     r"[\"']?[^\s\"',;]{6,}")  # fmt: skip
PARAMETRE_URL = re.compile(r"(?i)([?&](?:t|token|jeton|key|cle|code|auth|sig|signature)=)[^&\s#]+")
LONG_ALEATOIRE = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
CARTE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")
TELEPHONE = re.compile(r"(?<![\w+])(?:(?:\+|00)\s?33\s?|0)[1-9](?:[\s.\-]?\d{2}){4}(?![\w])")
SECU = re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b")


def caviarder(texte: str, longueur_max: int = 400, compacter: bool = True) -> str:
    """Le texte sans rien de personnel, coupé à `longueur_max` caractères (`compacter` : espaces réduits)."""
    if not texte:
        return ""
    t = str(texte)
    t = CLE_ANTHROPIC.sub("[clé]", t)
    t = CLE_GOOGLE.sub("[clé]", t)
    t = PARAMETRE_URL.sub(r"\1[jeton]", t)
    t = PORTEUR.sub(lambda m: f"{m.group(1)}{m.group(2)}[secret]", t)
    t = EMAIL.sub("[e-mail]", t)
    t = CHEMIN_PERSO.sub("~", t)
    t = CHEMIN_PRIVE.sub("[dossier temporaire]", t)
    t = IBAN.sub("[iban]", t)
    t = SECU.sub("[numéro]", t)
    t = CARTE.sub("[numéro]", t)
    t = TELEPHONE.sub("[téléphone]", t)
    t = LONG_ALEATOIRE.sub("[jeton]", t)
    if compacter:
        t = " ".join(t.split())
    if len(t) > longueur_max:
        t = t[: longueur_max - 1].rstrip() + "…"
    return t


# Ce que la page iPhone et le rapport ne doivent jamais contenir (vérifié avant chaque écriture).
MOTIFS_SENSIBLES = {
    "e-mail": EMAIL,
    "chemin personnel": re.compile(r"/Users/|/home/|/var/folders/"),
    "clé Anthropic": CLE_ANTHROPIC,
    "clé Google": CLE_GOOGLE,
    "jeton dans une URL": re.compile(r"(?i)[?&](t|token|jeton)=[A-Za-z0-9_\-]{8,}"),
    "suite aléatoire": LONG_ALEATOIRE,
    "IBAN": IBAN,
}


def contient_sensible(texte: str, jetons: tuple[str, ...] = ()) -> list[str]:
    """Les motifs sensibles trouvés (vide : rien)."""
    trouves = [nom for nom, motif in MOTIFS_SENSIBLES.items() if motif.search(texte or "")]
    if any(j and j in (texte or "") for j in jetons):
        trouves.append("jeton du tableau de bord")
    return trouves
