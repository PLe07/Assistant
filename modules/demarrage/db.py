"""La base SQLite du Nettoyeur (donnees/demarrage/demarrage.db, lisible par toi seul).

Une base corrompue est mise de côté puis reconstruite ; un disque plein abandonne l'écriture en cours sans
arrêter l'outil (DisquePlein).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Callable, Iterable, Iterator
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

    # --- relevés de l'échantillonneur ------------------------------------------------------------------------

    def enregistrer_releve(
        self, ts: float, mode: str, cpu_total_pct: float | None, par_fiche: dict[str, dict[str, Any]]
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO releves (ts, mode, cpu_total_pct) VALUES (?, ?, ?)", (ts, mode, cpu_total_pct)
            )
            db.executemany(
                "INSERT INTO mesures (ts, mode, fiche_id, cpu_s, rss_ko, puissance, veille)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (ts, mode, fid, m["cpu_s"], m["rss_ko"], m["puissance"], int(m["veille"]))
                    for fid, m in par_fiche.items()
                ],
            )

    def releves(
        self, debut: float = 0.0, fin: float = float("inf"), modes: Iterable[str] | None = None
    ) -> list[tuple[float, float | None]]:
        lignes = self.db.execute(
            "SELECT ts, cpu_total_pct, mode FROM releves WHERE ts >= ? AND ts <= ? ORDER BY ts", (debut, min(fin, 1e15))
        ).fetchall()
        choisis = set(modes) if modes is not None else None
        return [(t, c) for t, c, m in lignes if choisis is None or m in choisis]

    def mesures(
        self, debut: float = 0.0, fin: float = float("inf"), modes: Iterable[str] | None = None
    ) -> list[tuple[float, str, str, float, int, float | None, int]]:
        """(ts, mode, fiche_id, cpu_s, rss_ko, puissance, veille), dans l'ordre du temps."""
        lignes = self.db.execute(
            "SELECT ts, mode, fiche_id, cpu_s, rss_ko, puissance, veille FROM mesures WHERE ts >= ? AND ts <= ?"
            " ORDER BY ts",
            (debut, min(fin, 1e15)),
        ).fetchall()
        choisis = set(modes) if modes is not None else None
        return [tuple(x) for x in lignes if choisis is None or x[1] in choisis]

    def agregats(self) -> list[tuple[str, str, str, float, int, float | None, int, int]]:
        return [tuple(x) for x in self.db.execute("SELECT * FROM agregats ORDER BY jour")]

    # --- sessions ----------------------------------------------------------------------------------------------

    def enregistrer_session(
        self, boot: float, connexion: float | None, calme: float | None, details: dict[str, Any]
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO sessions (boot, connexion, calme, details) VALUES (?, ?, ?, ?)",
                (boot, connexion, calme, json.dumps(details)),
            )

    def session(self, boot: float) -> dict[str, Any] | None:
        ligne = self.db.execute(
            "SELECT boot, connexion, calme, details FROM sessions WHERE boot = ?", (boot,)
        ).fetchone()
        return self._session(ligne) if ligne else None

    def sessions(self, n: int = 60) -> list[dict[str, Any]]:
        """Les n dernières sessions, de la plus ancienne à la plus récente."""
        lignes = self.db.execute(
            "SELECT boot, connexion, calme, details FROM sessions ORDER BY boot DESC LIMIT ?", (n,)
        ).fetchall()
        return [self._session(x) for x in reversed(lignes)]

    @staticmethod
    def _session(ligne: tuple[Any, ...]) -> dict[str, Any]:
        try:
            details = json.loads(ligne[3]) if ligne[3] else {}
        except ValueError:
            details = {}
        return {"boot": ligne[0], "connexion": ligne[1], "calme": ligne[2], **details}

    # --- rétention ---------------------------------------------------------------------------------------------

    def purger(self, retention_jours: int, maintenant: float, jour_de: Callable[[float], str]) -> int:
        """Les relevés de plus de retention_jours deviennent des agrégats par jour, élément et mode. Renvoie combien
        de mesures ont été résumées."""
        limite = maintenant - retention_jours * 86400
        vieilles = self.db.execute(
            "SELECT ts, mode, fiche_id, cpu_s, rss_ko, puissance, veille FROM mesures WHERE ts < ?", (limite,)
        ).fetchall()
        if not vieilles:
            self.db.execute("DELETE FROM releves WHERE ts < ?", (limite,))
            self.db.commit()
            return 0
        groupes: dict[tuple[str, str, str], list[tuple[Any, ...]]] = {}
        for ligne in vieilles:
            groupes.setdefault((jour_de(ligne[0]), ligne[2], ligne[1]), []).append(ligne)
        with self.transaction() as db:
            for (jour, fid, mode), lignes in groupes.items():
                ancien = db.execute(
                    "SELECT cpu_s, rss_moy_ko, puissance, veille_n, n FROM agregats"
                    " WHERE jour = ? AND fiche_id = ? AND mode = ?",
                    (jour, fid, mode),
                ).fetchone()
                cpu = sum(x[3] for x in lignes) + (ancien[0] if ancien else 0.0)
                n_ancien = ancien[4] if ancien else 0
                n = len(lignes) + n_ancien
                rss = (sum(x[4] for x in lignes) + (ancien[1] * n_ancien if ancien else 0)) // n
                puissances = [x[5] for x in lignes if x[5] is not None]
                puissance = sum(puissances) / len(puissances) if puissances else (ancien[2] if ancien else None)
                veille_n = sum(x[6] for x in lignes) + (ancien[3] if ancien else 0)
                db.execute(
                    "INSERT OR REPLACE INTO agregats VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (jour, fid, mode, cpu, rss, puissance, veille_n, n),
                )
            db.execute("DELETE FROM mesures WHERE ts < ?", (limite,))
            db.execute("DELETE FROM releves WHERE ts < ?", (limite,))
        return len(vieilles)

    # --- zsh -------------------------------------------------------------------------------------------------------

    def enregistrer_zsh(self, ts: float, mediane_ms: float | None, details: dict[str, Any]) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO zsh (ts, mediane_ms, details) VALUES (?, ?, ?)",
                (ts, mediane_ms, json.dumps(details)),
            )

    def zsh(self, n: int = 30) -> list[dict[str, Any]]:
        lignes = self.db.execute("SELECT ts, mediane_ms, details FROM zsh ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
        resultats = []
        for ts, mediane, details in reversed(lignes):
            try:
                d = json.loads(details) if details else {}
            except ValueError:
                d = {}
            resultats.append({"ts": ts, "mediane_ms": mediane, **d})
        return resultats
