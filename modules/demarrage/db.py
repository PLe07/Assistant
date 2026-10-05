"""La base SQLite du Nettoyeur (donnees/demarrage/demarrage.db, lisible par toi seul).

Une base corrompue est mise de côté puis reconstruite ; un disque plein abandonne l'écriture en cours sans
arrêter l'outil (DisquePlein).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from modules.demarrage.modele import Inventaire

SCANS_GARDES = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS etat (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY, ts REAL NOT NULL, inventaire TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS apparitions (
    id TEXT PRIMARY KEY, label TEXT NOT NULL, source TEXT NOT NULL, premiere_vue REAL NOT NULL,
    derniere_vue REAL NOT NULL, notifiee REAL
);
CREATE TABLE IF NOT EXISTS signatures (chemin TEXT PRIMARY KEY, donnees TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS releves (ts REAL PRIMARY KEY, mode TEXT NOT NULL, cpu_total_pct REAL);
CREATE TABLE IF NOT EXISTS echantillons (
    ts REAL NOT NULL, pid INTEGER NOT NULL, ppid INTEGER, uid INTEGER, cpu_s REAL, rss_ko INTEGER, comm TEXT
);
CREATE INDEX IF NOT EXISTS echantillons_ts ON echantillons (ts);
CREATE TABLE IF NOT EXISTS pids_launchd (ts REAL NOT NULL, pid INTEGER NOT NULL, label TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS pids_launchd_ts ON pids_launchd (ts);
CREATE TABLE IF NOT EXISTS energie (ts REAL NOT NULL, pid INTEGER NOT NULL, commande TEXT, cpu REAL, puissance REAL);
CREATE INDEX IF NOT EXISTS energie_ts ON energie (ts);
CREATE TABLE IF NOT EXISTS veille (ts REAL NOT NULL, pid INTEGER NOT NULL, type TEXT, nom TEXT, au_nom_de INTEGER);
CREATE INDEX IF NOT EXISTS veille_ts ON veille (ts);
CREATE TABLE IF NOT EXISTS sessions (
    boot REAL PRIMARY KEY, connexion REAL, source_connexion TEXT, calme REAL, details TEXT
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, fiche_id TEXT NOT NULL, label TEXT NOT NULL, genre TEXT NOT NULL,
    avant TEXT, apres TEXT, commandes TEXT, details TEXT, annulee REAL
);
CREATE TABLE IF NOT EXISTS agregats (
    jour TEXT NOT NULL, comm TEXT NOT NULL, cpu_s REAL, rss_med_ko INTEGER, puissance REAL, veille_n INTEGER,
    n INTEGER, PRIMARY KEY (jour, comm)
);
CREATE TABLE IF NOT EXISTS zsh (ts REAL PRIMARY KEY, mediane_ms REAL, details TEXT);
CREATE TABLE IF NOT EXISTS notifications (ts REAL NOT NULL, genre TEXT NOT NULL, titre TEXT, texte TEXT);
"""


class DisquePlein(Exception):
    """Plus de place pour écrire : l'écriture en cours est abandonnée, l'outil continue."""


def _ouvrir(chemin: Path) -> sqlite3.Connection:
    db = sqlite3.connect(chemin, timeout=15)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


def _creer_prive(chemin: Path) -> None:
    os.close(os.open(chemin, os.O_WRONLY | os.O_CREAT, 0o600))


class Base:
    def __init__(self, chemin: Path, journal: Callable[[str], None] | None = None):
        self.chemin = Path(chemin)
        self.journal = journal  # où dire qu'une base a été reconstruite
        self.chemin.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = self._connecter()

    def _connecter(self) -> sqlite3.Connection:
        if not self.chemin.exists():  # créée lisible par toi seul : SQLite donne les mêmes droits à -wal et -shm
            _creer_prive(self.chemin)
        db: sqlite3.Connection | None = None
        try:
            db = _ouvrir(self.chemin)
            resultat = db.execute("PRAGMA quick_check").fetchone()
            if not resultat or resultat[0] != "ok":
                raise sqlite3.DatabaseError(f"contrôle d'intégrité : {resultat}")
            db.executescript(SCHEMA)
        except sqlite3.DatabaseError as e:
            if db is not None:
                db.close()
            sauvegarde = self.chemin.with_name(f"{self.chemin.name}.corrompue-{int(time.time())}")
            for suffixe in ("", "-wal", "-shm"):
                morceau = Path(f"{self.chemin}{suffixe}")
                if morceau.exists():
                    morceau.rename(Path(f"{sauvegarde}{suffixe}"))
            if self.journal:
                self.journal(f"Base corrompue ({e}) : mise de côté ({sauvegarde.name}) et reconstruite")
            _creer_prive(self.chemin)
            db = _ouvrir(self.chemin)
            db.executescript(SCHEMA)
        for fichier in (self.chemin, Path(f"{self.chemin}-wal"), Path(f"{self.chemin}-shm")):
            if fichier.exists() and fichier.stat().st_mode & 0o077:
                os.chmod(fichier, 0o600)
        return db

    def fermer(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            with self.db:
                yield self.db
        except sqlite3.OperationalError as e:
            if "full" in str(e).lower() or "disk i/o" in str(e).lower():
                raise DisquePlein(str(e)) from e
            raise

    # --- état (clé → valeur JSON) ------------------------------------------------------------------------------

    def lire(self, cle: str, defaut: Any = None) -> Any:
        ligne = self.db.execute("SELECT valeur FROM etat WHERE cle = ?", (cle,)).fetchone()
        return json.loads(ligne[0]) if ligne else defaut

    def ecrire(self, cle: str, valeur: Any) -> None:
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO etat (cle, valeur) VALUES (?, ?)", (cle, json.dumps(valeur)))

    def effacer(self, cle: str) -> None:
        with self.transaction() as db:
            db.execute("DELETE FROM etat WHERE cle = ?", (cle,))

    # --- scans et apparitions ----------------------------------------------------------------------------------

    def enregistrer_scan(self, inventaire: Inventaire) -> list[str]:
        """Garde le scan (les 10 derniers) et renvoie les identifiants vus pour la première fois."""
        nouveaux: list[str] = []
        with self.transaction() as db:
            db.execute(
                "INSERT INTO scans (ts, inventaire) VALUES (?, ?)",
                (inventaire.ts, json.dumps(inventaire.vers_dict(), ensure_ascii=False)),
            )
            db.execute(
                "DELETE FROM scans WHERE id NOT IN (SELECT id FROM scans ORDER BY ts DESC, id DESC LIMIT ?)",
                (SCANS_GARDES,),
            )
            for f in inventaire.fiches:
                ancien = db.execute("SELECT 1 FROM apparitions WHERE id = ?", (f.id,)).fetchone()
                if ancien:
                    db.execute("UPDATE apparitions SET derniere_vue = ? WHERE id = ?", (inventaire.ts, f.id))
                else:
                    nouveaux.append(f.id)
                    db.execute(
                        "INSERT INTO apparitions (id, label, source, premiere_vue, derniere_vue)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (f.id, f.label, f.source, inventaire.ts, inventaire.ts),
                    )
        return nouveaux

    def scans(self, n: int = 2) -> list[Inventaire]:
        """Les n derniers scans, le plus récent d'abord (un scan illisible est ignoré)."""
        resultats: list[Inventaire] = []
        for (texte,) in self.db.execute("SELECT inventaire FROM scans ORDER BY ts DESC, id DESC"):
            try:
                resultats.append(Inventaire.depuis_dict(json.loads(texte)))
            except (ValueError, KeyError, TypeError):
                continue
            if len(resultats) >= n:
                break
        return resultats

    def dernier_scan(self) -> Inventaire | None:
        derniers = self.scans(1)
        return derniers[0] if derniers else None

    def premiere_vue(self, id_: str) -> float | None:
        ligne = self.db.execute("SELECT premiere_vue FROM apparitions WHERE id = ?", (id_,)).fetchone()
        return float(ligne[0]) if ligne else None

    def premieres_vues(self) -> dict[str, float]:
        return {i: float(t) for i, t in self.db.execute("SELECT id, premiere_vue FROM apparitions")}

    def marquer_notifiee(self, id_: str, quand: float) -> None:
        with self.transaction() as db:
            db.execute("UPDATE apparitions SET notifiee = ? WHERE id = ?", (quand, id_))

    # --- cache des signatures ----------------------------------------------------------------------------------

    def signatures(self) -> dict[str, dict[str, Any]]:
        entrees: dict[str, dict[str, Any]] = {}
        for chemin, texte in self.db.execute("SELECT chemin, donnees FROM signatures"):
            try:
                entrees[chemin] = json.loads(texte)
            except ValueError:
                continue
        return entrees

    def sauver_signatures(self, entrees: dict[str, dict[str, Any]]) -> None:
        with self.transaction() as db:
            db.executemany(
                "INSERT OR REPLACE INTO signatures (chemin, donnees) VALUES (?, ?)",
                [(c, json.dumps(e)) for c, e in entrees.items()],
            )
