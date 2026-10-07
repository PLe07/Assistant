-- Schéma recopié à l'identique de bouclier/bouclier/db.py (dépôt de l'assistant, 2026-10-07).
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date REAL NOT NULL,
    source TEXT NOT NULL,
    niveau TEXT NOT NULL,
    score INTEGER NOT NULL,
    titre TEXT NOT NULL,
    texte_caviarde TEXT NOT NULL,
    raisons TEXT NOT NULL,
    ia TEXT NOT NULL DEFAULT 'non',
    cout_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS analyses_date ON analyses(date);
CREATE TABLE IF NOT EXISTS depenses_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date REAL NOT NULL,
    mois TEXT NOT NULL,
    cout_usd REAL NOT NULL,
    jetons_entree INTEGER NOT NULL,
    jetons_sortie INTEGER NOT NULL,
    usage TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rdap (domaine TEXT PRIMARY KEY, creation TEXT, verifie_le REAL NOT NULL, erreur TEXT);
CREATE TABLE IF NOT EXISTS gmail (dossier TEXT PRIMARY KEY, uidvalidity TEXT NOT NULL, dernier_uid INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS comptes (
    service TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    categorie TEXT NOT NULL,
    nature TEXT NOT NULL,
    domaines TEXT NOT NULL,
    premiere_vue TEXT,
    derniere_activite TEXT,
    sources TEXT NOT NULL,
    signaux TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'a_trier',
    vu_le REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS fuites_signalees (nom TEXT PRIMARY KEY, service TEXT NOT NULL, signalee_le REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date REAL NOT NULL,
    genre TEXT NOT NULL,
    titre TEXT NOT NULL,
    envoyee INTEGER NOT NULL,
    motif TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS entrees_vues (chemin TEXT PRIMARY KEY, taille INTEGER, traitee_le REAL, etat TEXT);
