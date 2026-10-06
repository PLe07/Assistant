"""Le journal de Bouclier (~/Library/Logs/Bouclier/bouclier.log), toujours caviardé.

Chaque ligne passe par `caviardage.caviarder` avant d'être écrite : un message analysé, une adresse ou un numéro
ne peuvent pas s'y retrouver en clair, même si un module oublie de le retirer.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any

from bouclier import caviardage

NOM = "bouclier"


class FiltreCaviardage(logging.Filter):
    def __init__(self, perso: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.perso = perso or {}

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - un message mal formé ne doit pas casser le journal
            message = str(record.msg)
        record.msg = caviardage.caviarder(message, self.perso)
        record.args = None
        if record.exc_info and record.exc_info[1] is not None:
            # La pile d'une exception peut contenir le texte analysé : on n'en garde que le type.
            record.msg += f" [{record.exc_info[0].__name__ if record.exc_info[0] else 'erreur'}]"
            record.exc_info = None
            record.exc_text = None
        return True


def configurer(dossier: Path, perso: dict[str, Any] | None = None, console: bool = False) -> logging.Logger:
    log = logging.getLogger(NOM)
    log.setLevel(logging.INFO)
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    for f in list(log.filters):
        log.removeFilter(f)
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / "bouclier.log"
    gestionnaire = logging.handlers.RotatingFileHandler(fichier, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    gestionnaire.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(module)s] %(message)s"))
    filtre = FiltreCaviardage(perso)
    gestionnaire.addFilter(filtre)
    log.addHandler(gestionnaire)
    if console:
        sortie = logging.StreamHandler()
        sortie.setFormatter(logging.Formatter("%(message)s"))
        sortie.addFilter(filtre)
        log.addHandler(sortie)
    log.propagate = False
    try:
        os.chmod(fichier, 0o600)
    except OSError:
        pass
    return log


def log() -> logging.Logger:
    return logging.getLogger(NOM)
