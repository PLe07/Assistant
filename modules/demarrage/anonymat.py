"""Rendre anonyme une sortie de commande avant de la garder comme fixture (capturer.py), et vérifier qu'il ne reste
rien : dossier personnel, nom de compte, nom complet, nom de l'ordinateur, adresses e-mail, UUID.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

COMPTE_FICTIF = "utilisateur"
MAISON_FICTIVE = f"/Users/{COMPTE_FICTIF}"
NOM_FICTIF = "Utilisateur Exemple"
ORDINATEUR_FICTIF = "Mac"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_UUID = re.compile(r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


@dataclass
class Secrets:
    """Ce qui ne doit jamais sortir du Mac."""

    maison: str
    compte: str
    nom_complet: str = ""
    ordinateurs: list[str] = field(default_factory=list)  # ComputerName, LocalHostName, hostname
    autres: list[str] = field(default_factory=list)  # mots ajoutés à la main (--masquer)

    def mots(self) -> list[str]:
        """Chaque mot sensible (au moins 3 lettres), avec et sans accents, du plus long au plus court."""
        bruts = [self.compte, *self.nom_complet.split(), *self.ordinateurs, *self.autres]
        for nom in self.ordinateurs:
            bruts += re.split(r"[\s’'-]+", nom)
        mots = {m for b in bruts for m in (b.strip(), sans_accents(b.strip())) if len(m.strip()) >= 3}
        mots -= {"Mac", "MacBook", "Air", "Pro", "iMac", "mini", "Studio", "local", "The", "les", "des", "Exemple"}
        return sorted(mots, key=len, reverse=True)


def anonymiser(texte: str, secrets: Secrets) -> str:
    texte = texte.replace(secrets.maison, MAISON_FICTIVE)
    numeros: dict[str, str] = {}

    def uuid(m: re.Match[str]) -> str:
        cle = m.group(0).upper()
        numeros.setdefault(cle, f"00000000-0000-0000-0000-{len(numeros) + 1:012d}")
        return numeros[cle]

    texte = _UUID.sub(uuid, texte)
    texte = _EMAIL.sub("adresse@exemple.fr", texte)
    if secrets.nom_complet.strip():
        texte = re.sub(re.escape(secrets.nom_complet.strip()), NOM_FICTIF, texte, flags=re.IGNORECASE)
    for nom in sorted(secrets.ordinateurs, key=len, reverse=True):
        if nom.strip():
            texte = re.sub(re.escape(nom.strip()), ORDINATEUR_FICTIF, texte, flags=re.IGNORECASE)
    for mot in secrets.mots():
        remplacement = COMPTE_FICTIF if mot in (secrets.compte, sans_accents(secrets.compte)) else "Anonyme"
        texte = re.sub(rf"(?<![\w]){re.escape(mot)}(?![\w])", remplacement, texte, flags=re.IGNORECASE)
    return texte


def fuites(texte: str, secrets: Secrets) -> list[str]:
    """Les mots sensibles encore présents (vide : rien ne fuit)."""
    plat = sans_accents(texte).casefold()
    trouves = [m for m in secrets.mots() if sans_accents(m).casefold() in plat]
    if secrets.maison.casefold() in texte.casefold():
        trouves.append(secrets.maison)
    trouves += [e for e in _EMAIL.findall(texte) if not e.endswith("@exemple.fr")]
    return trouves
