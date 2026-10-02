"""La base de la veille (donnees/veille/veille.db, sur ton Mac, lisible par toi seul).

- articles : chaque article vu une fois (pour ne te montrer que les nouveautés), et ce que Claude en a dit ;
- revues : chaque veille que tu as lancée (combien d'articles lus, retenus, l'état des sources).
Tout est public (des articles de sites officiels) ; oublié au bout de 90 jours.
"""

import os
import sqlite3
from contextlib import contextmanager

from modules.veille import parametres as p

# statut d'un article : nouveau (pas encore trié) · retenu · ecarte (par Claude) · hors_sujet (sur ton Mac)
# · ancien (déjà vieux quand l'Assistant l'a vu pour la première fois).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY, cle TEXT UNIQUE, source TEXT, titre TEXT, lien TEXT, resume TEXT, publie REAL,
    vu REAL, revu REAL, statut TEXT, importance INTEGER DEFAULT 0, pourquoi TEXT DEFAULT '', ue INTEGER DEFAULT 0,
    revue INTEGER
);
CREATE TABLE IF NOT EXISTS revues (
    id INTEGER PRIMARY KEY, quand REAL, lus INTEGER, nouveaux INTEGER, hors_sujet INTEGER, en_bref TEXT,
    trie INTEGER, erreur TEXT, sources TEXT
);
"""


@contextmanager
def connexion():
    p.DOSSIER.mkdir(parents=True, exist_ok=True)
    nouveau = not p.BASE.exists()
    db = sqlite3.connect(p.BASE, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        if nouveau:
            os.chmod(p.BASE, 0o600)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_SCHEMA)
        with db:
            yield db
    finally:
        db.close()


def existe() -> bool:
    return p.BASE.exists()
