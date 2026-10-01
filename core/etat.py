"""L'état local partagé (donnees/etat.db, SQLite) : qui tourne, notifications, appels à Claude.

Plusieurs programmes y lisent et écrivent en même temps : le mode WAL de SQLite
le permet sans se marcher dessus.
"""

import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime

from core import config

FICHIER = config.DONNEES / "etat.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cles (cle TEXT PRIMARY KEY, valeur TEXT, maj REAL);
CREATE TABLE IF NOT EXISTS modules (
    nom TEXT PRIMARY KEY, statut TEXT, detail TEXT, pid INTEGER, relances INTEGER, maj REAL
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY, quand REAL, module TEXT, titre TEXT, message TEXT,
    empreinte TEXT, envoyee INTEGER, raison TEXT
);
CREATE TABLE IF NOT EXISTS aides (
    id INTEGER PRIMARY KEY, quand REAL, module TEXT, titre TEXT, statut TEXT, texte TEXT,
    vue INTEGER DEFAULT 0, maj REAL
);
CREATE TABLE IF NOT EXISTS appels_claude (
    id INTEGER PRIMARY KEY, quand REAL, module TEXT, modele TEXT, ok INTEGER,
    tokens_entree INTEGER, tokens_sortie INTEGER, erreur TEXT
);
"""


@contextmanager
def connexion():
    config.DONNEES.mkdir(exist_ok=True)
    nouveau = not FICHIER.exists()
    db = sqlite3.connect(FICHIER, timeout=10)
    try:
        if nouveau:
            os.chmod(FICHIER, 0o600)  # lisible par toi seul
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_SCHEMA)
        with db:
            yield db
    finally:
        db.close()


def debut_du_jour() -> float:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


# --- Clés simples -------------------------------------------------------------


def lire(cle: str, defaut=None):
    with connexion() as db:
        ligne = db.execute("SELECT valeur FROM cles WHERE cle = ?", (cle,)).fetchone()
    return ligne[0] if ligne else defaut


def ecrire(cle: str, valeur) -> None:
    with connexion() as db:
        db.execute("INSERT OR REPLACE INTO cles VALUES (?, ?, ?)", (cle, str(valeur), time.time()))


def effacer(cle: str) -> None:
    with connexion() as db:
        db.execute("DELETE FROM cles WHERE cle = ?", (cle,))


# --- Modules (écrit par le superviseur) ----------------------------------------


def maj_modules(lignes: list[tuple]) -> None:
    """lignes = [(nom, statut, detail, pid, relances), …] : remplace tout le tableau."""
    with connexion() as db:
        db.execute("DELETE FROM modules")
        db.executemany(
            "INSERT INTO modules VALUES (?, ?, ?, ?, ?, ?)",
            [(*l, time.time()) for l in lignes],
        )


def modules() -> list[dict]:
    with connexion() as db:
        lignes = db.execute("SELECT nom, statut, detail, pid, relances FROM modules ORDER BY nom").fetchall()
    return [dict(zip(("nom", "statut", "detail", "pid", "relances"), l)) for l in lignes]


# --- Notifications -------------------------------------------------------------


def noter_notification(module, titre, message, empreinte, envoyee: bool, raison: str = "") -> None:
    with connexion() as db:
        db.execute(
            "INSERT INTO notifications (quand, module, titre, message, empreinte, envoyee, raison) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), module, titre, message, empreinte, int(envoyee), raison),
        )


def notifications_envoyees_depuis(instant: float) -> int:
    with connexion() as db:
        return db.execute(
            "SELECT COUNT(*) FROM notifications WHERE envoyee = 1 AND COALESCE(raison, '') != 'test' AND quand >= ?",
            (instant,)
        ).fetchone()[0]


def deja_envoyee(empreinte: str, depuis: float) -> bool:
    """Ce message a-t-il déjà été affiché (ou tenté sans succès) depuis cet instant ?"""
    with connexion() as db:
        return db.execute(
            "SELECT 1 FROM notifications WHERE empreinte = ? AND quand >= ? "
            "AND (envoyee = 1 OR raison = 'échec de l''affichage') LIMIT 1",
            (empreinte, depuis),
        ).fetchone() is not None


def deja_retenue(empreinte: str, depuis: float) -> bool:
    """Ce message a-t-il déjà été retenu (nuit, limite, pause) depuis cet instant ?"""
    with connexion() as db:
        return db.execute(
            "SELECT 1 FROM notifications WHERE empreinte = ? AND quand >= ? AND envoyee = 0 LIMIT 1",
            (empreinte, depuis),
        ).fetchone() is not None


# --- Appels à Claude -------------------------------------------------------------


def noter_appel(module, modele, ok: bool, tokens_entree=0, tokens_sortie=0, erreur="") -> None:
    with connexion() as db:
        db.execute(
            "INSERT INTO appels_claude (quand, module, modele, ok, tokens_entree, tokens_sortie, erreur) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), module, modele, int(ok), tokens_entree, tokens_sortie, erreur),
        )


def appels_aujourdhui() -> tuple[int, int, int]:
    """(appels réussis, tokens lus, tokens écrits) depuis minuit. Les échecs ne comptent pas
    dans le plafond : ils ne consomment presque rien."""
    with connexion() as db:
        n, entree, sortie = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(tokens_entree), 0), COALESCE(SUM(tokens_sortie), 0) "
            "FROM appels_claude WHERE ok = 1 AND quand >= ?",
            (debut_du_jour(),),
        ).fetchone()
    return n, entree, sortie


# --- Aides proposées (💡) ----------------------------------------------------------------
# Statuts : proposee → demandee (clic sur 💡) → prete / echec / expiree.
# Seuls le titre et l'aide rédigée par Claude sont ici : jamais ce que tu as dit.


def proposer_aide(module: str, titre: str) -> int:
    with connexion() as db:
        return db.execute(
            "INSERT INTO aides (quand, module, titre, statut, texte, maj) VALUES (?, ?, ?, 'proposee', '', ?)",
            (time.time(), module, titre, time.time()),
        ).lastrowid


def aides_recentes(depuis: float) -> list[dict]:
    with connexion() as db:
        lignes = db.execute(
            "SELECT id, quand, module, titre, statut, texte, vue FROM aides WHERE quand >= ? ORDER BY quand DESC",
            (depuis,),
        ).fetchall()
    return [dict(zip(("id", "quand", "module", "titre", "statut", "texte", "vue"), l)) for l in lignes]


def demander_aide(id_aide: int) -> bool:
    with connexion() as db:
        return db.execute(
            "UPDATE aides SET statut = 'demandee', maj = ? WHERE id = ? AND statut = 'proposee'",
            (time.time(), id_aide),
        ).rowcount == 1


def aides_demandees(module: str) -> list[dict]:
    with connexion() as db:
        lignes = db.execute("SELECT id, titre FROM aides WHERE module = ? AND statut = 'demandee'", (module,)).fetchall()
    return [{"id": i, "titre": t} for i, t in lignes]


def finir_aide(id_aide: int, texte: str, statut: str) -> None:
    with connexion() as db:
        db.execute("UPDATE aides SET texte = ?, statut = ?, maj = ? WHERE id = ?", (texte, statut, time.time(), id_aide))


def expirer_aides(module: str, texte: str) -> None:
    """Les aides pas encore rédigées de ce module ne pourront plus l'être (extraits oubliés)."""
    with connexion() as db:
        db.execute("UPDATE aides SET texte = ?, statut = 'expiree', maj = ? "
                   "WHERE module = ? AND statut IN ('proposee', 'demandee', 'a_capturer')", (texte, time.time(), module))


# « M'aider avec cet écran » : l'icône pose la demande, le module « yeux » capture et la passe en « demandee ».

def demander_capture(module: str = "yeux") -> int:
    with connexion() as db:
        return db.execute(
            "INSERT INTO aides (quand, module, titre, statut, texte, maj) VALUES (?, ?, ?, 'a_capturer', '', ?)",
            (time.time(), module, "Aide sur ton écran", time.time()),
        ).lastrowid


def aides_a_capturer(module: str) -> list[dict]:
    with connexion() as db:
        lignes = db.execute("SELECT id, titre FROM aides WHERE module = ? AND statut = 'a_capturer'", (module,)).fetchall()
    return [{"id": i, "titre": t} for i, t in lignes]


def preparer_aide(id_aide: int, titre: str) -> None:
    with connexion() as db:
        db.execute("UPDATE aides SET titre = ?, statut = 'demandee', maj = ? WHERE id = ? AND statut = 'a_capturer'",
                   (titre, time.time(), id_aide))


def marquer_vue(id_aide: int) -> None:
    with connexion() as db:
        db.execute("UPDATE aides SET vue = 1 WHERE id = ?", (id_aide,))


def purger_aides(avant: float) -> None:
    with connexion() as db:
        db.execute("DELETE FROM aides WHERE quand < ?", (avant,))


# --- Résumé (pour l'icône et la commande « etat ») ---------------------------------


SUPERVISEUR_SILENCIEUX_APRES = 15  # secondes sans battement → considéré arrêté


def resume() -> dict:
    reglages = config.charger()
    vivant = lire("superviseur_vivant")
    superviseur_actif = vivant is not None and time.time() - float(vivant) < SUPERVISEUR_SILENCIEUX_APRES
    mods = modules() if superviseur_actif else []
    en_erreur = [m for m in mods if m["statut"] in ("relance", "introuvable")]
    with connexion() as db:
        envoyees, bloquees = db.execute(
            "SELECT COALESCE(SUM(envoyee), 0), COALESCE(SUM(1 - envoyee), 0) FROM notifications WHERE quand >= ?",
            (debut_du_jour(),),
        ).fetchone()
    appels, tokens_entree, tokens_sortie = appels_aujourdhui()
    test = lire("micro_test")  # le mode test (python -m modules.oreilles --test) ouvre aussi le micro
    micro_actif = (any(m["statut"] == "actif" and config.CAPTEURS.get(m["nom"]) == "micro" for m in mods)
                   or (test is not None and time.time() - float(test) < 5))
    son = lire("oreilles_son")  # dernier instant où le micro a transmis du son (jamais le son lui-même)
    micro_son = time.time() - float(son) if micro_actif and son is not None else None
    micro_muet = lire("oreilles_muet") if micro_actif else None  # aucun son : l'autorisation macOS, si connue
    micro_nom = lire("oreilles_micro") if micro_actif else None
    test = lire("ecran_test")  # idem pour l'écran (python -m modules.yeux --test)
    ecran_actif = (any(m["statut"] == "actif" and config.CAPTEURS.get(m["nom"]) == "ecran" for m in mods)
                   or (test is not None and time.time() - float(test) < 5))
    regard = lire("yeux_regard")  # dernier coup d'œil (jamais ce qui a été vu)
    ecran_regard = time.time() - float(regard) if ecran_actif and regard is not None else None
    ecran_alerte = lire("yeux_alerte") if ecran_actif else None  # « autorisation » ou « capture »
    aides = [a for a in aides_recentes(time.time() - 2 * 3600)
             if not a["vue"] and a["statut"] in ("proposee", "demandee", "prete", "a_capturer")]
    capteurs = ("🎙" if micro_actif else "") + ("👁" if ecran_actif else "")
    if reglages["pause_globale"]:
        icone = "⏸"
    elif not superviseur_actif:
        icone = capteurs or "⚪"
    else:
        # 🎙 et 👁 restent toujours visibles quand le micro ou l'écran sont actifs, même avec une aide ou une erreur.
        icone = capteurs + ("⚠️" if en_erreur or ecran_alerte or micro_muet else "") + ("💡" if aides else "") or "🟢"
    return {
        "icone": icone,
        "pause": reglages["pause_globale"],
        "pause_micro": reglages["pause_micro"],
        "micro_actif": micro_actif,
        "micro_son": micro_son,
        "micro_muet": micro_muet,
        "micro_nom": micro_nom,
        "pause_ecran": reglages["pause_ecran"],
        "ecran_actif": ecran_actif,
        "ecran_regard": ecran_regard,
        "ecran_alerte": ecran_alerte,
        "mode_yeux": "reel" if reglages["modules"].get("yeux", {}).get("mode") == "reel" else "journal",
        "aides": aides,
        "superviseur_actif": superviseur_actif,
        "modules": mods,
        "proactivite": reglages["niveau_proactivite"],
        "notifications": (envoyees, bloquees),
        "claude": (appels, reglages["claude"]["appels_max_par_jour"], tokens_entree, tokens_sortie),
    }
