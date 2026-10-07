"""Le journal de Quotidien (`~/Library/Logs/Quotidien/quotidien.log`), caviardé, tournant (5 × 1 Mo)."""

from __future__ import annotations

import logging
import logging.handlers
import os

from quotidien import config
from quotidien.caviardage import caviarder

_NOM = "quotidien"


class _Caviardeur(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return caviarder(super().format(record))


def log() -> logging.Logger:
    journal = logging.getLogger(_NOM)
    if getattr(journal, "_quotidien_pret", False):
        return journal
    journal.setLevel(logging.INFO)
    journal.propagate = False
    try:
        dossier = config.dossier_logs()
        dossier.mkdir(parents=True, exist_ok=True)
        os.chmod(dossier, 0o700)
        fichier = logging.handlers.RotatingFileHandler(
            dossier / "quotidien.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        fichier.setFormatter(_Caviardeur("%(asctime)s %(levelname)s %(message)s"))
        journal.addHandler(fichier)
    except OSError:
        journal.addHandler(logging.NullHandler())
    journal._quotidien_pret = True  # type: ignore[attr-defined]
    return journal


def oublier() -> None:
    """Les tests changent de dossier personnel : le journal suivant repart du bon dossier."""
    journal = logging.getLogger(_NOM)
    for h in list(journal.handlers):
        journal.removeHandler(h)
        h.close()
    journal._quotidien_pret = False  # type: ignore[attr-defined]
