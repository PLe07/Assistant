"""La base locale (SQLite, lisible par toi seul) : événements, agrégats, décisions, candidats, coûts, état.

Le seul chemin d'écriture des événements est Base.ajouter(), qui passe chaque événement par le Gardien
(exclusions + caviardage). Une base corrompue est mise de côté puis reconstruite ; un disque plein ne fait
rien tomber.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.corvees.normalize import jour_de
from modules.corvees.privacy import Gardien

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL, token TEXT NOT NULL,
    attrs TEXT NOT NULL DEFAULT '{}', jour TEXT NOT NULL, session_id INTEGER
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS agregats (
    jour TEXT NOT NULL, source TEXT NOT NULL, token TEXT NOT NULL, n INTEGER NOT NULL,
    PRIMARY KEY (jour, source, token)
);
CREATE TABLE IF NOT EXISTS decisions (
    signature TEXT PRIMARY KEY, id TEXT, statut TEXT NOT NULL, jusqua REAL, frequence_ref REAL, quand REAL,
    tokens TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS candidats (
    id TEXT PRIMARY KEY, signature TEXT UNIQUE NOT NULL, type TEXT, donnees TEXT, score REAL,
    premier_vu REAL, dernier_vu REAL, analyse REAL
);
CREATE TABLE IF NOT EXISTS couts (
    id INTEGER PRIMARY KEY, quand REAL, mois TEXT, modele TEXT, jetons_entree INTEGER, jetons_sortie INTEGER,
    cout_usd REAL, ok INTEGER
);
CREATE TABLE IF NOT EXISTS descriptions (signature TEXT PRIMARY KEY, source TEXT, donnees TEXT, quand REAL);
CREATE TABLE IF NOT EXISTS etat (cle TEXT PRIMARY KEY, valeur TEXT, maj REAL);
"""


@dataclass(slots=True)  # sans dictionnaire par objet : 30 jours d'événements tiennent en mémoire sans peine
class Evenement:
    ts: float
    source: str  # le capteur : apps, fenetres, fichiers, shell, navigateur, pressepapiers, inactivite
    kind: str  # app, fen, url, fmove, fren, fcreate, fconv, cmd, clip, inactif
    token: str  # forme normalisée : « app:Numbers », « fmove:Downloads→Documents/Factures [pdf, Facture_*] »
    attrs: dict[str, Any] = field(default_factory=dict)
    session_id: int | None = None


_VIDE: dict[str, Any] = {}  # les attributs vides des événements lus : partagés, donc jamais modifiés


class DisquePlein(Exception):
    """Plus de place pour écrire : les événements en attente sont abandonnés, le détecteur continue."""


def _ouvrir(chemin: Path) -> sqlite3.Connection:
    db = sqlite3.connect(chemin, timeout=15)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db


class Base:
    def __init__(self, chemin: Path, gardien: Gardien, journal=None):
        self.chemin = Path(chemin)
        self.gardien = gardien
        self.journal = journal  # fonction(message) : où dire qu'une base a été reconstruite
        self.chemin.parent.mkdir(mode=0o700, parents=True, exist_ok=True)  # créé : lisible par toi seul
        self.db = self._connecter()
        self.naissance = self.lire("naissance")
        if not self.naissance:  # une marque unique : une base effacée puis recréée (purge) n'est plus la même
            self.naissance = secrets.token_hex(8)
            self.ecrire("naissance", self.naissance)

    # --- ouverture, réparation -------------------------------------------------------------------------------

    def _connecter(self) -> sqlite3.Connection:
        nouveau = not self.chemin.exists()
        if nouveau:  # créée lisible par toi seul : SQLite donne alors les mêmes droits à son journal (-wal, -shm)
            os.close(os.open(self.chemin, os.O_WRONLY | os.O_CREAT, 0o600))
        try:
            db = _ouvrir(self.chemin)
            resultat = db.execute("PRAGMA quick_check").fetchone()
            if not resultat or resultat[0] != "ok":
                raise sqlite3.DatabaseError(f"contrôle d'intégrité : {resultat}")
            db.executescript(SCHEMA)
        except sqlite3.DatabaseError as e:
            try:
                db.close()
            except Exception:
                pass
            sauvegarde = self.chemin.with_name(f"{self.chemin.name}.corrompue-{int(time.time())}")
            for suffixe in ("", "-wal", "-shm"):
                morceau = Path(str(self.chemin) + suffixe)
                if morceau.exists():
                    morceau.rename(Path(str(sauvegarde) + suffixe))
            if self.journal:
                self.journal(f"Base corrompue ({e}) : mise de côté ({sauvegarde.name}) et reconstruite")
            os.close(os.open(self.chemin, os.O_WRONLY | os.O_CREAT, 0o600))
            db = _ouvrir(self.chemin)
            db.executescript(SCHEMA)
        for fichier in (self.chemin, Path(f"{self.chemin}-wal"), Path(f"{self.chemin}-shm")):
            if fichier.exists() and fichier.stat().st_mode & 0o077:
                os.chmod(fichier, 0o600)  # lisible par toi seul (une base d'avant ce réglage, ou recréée)
        return db

    def fermer(self) -> None:
        self.db.close()

    def toujours_la(self) -> bool:
        """Le fichier sur le disque est-il encore cette base-ci ? (une purge a pu l'effacer et la recréer)"""
        try:
            uri = self.chemin.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=5)) as autre:
                ligne = autre.execute("SELECT valeur FROM etat WHERE cle = 'naissance'").fetchone()
        except (sqlite3.Error, OSError):
            return False
        return ligne is not None and json.loads(ligne[0]) == self.naissance

    # --- événements --------------------------------------------------------------------------------------------

    def ajouter(self, evenements: Iterable[Evenement]) -> int:
        """Écrit les événements autorisés (exclusions, caviardage) en une transaction. Renvoie combien."""
        lignes = []
        for evt in evenements:
            propre = self.gardien.nettoyer(evt)
            if propre is None:
                continue
            lignes.append(
                (
                    propre.ts,
                    propre.source,
                    propre.kind,
                    propre.token,
                    json.dumps(propre.attrs, ensure_ascii=False, sort_keys=True),
                    jour_de(propre.ts),
                    propre.session_id,
                )
            )
        if not lignes:
            return 0
        try:
            with self.db:
                self.db.executemany(
                    "INSERT INTO events (ts, source, kind, token, attrs, jour, session_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    lignes,
                )
        except sqlite3.OperationalError as e:
            if "full" in str(e).lower() or "disk" in str(e).lower():
                raise DisquePlein(str(e)) from e
            raise
        return len(lignes)

    def evenements(
        self, depuis: float, jusqua: float | None = None, attrs_pour: tuple[str, ...] | None = None
    ) -> list[Evenement]:
        return list(self.iterer(depuis, jusqua, attrs_pour))

    def iterer(
        self, depuis: float, jusqua: float | None = None, attrs_pour: tuple[str, ...] | None = None
    ) -> Iterator[Evenement]:
        """Les événements dans l'ordre. attrs_pour : ne lire les attributs que de ces sortes d'événements (l'analyse
        n'en a besoin que pour les fichiers : la mémoire reste petite)."""
        requete = "SELECT ts, source, kind, token, attrs, session_id FROM events WHERE ts >= ?"
        valeurs: list[Any] = [depuis]
        if jusqua is not None:
            requete += " AND ts < ?"
            valeurs.append(jusqua)
        # Des centaines de milliers d'événements, quelques milliers de tokens différents : chaque texte n'est gardé
        # qu'une fois en mémoire, et les attributs vides (la plupart) partagent le même dictionnaire, en lecture seule.
        textes: dict[str, str] = {}
        sessions: dict[int, int] = {}
        for ts, source, kind, token, attrs, session in self.db.execute(requete + " ORDER BY ts, id", valeurs):
            yield Evenement(
                ts,
                textes.setdefault(source, source),
                textes.setdefault(kind, kind),
                textes.setdefault(token, token),
                _VIDE if attrs == "{}" or (attrs_pour is not None and kind not in attrs_pour) else json.loads(attrs),
                session if session is None else sessions.setdefault(session, session),
            )

    def compter(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def purger(self, retention_jours: int, maintenant: float | None = None) -> int:
        """Les événements plus vieux que la rétention deviennent des comptes par jour (agrégats), puis sont effacés."""
        limite = (maintenant or time.time()) - retention_jours * 86400
        with self.db:
            self.db.execute(
                "INSERT INTO agregats (jour, source, token, n) SELECT jour, source, token, COUNT(*) FROM events "
                "WHERE ts < ? GROUP BY jour, source, token "
                "ON CONFLICT(jour, source, token) DO UPDATE SET n = n + excluded.n",
                (limite,),
            )
            n = self.db.execute("DELETE FROM events WHERE ts < ?", (limite,)).rowcount
        return int(n)

    def taille(self) -> int:
        """Octets occupés sur le disque (base + journal WAL)."""
        return sum(
            Path(str(self.chemin) + s).stat().st_size for s in ("", "-wal") if Path(str(self.chemin) + s).exists()
        )

    # --- clés simples (curseurs, battement, pause…) -------------------------------------------------------------

    def lire(self, cle: str, defaut: Any = None) -> Any:
        ligne = self.db.execute("SELECT valeur FROM etat WHERE cle = ?", (cle,)).fetchone()
        return json.loads(ligne[0]) if ligne else defaut

    def ecrire(self, cle: str, valeur: Any) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO etat (cle, valeur, maj) VALUES (?, ?, ?) "
                "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, maj = excluded.maj",
                (cle, json.dumps(valeur, ensure_ascii=False), time.time()),
            )

    def effacer(self, cle: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM etat WHERE cle = ?", (cle,))

    # --- décisions (accepter, refuser, reporter) -----------------------------------------------------------------

    def decider(
        self,
        signature: str,
        id_: str,
        statut: str,
        jusqua: float | None,
        frequence_ref: float,
        tokens: list[str] | None = None,
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO decisions (signature, id, statut, jusqua, frequence_ref, quand, tokens) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(signature) DO UPDATE SET id = excluded.id, "
                "statut = excluded.statut, jusqua = excluded.jusqua, frequence_ref = excluded.frequence_ref, "
                "quand = excluded.quand, tokens = excluded.tokens",
                (
                    signature,
                    id_,
                    statut,
                    jusqua,
                    frequence_ref,
                    time.time(),
                    json.dumps(tokens or [], ensure_ascii=False),
                ),
            )

    def oublier_decision(self, signature: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM decisions WHERE signature = ?", (signature,))

    def decisions(self) -> dict[str, dict[str, Any]]:
        lignes = self.db.execute("SELECT signature, id, statut, jusqua, frequence_ref, quand, tokens FROM decisions")
        return {
            s: {"id": i, "statut": st, "jusqua": j, "frequence_ref": f, "quand": q, "tokens": json.loads(t)}
            for s, i, st, j, f, q, t in lignes
        }

    # --- candidats de la dernière analyse ---------------------------------------------------------------------

    def enregistrer_candidats(self, candidats: list[dict[str, Any]], analyse: float) -> None:
        with self.db:
            for c in candidats:
                ancien = self.db.execute(
                    "SELECT premier_vu FROM candidats WHERE signature = ?", (c["signature"],)
                ).fetchone()
                self.db.execute(
                    "INSERT INTO candidats (id, signature, type, donnees, score, premier_vu, dernier_vu, analyse) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(signature) DO UPDATE SET donnees = excluded.donnees, "
                    "score = excluded.score, dernier_vu = excluded.dernier_vu, analyse = excluded.analyse",
                    (
                        c["id"],
                        c["signature"],
                        c["type"],
                        json.dumps(c, ensure_ascii=False),
                        c["score"],
                        ancien[0] if ancien else analyse,
                        analyse,
                        analyse,
                    ),
                )

    def candidats(self, analyse: float | None = None) -> list[dict[str, Any]]:
        if analyse is None:
            ligne = self.db.execute("SELECT MAX(analyse) FROM candidats").fetchone()
            analyse = ligne[0] if ligne else None
        if analyse is None:
            return []
        lignes = self.db.execute(
            "SELECT donnees, premier_vu FROM candidats WHERE analyse = ? ORDER BY score DESC", (analyse,)
        )
        resultat = []
        for donnees, premier in lignes:
            c = json.loads(donnees)
            c["premier_vu"] = premier
            resultat.append(c)
        return resultat

    def candidat(self, id_: str) -> dict[str, Any] | None:
        ligne = self.db.execute("SELECT donnees FROM candidats WHERE id = ?", (id_.lower(),)).fetchone()
        return json.loads(ligne[0]) if ligne else None

    # --- coûts de Claude ----------------------------------------------------------------------------------------

    def noter_cout(
        self, mois: str, modele: str, entree: int, sortie: int, cout: float, ok: bool, quand: float | None = None
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO couts (quand, mois, modele, jetons_entree, jetons_sortie, cout_usd, ok) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (quand or time.time(), mois, modele, entree, sortie, cout, int(ok)),
            )

    def cout_du_mois(self, mois: str) -> float:
        return float(
            self.db.execute("SELECT COALESCE(SUM(cout_usd), 0) FROM couts WHERE mois = ?", (mois,)).fetchone()[0]
        )

    def appels_du_jour(self, debut_jour: float) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM couts WHERE quand >= ?", (debut_jour,)).fetchone()[0])

    # --- descriptions (de Claude, ou faites sur place) ----------------------------------------------------------

    def noter_description(self, signature: str, source: str, description: dict[str, Any], quand: float) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO descriptions (signature, source, donnees, quand) VALUES (?, ?, ?, ?)",
                (signature, source, json.dumps(description, ensure_ascii=False), quand),
            )

    def descriptions(self) -> dict[str, dict[str, Any]]:
        """signature → description (avec sa « source » : claude ou locale)."""
        lignes = self.db.execute("SELECT signature, source, donnees FROM descriptions")
        return {s: {**json.loads(d), "source": src} for s, src, d in lignes}
