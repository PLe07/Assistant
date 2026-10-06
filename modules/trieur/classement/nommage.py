"""Le nom de fichier (§5) et le dossier de rangement.

Nom : AAAA-MM-JJ_Emetteur_Type_Detail_Montant.ext, 120 caractères au plus.
- « sans-date » quand le document n'a pas de date ;
- les morceaux vides disparaissent (pas de « __ ») ;
- trop long : le détail est raccourci d'abord, puis l'émetteur ;
- un nom déjà pris reçoit « -2 », « -3 »… : rien n'est jamais écrasé (le déplacement vérifie encore, D-xx).

Dossier : le modèle de reglages["arborescence"][type], sous « Classés » ({annee}, {banque}, {emetteur}) ; un
modèle qui commence par « ~/ » désigne un de tes dossiers (D-10).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from modules.trieur.classement import Classement
from modules.trieur.classement.montants import en_francais

_INTERDITS = re.compile(r'[/\\:*?"<>|\x00-\x1f‪-‮⁦-⁩]')


def propre(texte: str, max_: int = 60) -> str:
    """Un morceau de nom : sans caractère interdit, espaces et apostrophes en tirets, accents gardés (NFC)."""
    t = unicodedata.normalize("NFC", texte or "")
    t = _INTERDITS.sub(" ", t).replace("&", " et ").replace("'", " ").replace("’", " ")
    t = re.sub(r"[\s_]+", "-", t.strip())
    t = re.sub(r"-{2,}", "-", t).strip("-.")
    return t[:max_].rstrip("-.")


def nom(c: Classement, extension: str, reglages: dict[str, Any]) -> str:
    longueur_max = int(reglages["classement"]["nom_max"])
    ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
    debut = c.date.isoformat() if c.date else "sans-date"
    emetteur = propre(c.emetteur or "", 40)
    type_ = propre(c.libelle or c.type, 30)
    detail = propre(c.detail, 40)
    montant = f"{en_francais(c.montant)}€" if c.montant is not None else ""

    def assembler(e: str, d: str) -> str:
        return "_".join(x for x in (debut, e, type_, d, montant) if x) + ext

    sortie = assembler(emetteur, detail)
    while len(sortie) > longueur_max and detail:
        detail = detail[: max(0, len(detail) - (len(sortie) - longueur_max))].rstrip("-.")
        sortie = assembler(emetteur, detail)
    while len(sortie) > longueur_max and emetteur:
        emetteur = emetteur[: max(0, len(emetteur) - (len(sortie) - longueur_max))].rstrip("-.")
        sortie = assembler(emetteur, detail)
    return sortie[: longueur_max - len(ext)] + ext if len(sortie) > longueur_max else sortie


def libre(dossier: Path, nom_: str) -> Path:
    """Le premier chemin libre : « nom.pdf », sinon « nom-2.pdf », « nom-3.pdf »…"""
    cible = dossier / nom_
    if not cible.exists() and not cible.is_symlink():
        return cible
    racine, ext = Path(nom_).stem, Path(nom_).suffix
    n = 2
    while True:
        cible = dossier / f"{racine}-{n}{ext}"
        if not cible.exists() and not cible.is_symlink():
            return cible
        n += 1


def dossier(c: Classement, reglages: dict[str, Any], cle: str | None = None) -> Path:
    """Le dossier (relatif à « Classés ») : « Factures/2026 », « Banque/BNP Paribas/2026 »…"""
    modele = reglages["arborescence"].get(cle or c.type) or reglages["arborescence"]["autre"]
    valeurs = {"annee": str(c.date.year) if c.date else "Sans date", "banque": c.emetteur or "Autre banque",
               "emetteur": c.emetteur or "Inconnu", "extension": ""}  # fmt: skip
    racine = ""
    if modele.startswith(("~/", "/")):  # aligné sur un dossier à toi (« trieur arborescence --appliquer »)
        racine, modele = ("~" if modele.startswith("~") else "/"), modele.lstrip("~/")
    morceaux = []
    for partie in modele.split("/"):
        rempli = re.sub(r"\{(\w+)\}", lambda m: valeurs.get(m.group(1), ""), partie)
        rempli = unicodedata.normalize("NFC", _INTERDITS.sub(" ", rempli)).strip(" .")
        if rempli and rempli not in (".", ".."):
            morceaux.append(rempli)
    if not morceaux:
        return Path("Divers")
    return Path(racine, *morceaux).expanduser() if racine else Path(*morceaux)
