-- Schéma recopié à l'identique de modules/mails/memoire.py (2026-10-07).
CREATE TABLE IF NOT EXISTS parametres (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE IF NOT EXISTS mails (
id TEXT PRIMARY KEY, statut TEXT, traite_le TEXT, recu_le TEXT,
bac TEXT, source TEXT, vaut_mon_temps INTEGER, raison TEXT,
expediteur TEXT, objet TEXT
);
CREATE TABLE IF NOT EXISTS echecs (id TEXT PRIMARY KEY, tentatives INTEGER);
