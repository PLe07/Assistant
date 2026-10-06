"""Le déplacement sûr (§9) : copier, vérifier l'empreinte, puis seulement supprimer l'original. Jamais d'écrasement.

- La copie est créée en mode exclusif (O_EXCL) : si le nom est pris entre-temps, le suivant (« -2 ») est choisi.
- L'empreinte SHA-256 de la copie doit être celle de l'original, sinon la copie est effacée et rien ne bouge.
- L'original n'est supprimé que s'il n'a pas changé pendant ce temps (sinon il reste, et c'est noté).
- Chaque étape est écrite dans le journal des actions, ce qui permet d'annuler (`ramener`).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from modules.trieur.base import Base
from modules.trieur.classement.nommage import libre

BLOC = 1 << 20


class DeplacementImpossible(Exception):
    pass


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        while bloc := f.read(BLOC):
            h.update(bloc)
    return h.hexdigest()


def copier_sans_ecraser(source: Path, dossier: Path, nom: str) -> Path:
    """Une copie de « source » dans « dossier », sous « nom » ou le premier nom libre : jamais sur un fichier."""
    dossier.mkdir(parents=True, exist_ok=True)
    for _ in range(1000):
        cible = libre(dossier, nom)
        try:
            fd = os.open(cible, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue  # pris entre-temps : le suivant
        try:
            with os.fdopen(fd, "wb") as f, source.open("rb") as s:
                shutil.copyfileobj(s, f, BLOC)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            cible.unlink(missing_ok=True)
            raise
        try:
            shutil.copystat(source, cible)
        except OSError:
            pass
        return cible
    raise DeplacementImpossible(f"aucun nom libre pour {nom}")


def deplacer(source: Path, dossier: Path, nom: str, base: Base, element: int, genre: str = "range",
             attendue: str | None = None, garder_source: bool = False) -> Path:  # fmt: skip
    """Range « source » dans « dossier » sous « nom » (ou « nom-2 »…) et renvoie le chemin final.
    attendue : l'empreinte lue avant le traitement ; si le fichier a changé depuis, rien ne bouge."""
    h = empreinte(source)
    if attendue and h != attendue:
        raise DeplacementImpossible("le fichier a changé pendant son traitement : il sera repris")
    cible = copier_sans_ecraser(source, dossier, nom)
    if empreinte(cible) != h:
        cible.unlink(missing_ok=True)
        raise DeplacementImpossible("la copie ne correspond pas à l'original : rien n'a bougé")
    base.noter_action(element, genre, str(source), str(cible), h)
    if garder_source:
        return cible
    if empreinte(source) != h:
        base.noter_action(element, "source_gardee", str(source), None, h)
        return cible
    source.unlink()
    base.noter_action(element, "supprime_source", str(source), str(cible), h)
    return cible


def creer(contenu_temporaire: Path, dossier: Path, nom: str, base: Base, element: int) -> Path:
    """Un fichier fabriqué par le Trieur (le PDF cherchable d'une photo) : rangé, puis le temporaire effacé."""
    cible = copier_sans_ecraser(contenu_temporaire, dossier, nom)
    h = empreinte(cible)
    if h != empreinte(contenu_temporaire):
        cible.unlink(missing_ok=True)
        raise DeplacementImpossible("copie incorrecte du PDF fabriqué")
    base.noter_action(element, "cree", None, str(cible), h)
    contenu_temporaire.unlink(missing_ok=True)
    return cible


def ramener(cible: Path, origine: Path, base: Base, element: int) -> Path:
    """Annuler un rangement : « cible » retourne là où il était (« origine »), ou à côté si la place est prise."""
    h = empreinte(cible)
    retour = copier_sans_ecraser(cible, origine.parent, origine.name)
    if empreinte(retour) != h:
        retour.unlink(missing_ok=True)
        raise DeplacementImpossible("copie de retour incorrecte : le fichier rangé n'a pas bougé")
    cible.unlink()
    base.noter_action(element, "ramene", str(cible), str(retour), h)
    return retour
