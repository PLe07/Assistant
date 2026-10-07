-- Schéma recopié à l'identique de modules/corvees/db.py (dépôt de l'assistant, 2026-10-07).
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL, token TEXT NOT NULL,
    attrs TEXT NOT NULL DEFAULT '{}', jour TEXT NOT NULL, session_id INTEGER
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS agregats (
    jour TEXT NOT NULL, source TEXT NOT NULL, token TEXT NOT NULL, n INTEGER NOT NULL,
    PRIMARY KEY (jour, source, token)
);
CREATE TABLE IF NOT EXISTS decisions (
    signature TEXT PRIMARY KEY, id TEXT, statut TEXT NOT NULL, jusqua REAL, frequence_ref REAL, quand REAL,
    tokens TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS candidats (
    id TEXT PRIMARY KEY, signature TEXT UNIQUE NOT NULL, type TEXT, donnees TEXT, score REAL,
    premier_vu REAL, dernier_vu REAL, analyse REAL
);
CREATE TABLE IF NOT EXISTS couts (
    id INTEGER PRIMARY KEY, quand REAL, mois TEXT, modele TEXT, jetons_entree INTEGER, jetons_sortie INTEGER,
    cout_usd REAL, ok INTEGER
);
CREATE TABLE IF NOT EXISTS descriptions (signature TEXT PRIMARY KEY, source TEXT, donnees TEXT, quand REAL);
CREATE TABLE IF NOT EXISTS etat (cle TEXT PRIMARY KEY, valeur TEXT, maj REAL);
