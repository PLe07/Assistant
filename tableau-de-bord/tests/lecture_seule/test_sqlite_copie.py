"""Les bases des autres modules : jamais ouvertes, seulement copiées puis lues dans la copie (§1.2)."""

from __future__ import annotations

import hashlib
import multiprocessing
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from tableau.sondes import sqlite_copie
from tableau.sondes.sqlite_copie import CopieImpossible, LecteurBases, copie


def empreintes(dossier: Path) -> dict[str, tuple[str, int]]:
    """SHA-256 et date de modification de chaque fichier du dossier."""
    return {
        p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in sorted(dossier.iterdir())
        if p.is_file()
    }


def base_wal(chemin: Path, lignes: int = 5) -> sqlite3.Connection:
    """Une base en mode WAL, laissée ouverte (comme un module qui tourne) : -wal et -shm existent."""
    db = sqlite3.connect(chemin, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS couts (id INTEGER PRIMARY KEY, quand REAL, cout_usd REAL)")
    for i in range(lignes):
        db.execute("INSERT INTO couts (quand, cout_usd) VALUES (?, ?)", (time.time(), 0.01 * i))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('battement', ?)", (str(time.time()),))
    return db


def test_copie_lit_les_donnees_du_wal_sans_toucher_l_original(tmp_path: Path) -> None:
    module = tmp_path / "module"
    module.mkdir()
    ecrivain = base_wal(module / "m.db")
    assert (module / "m.db-wal").exists() and (module / "m.db-shm").exists()
    avant = empreintes(module)
    copies = tmp_path / "copies"
    with copie(module / "m.db", copies) as db:
        assert db.execute("SELECT COUNT(*) FROM couts").fetchone()[0] == 5
        assert db.execute("SELECT valeur FROM meta WHERE cle = 'battement'").fetchone()[0]
        assert sqlite_copie.tables(db) == {"meta", "couts"}
        assert sqlite_copie.colonnes(db, "couts") == {"id", "quand", "cout_usd"}
        assert sqlite_copie.colonnes(db, "absente") == set()
    assert empreintes(module) == avant, "l'original a bougé"
    assert sorted(p.name for p in module.iterdir()) == ["m.db", "m.db-shm", "m.db-wal"], "un fichier est apparu"
    assert list(copies.iterdir()) == [], "la copie n'a pas été effacée"
    ecrivain.close()


def test_jamais_d_ouverture_hors_de_nos_copies(tmp_path: Path) -> None:
    (tmp_path / "copies").mkdir()
    with pytest.raises(CopieImpossible):
        sqlite_copie.connecter_copie(tmp_path / "ailleurs.db", tmp_path / "copies")


def test_base_absente_trop_grosse_ou_disque_plein(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(FileNotFoundError):
        with copie(tmp_path / "absente.db", tmp_path / "copies"):
            pass
    base_wal(tmp_path / "m.db", 50).close()
    with pytest.raises(CopieImpossible, match="trop grosse"):
        with copie(tmp_path / "m.db", tmp_path / "copies", taille_max=10):
            pass

    class Usage:
        free = 10

    monkeypatch.setattr(sqlite_copie.shutil, "disk_usage", lambda _p: Usage())
    with pytest.raises(CopieImpossible, match="disque presque plein"):
        with copie(tmp_path / "m.db", tmp_path / "copies"):
            pass


def test_base_qui_bouge_pendant_la_copie_est_recopiee_avec_un_delai_croissant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_wal(tmp_path / "m.db").close()
    attentes: list[float] = []
    appels = {"n": 0}
    vrai_stat = sqlite_copie._stat

    def stat_qui_bouge(chemin: Path) -> Any:
        appels["n"] += 1
        r = vrai_stat(chemin)
        # Les 3 premiers essais voient la base changer entre le « avant » et le « après ».
        if r is not None and appels["n"] <= 12 and appels["n"] % 4 in (3, 0):
            return (r[0] + 1, r[1], r[2])
        return r

    monkeypatch.setattr(sqlite_copie, "_stat", stat_qui_bouge)
    with copie(tmp_path / "m.db", tmp_path / "copies", dormir=attentes.append) as db:
        assert db.execute("SELECT COUNT(*) FROM couts").fetchone()[0] == 5
    assert attentes == [0.2, 0.5, 1.0]


def test_abandon_propre_apres_tous_les_essais(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_wal(tmp_path / "m.db").close()
    compteur = iter(range(10_000))
    monkeypatch.setattr(sqlite_copie, "_stat", lambda c: (next(compteur), 0, 0))
    attentes: list[float] = []
    with pytest.raises(CopieImpossible, match="en cours d'écriture : nouvel essai plus tard"):
        with copie(tmp_path / "m.db", tmp_path / "copies", dormir=attentes.append):
            pass
    assert attentes == list(sqlite_copie.DELAIS)
    assert list((tmp_path / "copies").iterdir()) == []


def test_copie_incoherente_ou_illisible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pas_une_base.db").write_bytes(b"SQLite format 3\x00" + b"\xff" * 5000)
    with pytest.raises(CopieImpossible, match="illisible|incohérente"):
        with copie(tmp_path / "pas_une_base.db", tmp_path / "copies", dormir=lambda _s: None):
            pass
    base_wal(tmp_path / "m.db").close()

    class Faux:
        def __init__(self, reponse: Any) -> None:
            self.reponse = reponse

        def execute(self, _sql: str) -> Any:
            return self

        def fetchone(self) -> Any:
            return self.reponse

        def close(self) -> None:
            pass

    monkeypatch.setattr(sqlite_copie, "connecter_copie", lambda c, d: Faux(("*** in database main ***",)))
    with pytest.raises(CopieImpossible, match="incohérente"):
        with copie(tmp_path / "m.db", tmp_path / "copies", dormir=lambda _s: None):
            pass


def test_fichier_qui_disparait_pendant_la_copie(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_wal(tmp_path / "m.db").close()

    def disparu(_s: Path, _c: Path) -> None:
        raise FileNotFoundError("parti")

    monkeypatch.setattr(sqlite_copie, "_copier_fichier", disparu)
    with pytest.raises(CopieImpossible, match="disparu"):
        with copie(tmp_path / "m.db", tmp_path / "copies", dormir=lambda _s: None):
            pass


def _ecrire_sans_arret(chemin: str, fin: float, erreurs: Any) -> None:
    """Un « module » qui écrit sans arrêt dans sa base WAL, comme Corvées ou le Trieur."""
    db = sqlite3.connect(chemin, timeout=0.05, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    i = 0
    while time.time() < fin:
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO couts (quand, cout_usd) VALUES (?, ?)", (time.time(), 0.001))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('battement', ?)", (str(time.time()),))
            db.execute("COMMIT")
            i += 1
            if i % 50 == 0:
                db.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.OperationalError as e:
            erreurs.put(str(e))
            try:
                db.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
    db.close()


def test_lecture_pendant_les_ecritures_jamais_de_verrou(tmp_path: Path) -> None:
    """La base est lue 30 fois pendant que son module écrit sans arrêt : 0 plantage, et le module ne voit jamais
    « database is locked » (timeout de 50 ms seulement de son côté)."""
    module = tmp_path / "module"
    module.mkdir()
    base_wal(module / "m.db").close()
    erreurs: Any = multiprocessing.Queue()
    p = multiprocessing.Process(target=_ecrire_sans_arret, args=(str(module / "m.db"), time.time() + 6, erreurs))
    p.start()
    lues, abandons = 0, 0
    try:
        for _ in range(30):
            try:
                with copie(module / "m.db", tmp_path / "copies") as db:
                    assert db.execute("SELECT COUNT(*) FROM couts").fetchone()[0] >= 5
                    lues += 1
            except CopieImpossible:
                abandons += 1
            time.sleep(0.1)
    finally:
        p.join(30)
    vues = []
    while not erreurs.empty():
        vues.append(erreurs.get())
    assert vues == [], f"le module a vu : {vues}"
    assert lues >= 20, f"{lues} lectures réussies seulement ({abandons} reportées)"
    assert list((tmp_path / "copies").iterdir()) == []


def test_lecteur_ne_recopie_pas_une_base_qui_n_a_pas_bouge(tmp_path: Path, horloge: Any) -> None:
    ecrivain = base_wal(tmp_path / "m.db")
    lecteur = LecteurBases(tmp_path / "copies", intervalle_s=600, horloge=horloge)
    appels: list[int] = []

    def compter(db: sqlite3.Connection) -> int:
        n = int(db.execute("SELECT COUNT(*) FROM couts").fetchone()[0])
        appels.append(n)
        return n

    assert lecteur.lire(tmp_path / "m.db", "n", compter) == 5
    assert lecteur.lire(tmp_path / "m.db", "n", compter) == 5
    assert appels == [5]  # pas recopiée
    ecrivain.execute("INSERT INTO couts (quand, cout_usd) VALUES (1, 1)")
    os.utime(tmp_path / "m.db-wal", ns=(1, time.time_ns() + 10**9))
    assert lecteur.lire(tmp_path / "m.db", "n", compter) == 5  # a bougé, mais trop tôt : ancienne valeur
    horloge.avancer(60)
    assert lecteur.lire(tmp_path / "m.db", "n", compter) == 6  # petite base : relue au tour suivant
    ecrivain.execute("INSERT INTO couts (quand, cout_usd) VALUES (1, 1)")
    os.utime(tmp_path / "m.db-wal", ns=(1, time.time_ns() + 2 * 10**9))
    sqlite_copie.PETITE_BASE, ancienne = 0, sqlite_copie.PETITE_BASE
    try:
        horloge.avancer(60)
        assert lecteur.lire(tmp_path / "m.db", "n", compter) == 6  # « grosse » base : pas avant 10 min
    finally:
        sqlite_copie.PETITE_BASE = ancienne
    horloge.avancer(601)
    assert lecteur.lire(tmp_path / "m.db", "n", compter) == 7
    assert lecteur.lire(tmp_path / "m.db", "n", compter, forcer=True) == 7
    assert appels == [5, 6, 7, 7]
    assert lecteur.lire(tmp_path / "absente.db", "n", compter) is None
    ecrivain.close()


def test_lecteur_tolere_une_base_illisible(tmp_path: Path, horloge: Any) -> None:
    (tmp_path / "x.db").write_bytes(b"pas une base")
    lecteur = LecteurBases(tmp_path / "copies", horloge=horloge, dormir=lambda _s: None)
    assert lecteur.lire(tmp_path / "x.db", "n", lambda db: 1) is None
    assert str(tmp_path / "x.db") in lecteur.erreurs
    base_wal(tmp_path / "m.db").close()
    assert lecteur.lire(tmp_path / "m.db", "n", lambda db: 7) == 7
    # Une fonction qui échoue (colonne renommée…) : l'ancienne valeur reste, rien ne plante.
    horloge.avancer(10_000)
    os.utime(tmp_path / "m.db", ns=(1, time.time_ns() + 5 * 10**9))

    def casse(db: sqlite3.Connection) -> int:
        db.execute("SELECT colonne_renommee FROM couts")
        return 0

    assert lecteur.lire(tmp_path / "m.db", "n", casse) == 7


def test_signature_et_derniere_ecriture(tmp_path: Path) -> None:
    assert sqlite_copie.signature(tmp_path / "rien.db").derniere_ecriture is None
    base_wal(tmp_path / "m.db").close()
    sig = sqlite_copie.signature(tmp_path / "m.db")
    assert sig.derniere_ecriture is not None and abs(sig.derniere_ecriture - time.time()) < 60


def test_jamais_une_base_dans_icloud(tmp_path: Path) -> None:
    """Une base sous iCloud Drive n'est jamais copiée : la lire forcerait son téléchargement."""
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Module"
    icloud.mkdir(parents=True)
    db = base_wal(icloud / "m.db")
    from tableau import config

    lecteur = sqlite_copie.LecteurBases(tmp_path / "copies", intervalle_s=0,
                                        interdits=lambda p: config.dans_icloud(p, tmp_path))  # fmt: skip
    avant = empreintes(icloud)
    assert lecteur.lire(icloud / "m.db", "x", lambda d: 1) is None
    assert "iCloud" in lecteur.erreurs[str(icloud / "m.db")] and empreintes(icloud) == avant
    assert not (tmp_path / "copies").exists() or not any((tmp_path / "copies").iterdir())
    db.close()


def test_grosse_base_un_budget_de_copie_par_heure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """40 Mo : recopiée au plus toutes les 48 min, même si elle bouge à chaque tour (disque et batterie)."""
    source = tmp_path / "grosse.db"
    db = base_wal(source)
    t = [1000.0]
    taille = [40 * 1024 * 1024]
    vraie = sqlite_copie.signature

    def signature(chemin: Path) -> sqlite_copie.Signature:
        s = vraie(chemin)
        principal = s.fichiers[0]
        assert principal is not None
        return sqlite_copie.Signature(((taille[0], principal[1] + int(t[0]), principal[2]), *s.fichiers[1:]))

    monkeypatch.setattr(sqlite_copie, "signature", signature)
    lecteur = sqlite_copie.LecteurBases(tmp_path / "copies", intervalle_s=600, horloge=lambda: t[0],
                                        dormir=lambda _s: None)  # fmt: skip
    lectures: list[float] = []
    for _ in range(60):  # une heure, un tour par minute, la base bouge à chaque fois
        lecteur.lire(source, "x", lambda d: lectures.append(t[0]) or len(lectures))
        t[0] += 60
    assert len(lectures) == 2 and lectures[1] - lectures[0] >= 40 / 50 * 3600
    taille[0] = 2 * 1024 * 1024  # petite : à chaque tour si elle a bougé
    n = len(lectures)
    for _ in range(3):
        lecteur.lire(source, "x", lambda d: lectures.append(t[0]) or len(lectures))
        t[0] += 60
    assert len(lectures) == n + 3
    db.close()
