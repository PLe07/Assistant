-- Échantillon anonymisé de trieur.db (schéma exact, 12 lignes au plus par table).
CREATE TABLE elements (
    id INTEGER PRIMARY KEY,
    chemin TEXT NOT NULL,          -- là où le fichier a été trouvé
    nom TEXT NOT NULL,             -- son nom d'origine
    source TEXT NOT NULL,          -- boite, a_trier, finder, cli, api, telechargements, courriel
    note TEXT,
    parent INTEGER,                -- la pièce jointe d'un courriel : l'élément du courriel
    empreinte TEXT,                -- SHA-256 du contenu
    taille INTEGER,
    etat TEXT NOT NULL,            -- en_attente, en_cours, classe, a_verifier, photos, doublon, ignore, erreur, annule
    ajoute REAL NOT NULL,
    traite REAL,
    essais INTEGER NOT NULL DEFAULT 0,
    erreur TEXT,
    type TEXT, confiance REAL, emetteur TEXT, date TEXT, montant TEXT, par TEXT,
    destination TEXT,              -- le fichier rangé
    infos TEXT                     -- JSON : numéro, détail, raisons, original archivé…
);
CREATE TABLE actions (
    id INTEGER PRIMARY KEY,
    element INTEGER NOT NULL,
    quand REAL NOT NULL,
    genre TEXT NOT NULL,           -- range, archive, cree, supprime_source, alias, rappel, tag
    source TEXT, cible TEXT, empreinte TEXT,
    defaite REAL                   -- quand l'action a été annulée
);
CREATE TABLE appris (
    cle TEXT NOT NULL, type TEXT NOT NULL, points REAL NOT NULL, fois INTEGER NOT NULL DEFAULT 1, quand REAL,
    PRIMARY KEY (cle, type)
);
CREATE TABLE garanties (
    id INTEGER PRIMARY KEY,
    element INTEGER,               -- la facture (vide : une garantie saisie à la main)
    produit TEXT NOT NULL, emetteur TEXT, prix TEXT,
    achat TEXT NOT NULL, fin TEXT NOT NULL, mois INTEGER NOT NULL, source TEXT NOT NULL,
    facture TEXT,                  -- le chemin de la facture rangée
    alias TEXT,                    -- l'alias dans Garanties/
    rappels TEXT,                  -- JSON : les rappels créés dans l'app Rappels
    retractation TEXT,             -- la date du rappel de rétractation (achat en ligne)
    cree REAL NOT NULL, supprimee REAL
);
CREATE TABLE meta (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE depenses_ia (
    id INTEGER PRIMARY KEY, quand REAL NOT NULL, mois TEXT NOT NULL, element INTEGER,
    entree INTEGER, sortie INTEGER, cout_usd REAL NOT NULL, resultat TEXT
);
CREATE INDEX elements_etat ON elements(etat);
CREATE INDEX elements_empreinte ON elements(empreinte);
CREATE INDEX elements_destination ON elements(destination);
CREATE INDEX actions_element ON actions(element);
INSERT INTO "meta" (cle, valeur) VALUES ('installe_le', '1791288015.3098645');
INSERT INTO "meta" (cle, valeur) VALUES ('verifie_le', '2026-10-06');
INSERT INTO "meta" (cle, valeur) VALUES ('battement', '1791297697.906097');
INSERT INTO "meta" (cle, valeur) VALUES ('a_trier', '[valeur]');
