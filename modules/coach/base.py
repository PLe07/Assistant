"""La base du coach (donnees/coach/coach.db, sur ton Mac, lisible par toi seul).

- fichiers / morceaux : tes cours découpés en morceaux d'environ une page (pour choisir l'extrait du jour) ;
- questions : chaque question posée une fois, avec sa « boîte » de révision (1 = à revoir vite, 5 = acquise) ;
- seances : chaque fois qu'une question t'est posée (un jour), ta réponse, ta note et la correction.
"""

import os
import sqlite3
from contextlib import contextmanager

from modules.coach import parametres as p

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fichiers (chemin TEXT PRIMARY KEY, matiere TEXT, maj REAL, morceaux INTEGER, erreur TEXT);
CREATE TABLE IF NOT EXISTS morceaux (id INTEGER PRIMARY KEY, chemin TEXT, matiere TEXT, numero INTEGER, texte TEXT);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY, cree REAL, matiere TEXT, morceau INTEGER, question TEXT, type TEXT, choix TEXT,
    bonne INTEGER, attendu TEXT, notion TEXT, a_verifier INTEGER DEFAULT 0, boite INTEGER DEFAULT 1, prochaine REAL
);
CREATE TABLE IF NOT EXISTS seances (
    id INTEGER PRIMARY KEY, jour TEXT, ordre INTEGER, question INTEGER, reponse TEXT, note INTEGER,
    correction TEXT, a_retenir TEXT, statut TEXT, quand REAL
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
