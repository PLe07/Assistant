"""La base SQLite de Quotidien (`~/Library/Application Support/Quotidien/quotidien.db`, `chmod 600`).

Une base corrompue ne bloque rien : elle est mise de côté (`quotidien.db.corrompue-<date>`) et une base neuve est
créée ; le journal et `quotidien doctor` le disent.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS taches (
  nom TEXT NOT NULL, echeance TEXT NOT NULL, faite_le REAL NOT NULL, resultat TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (nom, echeance)
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY, date REAL NOT NULL, genre TEXT NOT NULL, titre TEXT NOT NULL, texte TEXT NOT NULL,
  envoyee INTEGER NOT NULL, motif TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS depenses_ia (
  id INTEGER PRIMARY KEY, date REAL NOT NULL, mois TEXT NOT NULL, cout_usd REAL NOT NULL,
  jetons_entree INTEGER NOT NULL, jetons_sortie INTEGER NOT NULL, usage TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meteo_cache (cle TEXT PRIMARY KEY, recu_le REAL NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS textes_meteo (jour TEXT PRIMARY KEY, situation TEXT NOT NULL, texte TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS menus (semaine TEXT PRIMARY KEY, cree_le REAL NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cuisines (jour TEXT PRIMARY KEY, recette TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY, date REAL NOT NULL, jour TEXT NOT NULL, recette TEXT NOT NULL, note INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS envies (id INTEGER PRIMARY KEY, date REAL NOT NULL, texte TEXT NOT NULL,
  etiquettes TEXT NOT NULL, semaine TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS frigo (ingredient TEXT PRIMARY KEY, quantite REAL, unite TEXT, ajoute_le REAL NOT NULL,
  incertain INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rappels_apple (
  id INTEGER PRIMARY KEY, liste TEXT NOT NULL, identifiant TEXT NOT NULL, cle TEXT NOT NULL UNIQUE,
  cree_le REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS listes_apple (role TEXT PRIMARY KEY, nom TEXT NOT NULL, creee_par_nous INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS anniversaires_emis (cle TEXT PRIMARY KEY, emis_le REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages_prets (cle TEXT PRIMARY KEY, cree_le REAL NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS demandes (id TEXT PRIMARY KEY, recue_le REAL NOT NULL, genre TEXT NOT NULL,
  statut TEXT NOT NULL);
"""


class Base:
    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self.corrompue_mise_de_cote: Path | None = None
        chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(chemin.parent, 0o700)
        except OSError:
            pass
        self.cx = self._ouvrir()

    def _ouvrir(self) -> sqlite3.Connection:
        nouvelle = not self.chemin.exists()
        try:
            cx = self._connexion()
            ok = cx.execute("PRAGMA quick_check").fetchone()
            if ok is None or ok[0] != "ok":
                raise sqlite3.DatabaseError("quick_check")
            cx.executescript(SCHEMA)
        except sqlite3.DatabaseError:
            try:
                cx.close()
            except (UnboundLocalError, sqlite3.Error):
                pass
            cote = self.chemin.with_name(f"{self.chemin.name}.corrompue-{time.strftime('%Y%m%d-%H%M%S')}")
            self.chemin.replace(cote)
            for suffixe in ("-wal", "-shm", "-journal"):
                annexe = self.chemin.with_name(self.chemin.name + suffixe)
                if annexe.exists():
                    annexe.unlink()
            self.corrompue_mise_de_cote = cote
            nouvelle = True
            cx = self._connexion()
            cx.executescript(SCHEMA)
        if nouvelle or (self.chemin.stat().st_mode & 0o777) != 0o600:
            os.chmod(self.chemin, 0o600)
        return cx

    def _connexion(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.chemin, timeout=15, isolation_level=None)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA journal_mode=WAL")
        cx.execute("PRAGMA busy_timeout=15000")
        return cx

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.cx.execute("BEGIN IMMEDIATE")
        try:
            yield self.cx
        except BaseException:
            self.cx.execute("ROLLBACK")
            raise
        else:
            self.cx.execute("COMMIT")

    def lignes(self, requete: str, valeurs: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self.cx.execute(requete, valeurs).fetchall())

    def lire_meta(self, cle: str, defaut: str | None = None) -> str | None:
        ligne = self.cx.execute("SELECT valeur FROM meta WHERE cle = ?", (cle,)).fetchone()
        return str(ligne[0]) if ligne else defaut

    def ecrire_meta(self, cle: str, valeur: str) -> None:
        with self.transaction() as cx:
            cx.execute("INSERT INTO meta(cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = ?",
                       (cle, valeur, valeur))  # fmt: skip

    def lire_json(self, cle: str) -> Any:
        brut = self.lire_meta(cle)
        if brut is None:
            return None
        try:
            return json.loads(brut)
        except json.JSONDecodeError:
            return None

    def ecrire_json(self, cle: str, valeur: Any) -> None:
        self.ecrire_meta(cle, json.dumps(valeur, ensure_ascii=False, sort_keys=True))

    def fermer(self) -> None:
        self.cx.close()
