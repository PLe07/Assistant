import time

import pytest

from modules.demarrage.db import Base, DisquePlein
from modules.demarrage.notifier import Notifieur, nouveaux_message


@pytest.fixture(autouse=True)
def paris(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def heure(jour, h, m=0):
    return time.mktime((2026, 10, jour, h, m, 0, 0, 0, -1))


@pytest.fixture
def notif(tmp_path, reglages):
    base = Base(tmp_path / "d.db")
    envoyees = []
    n = Notifieur(base, reglages, lambda t, m: envoyees.append((t, m)) or True)
    yield n, envoyees, base
    base.fermer()


def test_silence_et_une_par_jour(notif):
    n, envoyees, base = notif
    assert n.en_silence(heure(5, 23, 30)) and n.en_silence(heure(5, 7, 59)) and not n.en_silence(heure(5, 8, 0))
    assert not n.proposer(
        "nouveau", nouveaux_message(["Zoom Updater (Zoom)"]), heure(5, 23, 30), ["Zoom Updater (Zoom)"]
    )
    assert envoyees == [] and base.lire("en_attente")["genre"] == "nouveau"
    assert not n.relancer(heure(6, 7, 0))  # toujours la nuit
    assert n.relancer(heure(6, 8, 1))
    assert envoyees == [("Nettoyeur de démarrage", "⚠️ Nouveau programme au démarrage : Zoom Updater (Zoom)")]
    assert base.lire("en_attente") is None
    assert not n.proposer("nouveau", "x", heure(6, 15, 0), ["B (b)"])  # déjà une aujourd'hui
    assert not n.relancer(heure(6, 20, 0)) and n.relancer(heure(7, 9, 0)) and len(envoyees) == 2
    assert base.db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 2


def test_les_nouveaux_s_ajoutent_et_passent_avant_le_recap(notif):
    n, envoyees, base = notif
    n.proposer("nouveau", "a", heure(5, 23, 0), ["A (a)"])
    n.proposer("nouveau", "b", heure(5, 23, 10), ["B (b)", "A (a)"])
    assert base.lire("en_attente")["elements"] == ["A (a)", "B (b)"]
    assert not n.proposer("recap", "récap", heure(5, 23, 20))  # le récap ne remplace pas les nouveaux
    assert base.lire("en_attente")["genre"] == "nouveau"
    assert n.proposer("recap", "récap", heure(6, 9, 0))  # 9 h : c'est le nouveau en attente qui part
    assert envoyees[0][1] == "⚠️ 2 nouveaux programmes au démarrage : A (a), B (b)"
    n.proposer("recap", "récap", heure(6, 10, 0))
    assert base.lire("en_attente")["genre"] == "recap" and len(envoyees) == 1


def test_message():
    assert nouveaux_message(["A (x)"]) == "⚠️ Nouveau programme au démarrage : A (x)"
    assert (
        nouveaux_message([f"E{i}" for i in range(5)])
        == "⚠️ 5 nouveaux programmes au démarrage : E0, E1, E2 et 2 autre(s)"
    )


def test_journal_seulement_et_echec(tmp_path, reglages):
    base = Base(tmp_path / "d.db")
    reglages["notifications"]["vers_journal"] = True
    appels = []
    n = Notifieur(base, reglages, lambda t, m: appels.append(m) or True)
    assert n.proposer("recap", "r", heure(5, 12)) and appels == []
    reglages["notifications"]["vers_journal"] = False
    reglages["notifications"]["silence_debut"] = reglages["notifications"]["silence_fin"] = "00:00"
    n2 = Notifieur(base, reglages, lambda t, m: False)  # refusée (pause de l'Assistant…)
    assert not n2.en_silence(heure(5, 3)) and not n2.proposer("recap", "r", heure(6, 12))
    base.fermer()


def test_disque_plein(notif, monkeypatch):
    n, envoyees, base = notif

    def plein(*a, **k):
        raise DisquePlein("full")

    monkeypatch.setattr(base, "ecrire", plein)
    assert not n.proposer("nouveau", "x", heure(5, 23, 30), ["X"])  # gardée… nulle part, sans planter
    assert n.proposer("nouveau", "x", heure(5, 12, 0), ["X"]) and envoyees
