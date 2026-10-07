"""Lire la base SQLite d'un autre module sans jamais l'ouvrir (§1.2).

Ouvrir la base d'un module, même en lecture seule, peut créer un fichier `-shm` ou poser un verrou (mode WAL). On
fait donc autrement : on **copie** le fichier `.db` (et ses `-wal` et `-shm` s'ils existent) dans notre dossier
temporaire, octet par octet, en lecture seule, puis on lit la copie.

Une copie prise pendant une écriture peut être incohérente : on relève taille, date et numéro de fichier avant et
après la copie ; s'ils ont bougé, ou si la copie ne passe pas `PRAGMA quick_check`, on recommence avec un délai
croissant (0,2 s, 0,5 s, 1 s, 2 s, 4 s), puis on abandonne pour ce tour (« nouvel essai plus tard ») sans planter.
Une base trop grosse, ou un disque presque plein, n'est pas copiée (le module garde son battement par la date de
ses fichiers).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUFFIXES = ("", "-wal", "-shm")
DELAIS = (0.2, 0.5, 1.0, 2.0, 4.0)
MARGE_DISQUE = 50 * 1024 * 1024
BLOC = 1 << 20


class CopieImpossible(Exception):
    """La base n'a pas pu être copiée proprement ce tour-ci (rien n'a planté, on réessaiera)."""


@dataclass(frozen=True)
class Signature:
    """Taille, date et numéro de fichier de la base et de son journal WAL : « a-t-elle bougé ? »."""

    fichiers: tuple[tuple[int, int, int] | None, ...]

    @property
    def derniere_ecriture(self) -> float | None:
        dates = [f[1] / 1e9 for f in self.fichiers[:2] if f is not None]
        return max(dates) if dates else None


def _stat(chemin: Path) -> tuple[int, int, int] | None:
    try:
        s = os.stat(chemin)
    except OSError:
        return None
    return (s.st_size, s.st_mtime_ns, s.st_ino)


def signature(source: Path) -> Signature:
    """Sans rien ouvrir : un simple `stat` de la base et de son journal."""
    return Signature(tuple(_stat(Path(f"{source}{s}")) for s in SUFFIXES[:2]))


def _copier_fichier(source: Path, cible: Path) -> None:
    # Lecture seule, sans verrou : un simple open(…, "rb"), refermé aussitôt.
    with open(source, "rb") as entree, open(cible, "wb") as sortie:
        while True:
            bloc = entree.read(BLOC)
            if not bloc:
                break
            sortie.write(bloc)


def _verifier_dans(chemin: Path, dossier: Path) -> None:
    if dossier.resolve() not in chemin.resolve().parents:
        raise CopieImpossible("refus : on n'ouvre que nos propres copies")


def connecter_copie(chemin: Path, dossier_copies: Path) -> sqlite3.Connection:
    """Ouvre une copie (jamais l'original : le chemin doit être dans notre dossier de copies)."""
    _verifier_dans(chemin, dossier_copies)
    db = sqlite3.connect(chemin, timeout=1, isolation_level=None)
    db.row_factory = sqlite3.Row
    return db


def _copie_coherente(
    source: Path, dossier_copies: Path, delais: tuple[float, ...], dormir: Callable[[float], None]
) -> tuple[sqlite3.Connection, Path]:
    derniere_raison = ""
    for essai, delai in enumerate((0.0, *delais)):
        if essai:
            dormir(delai)
        temporaire = Path(tempfile.mkdtemp(prefix="copie-", dir=dossier_copies))
        cible = temporaire / "base.db"
        garder = False
        try:
            avant = [_stat(Path(f"{source}{s}")) for s in SUFFIXES[:2]]
            for s in SUFFIXES:
                origine = Path(f"{source}{s}")
                if origine.exists():
                    _copier_fichier(origine, Path(f"{cible}{s}"))
            apres = [_stat(Path(f"{source}{s}")) for s in SUFFIXES[:2]]
            if avant != apres:
                derniere_raison = "base en cours d'écriture"
                continue
            db = connecter_copie(cible, dossier_copies)
            try:
                verdict = db.execute("PRAGMA quick_check").fetchone()
            except sqlite3.DatabaseError as e:
                derniere_raison = f"copie illisible ({e.__class__.__name__})"
                db.close()
                continue
            if not verdict or verdict[0] != "ok":
                derniere_raison = "copie incohérente"
                db.close()
                continue
            garder = True
            return db, temporaire
        except FileNotFoundError:
            derniere_raison = "fichier disparu pendant la copie"
        finally:
            if not garder:
                shutil.rmtree(temporaire, ignore_errors=True)
    raise CopieImpossible(f"{derniere_raison or 'copie impossible'} : nouvel essai plus tard")


@contextmanager
def copie(
    source: Path,
    dossier_copies: Path,
    taille_max: int = 256 * 1024 * 1024,
    delais: tuple[float, ...] = DELAIS,
    dormir: Callable[[float], None] = time.sleep,
) -> Iterator[sqlite3.Connection]:
    """`with copie(base, dossier) as db:` : une connexion à une copie cohérente, effacée en sortant."""
    if not source.is_file():
        raise FileNotFoundError(str(source))
    dossier_copies.mkdir(parents=True, exist_ok=True)
    tailles = [s[0] for s in (_stat(Path(f"{source}{x}")) for x in SUFFIXES) if s is not None]
    total = sum(tailles)
    if total > taille_max:
        raise CopieImpossible(f"base trop grosse pour être copiée sans gêner ({total // (1024 * 1024)} Mo)")
    if shutil.disk_usage(dossier_copies).free < 2 * total + MARGE_DISQUE:
        raise CopieImpossible("disque presque plein : copie reportée")
    db, temporaire = _copie_coherente(source, dossier_copies, delais, dormir)
    try:
        yield db
    finally:
        db.close()
        shutil.rmtree(temporaire, ignore_errors=True)


def colonnes(db: sqlite3.Connection, table: str) -> set[str]:
    """Les colonnes d'une table de la copie (vide si la table n'existe pas)."""
    try:
        return {str(r[1]) for r in db.execute(f"PRAGMA table_info({_ident(table)})").fetchall()}
    except sqlite3.DatabaseError:
        return set()


def tables(db: sqlite3.Connection) -> set[str]:
    return {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}


def _ident(nom: str) -> str:
    return '"' + nom.replace('"', '""') + '"'


class LecteurBases:
    """Lit les bases des modules avec parcimonie : une base qui n'a pas bougé n'est pas recopiée, et une base n'est
    jamais recopiée plus souvent que `intervalle_s` (ses fichiers donnent le battement entre deux copies)."""

    def __init__(
        self,
        dossier_copies: Path,
        intervalle_s: float = 600,
        taille_max: int = 256 * 1024 * 1024,
        horloge: Callable[[], float] = time.time,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.dossier = dossier_copies
        self.intervalle_s = intervalle_s
        self.taille_max = taille_max
        self.horloge = horloge
        self.dormir = dormir
        self._cache: dict[tuple[str, str], tuple[Signature, float, Any]] = {}
        self.erreurs: dict[str, str] = {}

    def lire(self, source: Path, cle: str, fonction: Callable[[sqlite3.Connection], Any], forcer: bool = False) -> Any:
        """Le résultat de `fonction(copie)`, recalculé seulement si la base a bougé et que le délai est passé.

        Renvoie None si la base n'existe pas ou n'a jamais pu être lue (inconnu)."""
        sig = signature(source)
        if sig.fichiers[0] is None:
            return None
        memo = self._cache.get((str(source), cle))
        maintenant = self.horloge()
        if memo is not None and not forcer:
            ancienne, quand, valeur = memo
            if ancienne == sig or maintenant - quand < self.intervalle_s:
                return valeur
        try:
            with copie(source, self.dossier, self.taille_max, dormir=self.dormir) as db:
                valeur = fonction(db)
        except (CopieImpossible, sqlite3.DatabaseError, OSError) as e:
            self.erreurs[str(source)] = str(e) or e.__class__.__name__
            return memo[2] if memo is not None else None
        self.erreurs.pop(str(source), None)
        self._cache[(str(source), cle)] = (sig, maintenant, valeur)
        return valeur
