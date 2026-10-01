"""La mémoire de l'Assistant (donnees/memoire.db) : ce que tu lui dis ou demandes, retrouvable en un instant.

Ce qui y entre (seulement ce que TU adresses à l'Assistant) :
- ce que tu lui dis avec le mot d'appel (« Assistant, … ») ;
- ce que tu tapes (« ✍️ Noter ou demander… » dans l'icône, ou python assistant.py noter "…") ;
- les aides 💡 que tu as ouvertes (titre + réponse de Claude) ;
- les rappels compris, et les réponses de ton second cerveau.
Ce qui n'y entre JAMAIS : les conversations entendues autour de toi, le texte de ton écran, le son.

Gardée sur ton Mac jusqu'à ce que tu l'effaces (python assistant.py oublier …). La recherche
se fait sur le Mac (index plein texte de SQLite) : aucun appel à Claude pour chercher.

Les habitudes (table « intentions ») ne gardent AUCUN contenu : quand, d'où (oreilles, yeux…),
quel type de déclencheur, quelle appli, et si tu as ouvert la 💡 ou non.
"""

import os
import re
import sqlite3
import time
from contextlib import contextmanager

from core import config
from core.journal import journal

FICHIER = config.DONNEES / "memoire.db"
GENRES = {"parole": "🗣", "note": "📝", "question": "❓", "aide": "💡", "rappel": "⏰"}
TEXTE_MAX, DETAIL_MAX = 2000, 4000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS souvenirs (
    id INTEGER PRIMARY KEY, quand REAL, genre TEXT, source TEXT, texte TEXT, detail TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS intentions (
    id INTEGER PRIMARY KEY, quand REAL, source TEXT, type TEXT, appli TEXT DEFAULT '', decision TEXT,
    confiance INTEGER, id_aide INTEGER, ouverte INTEGER DEFAULT 0
);
"""
# L'index plein texte : retrouve un mot (sans tenir compte des accents) parmi des milliers de souvenirs.
_INDEX = """
CREATE VIRTUAL TABLE souvenirs_index USING fts5(
    texte, detail, content='souvenirs', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER souvenirs_ajout AFTER INSERT ON souvenirs BEGIN
    INSERT INTO souvenirs_index(rowid, texte, detail) VALUES (new.id, new.texte, new.detail); END;
CREATE TRIGGER souvenirs_retrait AFTER DELETE ON souvenirs BEGIN
    INSERT INTO souvenirs_index(souvenirs_index, rowid, texte, detail) VALUES ('delete', old.id, old.texte, old.detail); END;
INSERT INTO souvenirs_index(souvenirs_index) VALUES ('rebuild');
"""
# Mots trop courants pour aider une recherche (ils sont ignorés).
MOTS_VIDES = set("""
a à au aux avec ce ces cet cette c ça ca d de des du elle en est et être eu il ils j je l la le les leur lui m ma
mais me mes moi mon n ne ni nos notre nous on ou où par pas pour qu que quel quelle quels quelles qui s sa se ses
si son sur t ta te tes toi ton tu un une vos votre vous y est-ce quoi dit dis avais avait ai as a été noté notée
demandé parlé raconté souviens souvenir rappelles rappelle propos concernant sujet chose choses
""".split())

log = journal("memoire")
_index_ok: bool | None = None  # SQLite de ce Mac sait-il faire l'index plein texte ? (presque toujours oui)


@contextmanager
def connexion():
    global _index_ok
    config.DONNEES.mkdir(exist_ok=True)
    nouveau = not FICHIER.exists()
    db = sqlite3.connect(FICHIER, timeout=10)
    try:
        if nouveau:
            os.chmod(FICHIER, 0o600)  # lisible par toi seul
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA secure_delete = ON")  # ce qui est effacé est écrasé par des zéros, pas juste « libéré »
        db.executescript(_SCHEMA)
        if _index_ok is None or not _index_ok:
            existe = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'souvenirs_index'").fetchone()
            if not existe:
                try:
                    db.executescript(_INDEX)
                    existe = True
                except sqlite3.OperationalError:  # pas d'index : la recherche reste possible, en plus simple
                    existe = False
            _index_ok = bool(existe)
        with db:
            yield db
    finally:
        db.close()


def _ligne(l) -> dict:
    return dict(zip(("id", "quand", "genre", "source", "texte", "detail"), l))


# --- Souvenirs ----------------------------------------------------------------------------


def noter(genre: str, texte: str, source: str, detail: str = "") -> int | None:
    texte = " ".join((texte or "").split())[:TEXTE_MAX]
    if not texte:
        return None
    with connexion() as db:
        return db.execute("INSERT INTO souvenirs (quand, genre, source, texte, detail) VALUES (?, ?, ?, ?, ?)",
                          (time.time(), genre, source, texte, (detail or "").strip()[:DETAIL_MAX])).lastrowid


def derniers(n: int = 15) -> list[dict]:
    with connexion() as db:
        return [_ligne(l) for l in db.execute(
            "SELECT id, quand, genre, source, texte, detail FROM souvenirs ORDER BY quand DESC, id DESC LIMIT ?", (n,))]


def compter() -> int:
    with connexion() as db:
        return db.execute("SELECT COUNT(*) FROM souvenirs").fetchone()[0]


def mots_cles(texte: str) -> list[str]:
    mots = []
    for mot in re.findall(r"\w+", (texte or "").lower().replace("’", "'")):
        if (len(mot) > 1 or mot.isdigit()) and mot not in MOTS_VIDES and mot not in mots:
            mots.append(mot)
    return mots[:12]


def chercher(requete: str, n: int = 10) -> list[dict]:
    """Les souvenirs qui contiennent tous les mots importants (sinon : au moins un), les plus pertinents d'abord."""
    mots = mots_cles(requete)
    if not mots:
        return []
    with connexion() as db:
        if _index_ok:
            for lien in (" AND ", " OR "):
                lignes = db.execute(
                    "SELECT s.id, s.quand, s.genre, s.source, s.texte, s.detail FROM souvenirs_index "
                    "JOIN souvenirs s ON s.id = souvenirs_index.rowid WHERE souvenirs_index MATCH ? "
                    "ORDER BY bm25(souvenirs_index), s.quand DESC LIMIT ?",
                    (lien.join(f'"{m}"*' for m in mots), n)).fetchall()
                if lignes or len(mots) == 1:
                    return [_ligne(l) for l in lignes]
            return []
        for lien in (" AND ", " OR "):  # sans index : plus simple (les accents comptent)
            condition = lien.join(["(lower(texte) LIKE ? OR lower(detail) LIKE ?)"] * len(mots))
            valeurs = [v for m in mots for v in (f"%{m}%", f"%{m}%")]
            lignes = db.execute(f"SELECT id, quand, genre, source, texte, detail FROM souvenirs WHERE {condition} "
                                "ORDER BY quand DESC LIMIT ?", (*valeurs, n)).fetchall()
            if lignes or len(mots) == 1:
                return [_ligne(l) for l in lignes]
    return []


def lire(id_souvenir: int) -> dict | None:
    with connexion() as db:
        l = db.execute("SELECT id, quand, genre, source, texte, detail FROM souvenirs WHERE id = ?", (id_souvenir,)).fetchone()
    return _ligne(l) if l else None


def oublier(id_souvenir: int) -> bool:
    with connexion() as db:
        efface = db.execute("DELETE FROM souvenirs WHERE id = ?", (id_souvenir,)).rowcount == 1
        if efface and _index_ok:  # l'index aussi oublie ses mots (sinon ils resteraient dans le fichier)
            db.execute("INSERT INTO souvenirs_index(souvenirs_index) VALUES ('optimize')")
        return efface


def oublier_tout() -> int:
    """Efface tous les souvenirs ET les habitudes. Irréversible : la commande demande confirmation."""
    with connexion() as db:
        n = db.execute("DELETE FROM souvenirs").rowcount
        db.execute("DELETE FROM intentions")
        if _index_ok:
            db.execute("INSERT INTO souvenirs_index(souvenirs_index) VALUES ('rebuild')")  # index vidé pour de bon
    with connexion() as db:
        db.execute("VACUUM")  # le fichier est réécrit : les anciens souvenirs ne traînent pas sur le disque
    return n


# --- Habitudes (aucun contenu) ---------------------------------------------------------------


def noter_intention(source: str, type_: str, appli: str = "", decision: str = "", confiance: int | None = None,
                    id_aide: int | None = None) -> None:
    """Jamais bloquant : une mémoire inaccessible ne doit pas empêcher une aide."""
    try:
        with connexion() as db:
            db.execute("INSERT INTO intentions (quand, source, type, appli, decision, confiance, id_aide) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?)", (time.time(), source, type_, appli or "", decision, confiance, id_aide))
    except sqlite3.Error as e:
        log.error("Habitudes : écriture impossible (%s)", e)


def intention_ouverte(id_aide: int) -> None:
    try:
        with connexion() as db:
            db.execute("UPDATE intentions SET ouverte = 1 WHERE id_aide = ?", (id_aide,))
    except sqlite3.Error as e:
        log.error("Habitudes : écriture impossible (%s)", e)


def habitudes(depuis: float = 0) -> dict:
    with connexion() as db:
        lignes = db.execute("SELECT quand, source, type, appli, decision, ouverte FROM intentions WHERE quand >= ?",
                            (depuis,)).fetchall()
        souvenirs = db.execute("SELECT genre, COUNT(*) FROM souvenirs WHERE quand >= ? GROUP BY genre", (depuis,)).fetchall()
    return {"intentions": [dict(zip(("quand", "source", "type", "appli", "decision", "ouverte"), l)) for l in lignes],
            "souvenirs": dict(souvenirs)}
