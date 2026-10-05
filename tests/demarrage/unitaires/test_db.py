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
