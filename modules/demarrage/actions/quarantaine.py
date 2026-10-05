"""La quarantaine des orphelins : le plist est déplacé (jamais effacé) dans
donnees/demarrage/quarantaine/<horodatage>/, avec un manifeste qui dit d'où il vient. `restaurer` le remet en place.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path, PurePosixPath
from typing import Any

from modules.demarrage.systeme import Systeme

MANIFESTE = "manifeste.json"


def empreinte(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def mettre(systeme: Systeme, chemin_plist: str, dossier: Path, infos: dict[str, Any]) -> Path:
    """Déplace le plist ; renvoie le dossier de quarantaine (qui contient le plist et le manifeste)."""
    source = systeme.chemin(chemin_plist)
    horodatage = time.strftime("%Y%m%d-%H%M%S", time.localtime(systeme.maintenant()))
    cible = dossier / "quarantaine" / horodatage
    n = 1
    while cible.exists():  # deux quarantaines dans la même seconde
        n += 1
        cible = dossier / "quarantaine" / f"{horodatage}-{n}"
    cible.mkdir(parents=True, mode=0o700)
    manifeste = {"original": chemin_plist, "fichier": PurePosixPath(chemin_plist).name, "sha256": empreinte(source),
                 "quand": systeme.maintenant(), **infos}  # fmt: skip
    (cible / MANIFESTE).write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.move(str(source), str(cible / manifeste["fichier"]))
    return cible


def lire_manifeste(dossier: Path) -> dict[str, Any]:
    return dict(json.loads((dossier / MANIFESTE).read_text(encoding="utf-8")))


def remettre(systeme: Systeme, dossier: Path) -> str:
    """Remet le plist à sa place d'origine. Refuse si un fichier l'occupe déjà, ou si le plist a été modifié."""
    m = lire_manifeste(dossier)
    fichier = dossier / m["fichier"]
    destination = systeme.chemin(m["original"])
    if destination.exists():
        raise FileExistsError(f"{m['original']} existe déjà : je ne l'écrase pas")
    if empreinte(fichier) != m["sha256"]:
        raise ValueError("le plist en quarantaine a été modifié depuis : je ne le remets pas")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(fichier), str(destination))
    os.replace(dossier / MANIFESTE, dossier / f"{MANIFESTE}.restaure")
    return str(m["original"])
