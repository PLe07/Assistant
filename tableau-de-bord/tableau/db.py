"""La base SQLite du tableau de bord (`~/Library/Application Support/TableauDeBord/tableau.db`, `chmod 600`).

C'est **notre** base : elle seule est ouverte directement. Les bases des autres modules ne le sont jamais (voir
`sondes/sqlite_copie.py`). Rétention : les mesures brutes 48 h, les agrégats horaires 90 jours, les agrégats
journaliers ensuite (`entretenir`). Une base illisible est mise de côté et recréée ; un disque plein ne fait rien
planter (l'écriture du tour est abandonnée, `tableau doctor` le dit).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS echantillons (
  module TEXT NOT NULL, ts REAL NOT NULL, pastille TEXT NOT NULL, cpu REAL, rss_mo REAL,
  erreurs INTEGER, avertissements INTEGER, file_n INTEGER, PRIMARY KEY (module, ts)
);
CREATE TABLE IF NOT EXISTS agregats (
  periode TEXT NOT NULL, debut REAL NOT NULL, module TEXT NOT NULL, n INTEGER NOT NULL,
  cpu_moy REAL, cpu_max REAL, rss_moy REAL, rss_max REAL, erreurs INTEGER, avertissements INTEGER,
  vert INTEGER NOT NULL DEFAULT 0, jaune INTEGER NOT NULL DEFAULT 0, rouge INTEGER NOT NULL DEFAULT 0,
  gris INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (periode, module, debut)
);
CREATE TABLE IF NOT EXISTS evenements (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, module TEXT NOT NULL, genre TEXT NOT NULL, gravite TEXT NOT NULL,
  message TEXT NOT NULL, details TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS evenements_ts ON evenements(ts);
CREATE TABLE IF NOT EXISTS problemes (
  cle TEXT PRIMARY KEY, module TEXT NOT NULL, genre TEXT NOT NULL, gravite TEXT NOT NULL, message TEXT NOT NULL,
  resolution TEXT NOT NULL DEFAULT '', nuit_permise INTEGER NOT NULL DEFAULT 0,
  ouvert_le REAL NOT NULL, vu_le REAL NOT NULL, observations INTEGER NOT NULL DEFAULT 1,
  absent_depuis REAL, notifie_le REAL, rappel_le REAL, resolu_le REAL, resolution_envoyee INTEGER NOT NULL DEFAULT 0,
  confirme_le REAL, phrase TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, titre TEXT NOT NULL, texte TEXT NOT NULL, cles TEXT NOT NULL,
  envoyee INTEGER NOT NULL, motif TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS curseurs (
  cle TEXT PRIMARY KEY, inode INTEGER, position INTEGER NOT NULL, taille INTEGER NOT NULL, tete TEXT, maj REAL
);
CREATE TABLE IF NOT EXISTS compteurs_logs (
  module TEXT NOT NULL, heure REAL NOT NULL, erreurs INTEGER NOT NULL DEFAULT 0,
  avertissements INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (module, heure)
);
CREATE TABLE IF NOT EXISTS dernieres_erreurs (
  module TEXT NOT NULL, ts REAL NOT NULL, message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS dernieres_erreurs_module ON dernieres_erreurs(module, ts);
CREATE TABLE IF NOT EXISTS relances (module TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY (module, ts));
CREATE TABLE IF NOT EXISTS lancements (module TEXT PRIMARY KEY, label TEXT, valeur INTEGER, maj REAL);
CREATE TABLE IF NOT EXISTS attentes (
  module TEXT NOT NULL, attente TEXT NOT NULL, echeance REAL NOT NULL, statut TEXT NOT NULL, constate_le REAL,
  detail TEXT NOT NULL DEFAULT '', PRIMARY KEY (module, attente, echeance)
);
CREATE TABLE IF NOT EXISTS fichiers_vus (chemin TEXT PRIMARY KEY, premier_vu REAL NOT NULL, dernier_vu REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tailles (
  module TEXT NOT NULL, ts REAL NOT NULL, donnees INTEGER, logs INTEGER, PRIMARY KEY (module, ts)
);
CREATE TABLE IF NOT EXISTS veilles (debut REAL NOT NULL, fin REAL NOT NULL, PRIMARY KEY (debut));
CREATE TABLE IF NOT EXISTS credits (
  module TEXT NOT NULL, mois TEXT NOT NULL, cout_usd REAL NOT NULL, plafond_usd REAL, maj REAL NOT NULL,
  PRIMARY KEY (module, mois)
);
CREATE TABLE IF NOT EXISTS integrite_reference (
  module TEXT NOT NULL, chemin TEXT NOT NULL, sha256 TEXT NOT NULL, taille INTEGER, mtime_ns INTEGER, inode INTEGER,
  PRIMARY KEY (module, chemin)
);
CREATE TABLE IF NOT EXISTS integrite_etat (
  module TEXT PRIMARY KEY, reference_le REAL, controle_le REAL, ecarts TEXT NOT NULL DEFAULT '[]', head TEXT,
  head_reference TEXT, signale_le REAL
);
CREATE TABLE IF NOT EXISTS etat_modules (module TEXT PRIMARY KEY, json TEXT NOT NULL, maj REAL NOT NULL);
"""

# Colonnes venues après la première version : ajoutées à une base existante, sans rien perdre.
COLONNES_AJOUTEES = {"problemes": [("confirme_le", "REAL"), ("phrase", "TEXT NOT NULL DEFAULT ''")]}


class DisquePlein(Exception):
    """Plus de place : l'écriture du tour est abandonnée, le tableau de bord continue."""


class Base:
    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self._verrou = threading.RLock()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.db = self._ouvrir()

    def _ouvrir(self) -> sqlite3.Connection:
        nouvelle = not self.chemin.exists()
        try:
            db = self._connecter(nouvelle)
            db.execute("SELECT COUNT(*) FROM meta").fetchone()
            return db
        except sqlite3.DatabaseError:
            # Base abîmée (coupure de courant, disque) : mise de côté, une neuve repart. L'historique est perdu,
            # pas la surveillance.
            for suffixe in ("", "-wal", "-shm"):
                ancien = Path(f"{self.chemin}{suffixe}")
                if ancien.exists():
                    ancien.replace(Path(f"{self.chemin}{suffixe}.abimee-{int(time.time())}"))
            return self._connecter(True)

    def _connecter(self, nouvelle: bool) -> sqlite3.Connection:
        if nouvelle:
            descripteur = os.open(self.chemin, os.O_WRONLY | os.O_CREAT, 0o600)
            os.close(descripteur)
        db = sqlite3.connect(self.chemin, timeout=10, check_same_thread=False, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA busy_timeout=5000")
        db.executescript(SCHEMA)
        for table, colonnes in COLONNES_AJOUTEES.items():
            presentes = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            for nom, genre in colonnes:
                if nom not in presentes:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {nom} {genre}")
        os.chmod(self.chemin, 0o600)
        return db

    def fermer(self) -> None:
        with self._verrou:
            self.db.close()

    # --- accès bas niveau ---------------------------------------------------------------------------------------

    def lignes(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._verrou:
            return list(self.db.execute(sql, params).fetchall())

    def ligne(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._verrou:
            r: sqlite3.Row | None = self.db.execute(sql, params).fetchone()
            return r

    def valeur(self, sql: str, params: tuple[Any, ...] = (), defaut: Any = None) -> Any:
        r = self.ligne(sql, params)
        return defaut if r is None or r[0] is None else r[0]

    def executer(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._verrou:
            try:
                return self.db.execute(sql, params).rowcount
            except sqlite3.OperationalError as e:
                if "full" in str(e).lower():
                    raise DisquePlein(str(e)) from e
                raise

    def plusieurs(self, sql: str, lignes: list[tuple[Any, ...]]) -> None:
        with self._verrou:
            try:
                self.db.executemany(sql, lignes)
            except sqlite3.OperationalError as e:
                if "full" in str(e).lower():
                    raise DisquePlein(str(e)) from e
                raise

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._verrou:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            else:
                try:
                    self.db.execute("COMMIT")
                except sqlite3.OperationalError as e:
                    self.db.execute("ROLLBACK")
                    if "full" in str(e).lower():
                        raise DisquePlein(str(e)) from e
                    raise

    # --- méta ------------------------------------------------------------------------------------------------------

    def lire_meta(self, cle: str, defaut: str | None = None) -> str | None:
        v = self.valeur("SELECT valeur FROM meta WHERE cle = ?", (cle,))
        return defaut if v is None else str(v)

    def ecrire_meta(self, cle: str, valeur: str) -> None:
        self.executer(
            "INSERT INTO meta (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
            (cle, valeur),
        )

    def effacer_meta(self, cle: str) -> None:
        self.executer("DELETE FROM meta WHERE cle = ?", (cle,))

    # --- journal des événements ------------------------------------------------------------------------------------

    def noter_evenement(
        self, ts: float, module: str, genre: str, gravite: str, message: str, details: str = ""
    ) -> None:
        self.executer(
            "INSERT INTO evenements (ts, module, genre, gravite, message, details) VALUES (?, ?, ?, ?, ?, ?)",
            (ts, module, genre, gravite, message, details),
        )

    def evenements(self, depuis: float, module: str | None = None, limite: int = 200) -> list[sqlite3.Row]:
        if module:
            return self.lignes(
                "SELECT * FROM evenements WHERE ts >= ? AND module = ? ORDER BY ts DESC, id DESC LIMIT ?",
                (depuis, module, limite),
            )
        return self.lignes("SELECT * FROM evenements WHERE ts >= ? ORDER BY ts DESC, id DESC LIMIT ?", (depuis, limite))

    # --- état publié de chaque module (relu par la CLI et après un redémarrage) -------------------------------------

    def ecrire_etat_module(self, module: str, etat: dict[str, Any], ts: float) -> None:
        self.executer(
            "INSERT INTO etat_modules (module, json, maj) VALUES (?, ?, ?) "
            "ON CONFLICT(module) DO UPDATE SET json = excluded.json, maj = excluded.maj",
            (module, json.dumps(etat, ensure_ascii=False), ts),
        )

    def etats_modules(self) -> dict[str, dict[str, Any]]:
        resultat: dict[str, dict[str, Any]] = {}
        for r in self.lignes("SELECT module, json FROM etat_modules"):
            try:
                resultat[r["module"]] = json.loads(r["json"])
            except ValueError:
                continue
        return resultat

    # --- entretien : agrégats et rétention -----------------------------------------------------------------------

    def entretenir(self, maintenant: float) -> None:
        """Agrège les mesures brutes de plus de 48 h en heures, les heures de plus de 90 jours en jours."""
        limite_brut = maintenant - 48 * 3600
        # Des jours entiers seulement : toutes les heures d'un jour passent ensemble dans son agrégat journalier.
        limite_heures = (int(maintenant - 90 * 86400) // 86400) * 86400
        with self.transaction():
            self._agreger("h", 3600, "echantillons", limite_brut)
            self.db.execute("DELETE FROM echantillons WHERE ts < ?", (limite_brut,))
            self._agreger_jours(limite_heures)
            self.db.execute("DELETE FROM agregats WHERE periode = 'h' AND debut < ?", (limite_heures,))
            self.db.execute("DELETE FROM evenements WHERE ts < ?", (limite_heures,))
            self.db.execute("DELETE FROM notifications WHERE ts < ?", (limite_heures,))
            self.db.execute("DELETE FROM compteurs_logs WHERE heure < ?", (maintenant - 35 * 86400,))
            self.db.execute("DELETE FROM dernieres_erreurs WHERE ts < ?", (maintenant - 7 * 86400,))
            self.db.execute("DELETE FROM relances WHERE ts < ?", (maintenant - 35 * 86400,))
            self.db.execute("DELETE FROM tailles WHERE ts < ?", (limite_heures,))
            self.db.execute("DELETE FROM veilles WHERE fin < ?", (limite_heures,))
            self.db.execute("DELETE FROM attentes WHERE echeance < ?", (limite_heures,))
            self.db.execute("DELETE FROM fichiers_vus WHERE dernier_vu < ?", (maintenant - 7 * 86400,))
            self.db.execute("DELETE FROM problemes WHERE resolu_le IS NOT NULL AND resolu_le < ?", (limite_heures,))

    def _agreger(self, periode: str, pas: int, table: str, avant: float) -> None:
        self.db.execute(
            f"""INSERT INTO agregats (periode, debut, module, n, cpu_moy, cpu_max, rss_moy, rss_max, erreurs,
                   avertissements, vert, jaune, rouge, gris)
               SELECT ?, CAST(ts / {pas} AS INTEGER) * {pas} AS d, module, COUNT(*), AVG(cpu), MAX(cpu), AVG(rss_mo),
                   MAX(rss_mo), MAX(erreurs), MAX(avertissements),
                   SUM(pastille = 'vert'), SUM(pastille = 'jaune'), SUM(pastille = 'rouge'), SUM(pastille = 'gris')
               FROM {table} WHERE ts < ? GROUP BY module, d
               ON CONFLICT(periode, module, debut) DO UPDATE SET
                   cpu_moy = (agregats.cpu_moy * agregats.n + excluded.cpu_moy * excluded.n)
                       / (agregats.n + excluded.n),
                   cpu_max = MAX(agregats.cpu_max, excluded.cpu_max),
                   rss_moy = (agregats.rss_moy * agregats.n + excluded.rss_moy * excluded.n)
                       / (agregats.n + excluded.n),
                   rss_max = MAX(agregats.rss_max, excluded.rss_max),
                   erreurs = MAX(agregats.erreurs, excluded.erreurs),
                   avertissements = MAX(agregats.avertissements, excluded.avertissements),
                   vert = agregats.vert + excluded.vert, jaune = agregats.jaune + excluded.jaune,
                   rouge = agregats.rouge + excluded.rouge, gris = agregats.gris + excluded.gris,
                   n = agregats.n + excluded.n""",  # noqa: S608 - noms de tables et pas fixés dans ce fichier
            (periode, avant),
        )

    def _agreger_jours(self, avant: float) -> None:
        self.db.execute(
            """INSERT INTO agregats (periode, debut, module, n, cpu_moy, cpu_max, rss_moy, rss_max, erreurs,
                   avertissements, vert, jaune, rouge, gris)
               SELECT 'j', CAST(debut / 86400 AS INTEGER) * 86400 AS d, module, SUM(n), SUM(cpu_moy * n) / SUM(n),
                   MAX(cpu_max), SUM(rss_moy * n) / SUM(n), MAX(rss_max), SUM(erreurs), SUM(avertissements),
                   SUM(vert), SUM(jaune), SUM(rouge), SUM(gris)
               FROM agregats WHERE periode = 'h' AND debut < ? GROUP BY module, d
               ON CONFLICT(periode, module, debut) DO NOTHING""",
            (avant,),
        )
