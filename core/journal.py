"""Le journal partagé : logs/assistant.log, une ligne par événement, lisible.

Plusieurs programmes écrivent dans le même fichier (superviseur, modules, icône).
Seul le superviseur le fait « tourner » (archive quand il dépasse 2 Mo) ; les autres
le rouvrent automatiquement grâce à WatchedFileHandler.
"""

import logging
import sys
from logging.handlers import WatchedFileHandler

from core.config import LOGS

FICHIER = LOGS / "assistant.log"
TAILLE_MAX = 2_000_000
ARCHIVES = 4

class _Format(logging.Formatter):
    def format(self, record):
        record.composant = record.name.removeprefix("assistant.")  # [superviseur] plutôt que [assistant.superviseur]
        return super().format(record)


_FORMAT = _Format("%(asctime)s %(levelname)-7s [%(composant)s] %(message)s", "%Y-%m-%d %H:%M:%S")


def journal(nom: str, ecran: bool = False) -> logging.Logger:
    """Le journal d'un composant (« superviseur », « battement »…)."""
    LOGS.mkdir(exist_ok=True)
    racine = logging.getLogger("assistant")
    if not racine.handlers:
        racine.setLevel(logging.INFO)
        fichier = WatchedFileHandler(FICHIER, encoding="utf-8")
        fichier.setFormatter(_FORMAT)
        racine.addHandler(fichier)
    if ecran and not any(getattr(h, "_ecran", False) for h in racine.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(_FORMAT)
        console._ecran = True
        racine.addHandler(console)
    return racine.getChild(nom)


def faire_tourner() -> bool:
    """Archive assistant.log s'il est trop gros (assistant.log.1 … .4). Appelé par le superviseur."""
    if not FICHIER.exists() or FICHIER.stat().st_size < TAILLE_MAX:
        return False
    for i in range(ARCHIVES - 1, 0, -1):
        ancien = FICHIER.with_name(f"assistant.log.{i}")
        if ancien.exists():
            ancien.replace(FICHIER.with_name(f"assistant.log.{i + 1}"))
    FICHIER.replace(FICHIER.with_name("assistant.log.1"))
    return True


def dernieres_lignes(n: int = 30) -> list[str]:
    if not FICHIER.exists():
        return []
    return FICHIER.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
