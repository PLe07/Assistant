import os
import sqlite3
import stat

import pytest

from modules.demarrage import db as dbm
from modules.demarrage.modele import Fiche, Inventaire


def inventaire(ts, *labels):
    return Inventaire(ts=ts, fiches=[Fiche(id=f"id-{x}", label=x, source="agent_utilisateur") for x in labels])


def test_creee_privee_et_etat(tmp_path):
    b = dbm.Base(tmp_path / "d" / "demarrage.db")
    b.ecrire("x", {"a": [1, 2]})
    assert b.lire("x") == {"a": [1, 2]} and b.lire("absent", 7) == 7
    b.effacer("x")
    assert b.lire("x") is None
    for f in tmp_path.joinpath("d").iterdir():
        assert stat.S_IMODE(f.stat().st_mode) == 0o600, f.name
    assert stat.S_IMODE(tmp_path.joinpath("d").stat().st_mode) == 0o700
    b.fermer()


def test_droits_corriges(tmp_path):
    chemin = tmp_path / "demarrage.db"
    sqlite3.connect(chemin).close()
    os.chmod(chemin, 0o644)
    dbm.Base(chemin).fermer()
    assert stat.S_IMODE(chemin.stat().st_mode) == 0o600


def test_base_corrompue_reconstruite(tmp_path):
    chemin = tmp_path / "demarrage.db"
    chemin.write_bytes(b"ceci n'est pas une base SQLite" * 100)
    messages = []
    b = dbm.Base(chemin, messages.append)
    b.ecrire("ok", True)
    assert b.lire("ok") is True
    assert len(list(tmp_path.glob("demarrage.db.corrompue-*"))) == 1 and "corrompue" in messages[0]
    b.fermer()


def test_scans_et_apparitions(tmp_path):
    b = dbm.Base(tmp_path / "demarrage.db")
    assert b.dernier_scan() is None
    assert b.enregistrer_scan(inventaire(100.0, "a", "b")) == ["id-a", "id-b"]
    assert b.enregistrer_scan(inventaire(200.0, "a", "c")) == ["id-c"]
    assert b.dernier_scan().ts == 200.0 and [s.ts for s in b.scans(5)] == [200.0, 100.0]
    assert b.premiere_vue("id-a") == 100.0 and b.premiere_vue("id-c") == 200.0 and b.premiere_vue("z") is None
    assert b.premieres_vues() == {"id-a": 100.0, "id-b": 100.0, "id-c": 200.0}
    b.marquer_notifiee("id-c", 201.0)
    assert b.db.execute("SELECT notifiee FROM apparitions WHERE id='id-c'").fetchone()[0] == 201.0
    for i in range(15):
        b.enregistrer_scan(inventaire(300.0 + i, "a"))
    assert b.db.execute("SELECT COUNT(*) FROM scans").fetchone()[0] == dbm.SCANS_GARDES
    b.db.execute("INSERT INTO scans (ts, inventaire) VALUES (999, 'pas du json')")
    b.db.commit()
    assert b.dernier_scan().ts == 314.0  # le scan illisible est ignoré
    b.fermer()


def test_cache_des_signatures(tmp_path):
    b = dbm.Base(tmp_path / "demarrage.db")
    b.sauver_signatures({"/x": {"empreinte": "1:2", "signature": {"etat": "apple"}}})
    b.db.execute("INSERT INTO signatures VALUES ('/casse', 'pas du json')")
    b.db.commit()
    assert b.signatures() == {"/x": {"empreinte": "1:2", "signature": {"etat": "apple"}}}
    b.fermer()


class ConnexionPleine:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a):
        raise sqlite3.OperationalError(self.message)


def test_disque_plein(tmp_path):
    b = dbm.Base(tmp_path / "demarrage.db")
    vraie = b.db
    b.db = ConnexionPleine("database or disk is full")  # type: ignore[assignment]
    with pytest.raises(dbm.DisquePlein):
        b.ecrire("x", 1)
    b.db = ConnexionPleine("no such table: zut")  # type: ignore[assignment]
    with pytest.raises(sqlite3.OperationalError):
        b.ecrire("x", 1)
    b.db = vraie
    b.fermer()


def test_releves_mesures_et_sessions(tmp_path):
    b = dbm.Base(tmp_path / "demarrage.db")
    m = {"cpu_s": 1.5, "rss_ko": 2048, "puissance": None, "veille": True, "pids": [1]}
    b.enregistrer_releve(100.0, "session", None, {"f1": m})
    b.enregistrer_releve(105.0, "session", 42.0, {"f1": {**m, "puissance": 3.0, "veille": False}})
    b.enregistrer_releve(300.0, "croisiere", 3.0, {})
    assert b.releves() == [(100.0, None), (105.0, 42.0), (300.0, 3.0)]
    assert b.releves(101, 400, modes=("session",)) == [(105.0, 42.0)]
    assert b.mesures(modes=("session",)) == [
        (100.0, "session", "f1", 1.5, 2048, None, 1),
        (105.0, "session", "f1", 1.5, 2048, 3.0, 0),
    ]
    assert b.mesures(200) == []
    assert b.session(1.0) is None and b.sessions() == []
    b.enregistrer_session(1.0, 60.0, None, {"demarrage_s": 59.0})
    b.enregistrer_session(2.0, 70.0, 300.0, {"demarrage_s": 68.0})
    b.db.execute("INSERT INTO sessions VALUES (3.0, NULL, NULL, 'pas du json')")
    b.db.commit()
    assert b.session(2.0) == {"boot": 2.0, "connexion": 70.0, "calme": 300.0, "demarrage_s": 68.0}
    assert [s["boot"] for s in b.sessions()] == [1.0, 2.0, 3.0] and b.sessions(1)[0]["connexion"] is None
    b.fermer()


def test_retention_en_agregats(tmp_path):
    b = dbm.Base(tmp_path / "demarrage.db")
    jour = 86400.0
    assert b.purger(60, 100 * jour, lambda t: "x") == 0
    for ts, cpu, rss, p, v in [(1 * jour, 1.0, 100, 2.0, 1), (1 * jour + 60, 2.0, 300, None, 0)]:
        b.enregistrer_releve(ts, "croisiere", 1.0, {"f": {"cpu_s": cpu, "rss_ko": rss, "puissance": p, "veille": v}})
    b.enregistrer_releve(
        90 * jour, "croisiere", 1.0, {"f": {"cpu_s": 9.0, "rss_ko": 1, "puissance": None, "veille": 0}}
    )
    jour_de = lambda t: f"j{int(t // jour)}"  # noqa: E731
    assert b.purger(60, 100 * jour, jour_de) == 2
    assert b.agregats() == [("j1", "f", "croisiere", 3.0, 200, 2.0, 1, 2)]
    assert len(b.mesures()) == 1 and len(b.releves()) == 1  # le récent reste
    b.enregistrer_releve(
        1 * jour + 120, "croisiere", 1.0, {"f": {"cpu_s": 1.0, "rss_ko": 500, "puissance": None, "veille": 1}}
    )
    assert b.purger(60, 100 * jour, jour_de) == 1
    assert b.agregats() == [("j1", "f", "croisiere", 4.0, 300, 2.0, 2, 3)]  # cumulé avec l'agrégat existant
    b.fermer()


def test_zsh(tmp_path):
    b = dbm.Base(tmp_path / "demarrage.db")
    b.enregistrer_zsh(10.0, 250.0, {"causes": []})
    b.enregistrer_zsh(20.0, None, {"erreur": "zsh absent"})
    b.db.execute("INSERT INTO zsh VALUES (30.0, 1.0, 'cassé')")
    b.db.commit()
    assert b.zsh() == [
        {"ts": 10.0, "mediane_ms": 250.0, "causes": []},
        {"ts": 20.0, "mediane_ms": None, "erreur": "zsh absent"},
        {"ts": 30.0, "mediane_ms": 1.0},
    ]
    b.fermer()
