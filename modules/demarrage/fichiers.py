"""Les fichiers du Mac vus à travers le Systeme : liens symboliques suivis sous la racine (vraie ou fausse),
existence d'un programme, recherche d'une commande dans le PATH de launchd.
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath

from modules.demarrage.systeme import Systeme

# Le PATH que launchd donne aux agents, plus Homebrew (Apple Silicon puis Intel).
CHEMINS_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/opt/homebrew/bin", "/usr/local/bin")
SAUTS_MAX = 20


def resoudre(systeme: Systeme, chemin: str) -> str | None:
    """Le chemin réel (liens suivis), écrit comme sur le Mac ; None s'il n'existe pas ou si un lien est cassé."""
    p = PurePosixPath(chemin)
    if not p.is_absolute():
        return None
    actuel = PurePosixPath("/")
    restant = list(p.parts[1:])
    sauts = 0
    while restant:
        nom = restant.pop(0)
        if nom in ("", "."):
            continue
        if nom == "..":
            actuel = actuel.parent
            continue
        candidat = actuel / nom
        reel = systeme.chemin(str(candidat))
        try:
            if reel.is_symlink():
                sauts += 1
                if sauts > SAUTS_MAX:
                    return None  # boucle de liens
                cible = PurePosixPath(os.readlink(reel))
                if cible.is_absolute():
                    actuel, restant = PurePosixPath("/"), [*cible.parts[1:], *restant]
                else:
                    restant = [*cible.parts, *restant]
                continue
            if not reel.exists():
                return None
        except OSError:
            return None
        actuel = candidat
    return str(actuel)


def existe(systeme: Systeme, chemin: str | None) -> bool:
    return bool(chemin) and resoudre(systeme, str(chemin)) is not None


def localiser(systeme: Systeme, programme: str, repertoire: str | None = None) -> str | None:
    """Où est vraiment ce programme : chemin absolu tel quel, relatif au WorkingDirectory, ou nom dans le PATH."""
    if programme.startswith("/"):
        return programme
    if "/" in programme:
        return str(PurePosixPath(repertoire) / programme) if repertoire else None
    if repertoire and existe(systeme, str(PurePosixPath(repertoire) / programme)):
        return str(PurePosixPath(repertoire) / programme)
    for dossier in CHEMINS_PATH:
        candidat = f"{dossier}/{programme}"
        if existe(systeme, candidat):
            return candidat
    return None


def absent_certain(systeme: Systeme, chemin: str | None) -> bool:
    """Vrai si le programme manque pour de bon : son plus proche dossier existant se lit. Faux si ce dossier nous
    est fermé (on ne voit pas dedans : on ne conclut pas)."""
    if not chemin or not chemin.startswith("/"):
        return False
    for parent in PurePosixPath(chemin).parents:
        reel = systeme.chemin(str(parent))
        try:
            if reel.is_dir():
                next(iter(reel.iterdir()), None)
                return True
            if reel.exists():
                return True  # un fichier là où on attendait un dossier : le chemin est cassé
        except OSError:
            return False
    return True
