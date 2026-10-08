"""Le vrai démon du tableau de bord (`tableau demon --sans-barre`), avec un espion à l'intérieur de son processus.

Un crochet d'audit Python voit chaque ouverture de fichier et chaque opération sur le disque du démon. Toute
écriture (ou connexion SQLite directe) sous les dossiers des faux modules (`TDB_ESPION_RACINE`) est notée dans
`TDB_ESPION_SORTIE` : le test exige que ce fichier reste vide. Les simples lectures (journaux, copie des bases)
sont permises, et c'est tout ce que le tableau de bord fait chez les autres.
"""

from __future__ import annotations

import os
import sys
from typing import Any

RACINE = os.environ["TDB_ESPION_RACINE"]
SORTIE = os.environ["TDB_ESPION_SORTIE"]
ECRITURE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
INTERDITS = {
    "os.remove", "os.rename", "os.replace", "os.mkdir", "os.chmod", "os.chown", "os.utime", "os.truncate",
    "os.rmdir", "shutil.rmtree", "shutil.move", "os.link", "os.symlink", "sqlite3.connect",
}  # fmt: skip
_dedans = False


def _sous_la_racine(valeur: Any) -> bool:
    try:
        return isinstance(valeur, (str, bytes, os.PathLike)) and os.fsdecode(valeur).startswith(RACINE)
    except (TypeError, ValueError):
        return False


def _crochet(evenement: str, args: tuple[Any, ...]) -> None:
    global _dedans
    if _dedans:
        return
    interdit = False
    if evenement == "open" and args and _sous_la_racine(args[0]):
        mode = args[1] if len(args) > 1 else None
        drapeaux = args[2] if len(args) > 2 else 0
        interdit = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(drapeaux, int) and bool(drapeaux & ECRITURE)
        )
    elif evenement in INTERDITS:
        interdit = any(_sous_la_racine(a) for a in args)
    if interdit:
        _dedans = True
        try:
            with open(SORTIE, "a", encoding="utf-8") as f:
                f.write(f"{evenement} {args!r}\n")
        finally:
            _dedans = False


sys.addaudithook(_crochet)

from tableau.cli import main  # noqa: E402 - l'espion d'abord, le démon ensuite

sys.exit(main(["demon", "--sans-barre"]))
