"""La base locale (SQLite, lisible par toi seul : chmod 600).

Une base abîmée n'arrête rien : elle est mise de côté (« bouclier.db.abimee-<date> ») et une base neuve la remplace.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
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
"""


class Base:
    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.mise_de_cote: Path | None = None
        self._ouvrir()

    def _ouvrir(self) -> None:
        neuf = not self.chemin.exists()
        try:
            self.cx = sqlite3.connect(self.chemin, timeout=10)
            self.cx.row_factory = sqlite3.Row
            verdict = self.cx.execute("PRAGMA quick_check").fetchone()[0]
            if verdict != "ok":
                raise sqlite3.DatabaseError(verdict)
            self.cx.executescript(SCHEMA)
        except sqlite3.DatabaseError:
            self._remplacer_base_abimee()
            neuf = True
        if neuf or (os.stat(self.chemin).st_mode & 0o777) != 0o600:
            os.chmod(self.chemin, 0o600)

    def _remplacer_base_abimee(self) -> None:
        try:
            self.cx.close()
        except Exception:  # noqa: BLE001 - la connexion peut ne pas exister
            pass
        cible = self.chemin.with_name(f"{self.chemin.name}.abimee-{time.strftime('%Y%m%d-%H%M%S')}")
        os.replace(self.chemin, cible)
        for suffixe in ("-journal", "-wal", "-shm"):
            annexe = self.chemin.with_name(self.chemin.name + suffixe)
            if annexe.exists():
                os.replace(annexe, cible.with_name(cible.name + suffixe))
        self.mise_de_cote = cible
        self.cx = sqlite3.connect(self.chemin, timeout=10)
        self.cx.row_factory = sqlite3.Row
        self.cx.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.cx:
            yield self.cx

    def lire_meta(self, cle: str, defaut: str | None = None) -> str | None:
        ligne = self.cx.execute("SELECT valeur FROM meta WHERE cle = ?", (cle,)).fetchone()
        return ligne[0] if ligne else defaut

    def ecrire_meta(self, cle: str, valeur: str) -> None:
        with self.transaction() as cx:
            cx.execute("INSERT OR REPLACE INTO meta(cle, valeur) VALUES (?, ?)", (cle, valeur))

    def lignes(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self.cx.execute(sql, params).fetchall())

    def fermer(self) -> None:
        self.cx.close()


def ouvrir(chemin: Path) -> Base:
    return Base(chemin)
