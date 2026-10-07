-- Schéma recopié à l'identique de modules/demarrage/db.py (dépôt de l'assistant, 2026-10-07).
CREATE TABLE IF NOT EXISTS etat (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY, ts REAL NOT NULL, inventaire TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS apparitions (
    id TEXT PRIMARY KEY, label TEXT NOT NULL, source TEXT NOT NULL, premiere_vue REAL NOT NULL,
    derniere_vue REAL NOT NULL, notifiee REAL
);
CREATE TABLE IF NOT EXISTS signatures (chemin TEXT PRIMARY KEY, donnees TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS releves (ts REAL PRIMARY KEY, mode TEXT NOT NULL, cpu_total_pct REAL);
CREATE TABLE IF NOT EXISTS mesures (
    ts REAL NOT NULL, mode TEXT NOT NULL, fiche_id TEXT NOT NULL, cpu_s REAL NOT NULL, rss_ko INTEGER NOT NULL,
    puissance REAL, veille INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS mesures_ts ON mesures (ts);
CREATE TABLE IF NOT EXISTS sessions (
    boot REAL PRIMARY KEY, connexion REAL, calme REAL, details TEXT
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, fiche_id TEXT NOT NULL, label TEXT NOT NULL, genre TEXT NOT NULL,
    avant TEXT, apres TEXT, commandes TEXT, details TEXT, annulee REAL
);
CREATE TABLE IF NOT EXISTS agregats (
    jour TEXT NOT NULL, fiche_id TEXT NOT NULL, mode TEXT NOT NULL, cpu_s REAL, rss_moy_ko INTEGER, puissance REAL,
    veille_n INTEGER, n INTEGER, PRIMARY KEY (jour, fiche_id, mode)
);
CREATE TABLE IF NOT EXISTS zsh (ts REAL PRIMARY KEY, mediane_ms REAL, details TEXT);
CREATE TABLE IF NOT EXISTS notifications (ts REAL NOT NULL, genre TEXT NOT NULL, titre TEXT, texte TEXT);
