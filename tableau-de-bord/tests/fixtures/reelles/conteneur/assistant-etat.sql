-- Échantillon anonymisé de etat.db (schéma exact, 12 lignes au plus par table).
CREATE TABLE cles (cle TEXT PRIMARY KEY, valeur TEXT, maj REAL);
CREATE TABLE modules (
    nom TEXT PRIMARY KEY, statut TEXT, detail TEXT, pid INTEGER, relances INTEGER, maj REAL
);
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY, quand REAL, module TEXT, titre TEXT, message TEXT,
    empreinte TEXT, envoyee INTEGER, raison TEXT
);
CREATE TABLE aides (
    id INTEGER PRIMARY KEY, quand REAL, module TEXT, titre TEXT, statut TEXT, texte TEXT,
    vue INTEGER DEFAULT 0, maj REAL
);
CREATE TABLE appels_claude (
    id INTEGER PRIMARY KEY, quand REAL, module TEXT, modele TEXT, ok INTEGER,
    tokens_entree INTEGER, tokens_sortie INTEGER, erreur TEXT
);
INSERT INTO "notifications" (id, quand, module, titre, message, empreinte, envoyee, raison) VALUES (1, 1791190259.835957, 'corvees', '[titre]', '[message]', '[empreinte]', 0, '[raison]');
INSERT INTO "notifications" (id, quand, module, titre, message, empreinte, envoyee, raison) VALUES (2, 1791219642.5931563, 'corvees', '[titre]', '[message]', '[empreinte]', 0, '[raison]');
INSERT INTO "notifications" (id, quand, module, titre, message, empreinte, envoyee, raison) VALUES (3, 1791288824.941748, 'corvees', '[titre]', '[message]', '[empreinte]', 0, '[raison]');
