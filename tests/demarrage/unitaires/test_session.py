import os
import time

import pytest

from modules.demarrage.mesure import session
from tests.demarrage.conftest import fixture

BOOT = 1_791_176_000.0  # lundi 5 octobre 2026, 06:53:20 à Paris


@pytest.fixture(autouse=True)
def paris(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def test_boottime():
    assert session.analyser_boottime(fixture("sysctl_boottime.txt")) == BOOT
    assert session.analyser_boottime("rien") is None


def test_last():
    quand = session.analyser_last(fixture("last_console.txt"), "utilisateur", BOOT)
    assert quand == BOOT + 40  # 06:54:00 à Paris (last est à la minute)
    assert session.analyser_last(fixture("last_console.txt"), "autre", BOOT) is None
    assert session.analyser_last(fixture("last_console.txt"), "utilisateur", BOOT + 86400) is None  # avant ce démarrage
    assert session.analyser_last("utilisateur console Mon Foo  5 06:54 still\n", "utilisateur", BOOT) is None
    assert session.analyser_last(fixture("last_console.txt"), "utilisateur", BOOT, maintenant=BOOT - 100) is None


def test_last_nouvel_an():
    boot = time.mktime((2026, 12, 31, 23, 58, 0, 0, 0, -1))
    texte = "utilisateur  console  Fri Jan  1 00:01   still logged in\n"
    assert session.analyser_last(texte, "utilisateur", boot) == time.mktime((2027, 1, 1, 0, 1, 0, 0, 0, -1))


def test_journal():
    assert session.analyser_journal(fixture("log_loginwindow.txt"), BOOT) == BOOT + 52.0  # 06:54:12 (screenIsUnlocked)
    avec_fuseau = "2026-10-05 04:54:20.000+0000 Df loginwindow[391:1] login success\n"
    assert session.analyser_journal(avec_fuseau, BOOT) == BOOT + 60.0
    assert session.analyser_journal("2026-10-04 06:54:12.000 Df loginwindow[1:1] login success\n", BOOT) is None


def test_connexion(mac):
    mac.repondre(["last", "-20", "utilisateur"], fixture("last_console.txt"))
    assert session.connexion(mac, BOOT, None) == (BOOT + 40, "last")
    assert session.connexion(mac, BOOT, BOOT + 52) == (BOOT + 52, "last + processus")  # même minute : plus précis
    assert session.connexion(mac, BOOT, BOOT + 400) == (BOOT + 40, "last")  # trop loin : on garde last
    mac.repondre(["last", "-20", "utilisateur"], "wtmp begins Tue Sep  1\n")
    mac.repondre_debut(["log", "show"], fixture("log_loginwindow.txt"))
    assert session.connexion(mac, BOOT, None) == (BOOT + 52, "journal")
    mac.commandes.discard("log")
    assert session.connexion(mac, BOOT, BOOT + 30) == (BOOT + 30, "processus")
    assert session.connexion(mac, BOOT, None) == (None, "inconnue")
    assert session.demarrage(mac) is None
    mac.repondre(["sysctl", "-n", "kern.boottime"], fixture("sysctl_boottime.txt"))
    assert session.demarrage(mac) == BOOT


def test_temps_jusquau_calme():
    c = 1000.0
    releves = [(c + t, 80.0) for t in range(0, 100, 5)] + [(c + t, 10.0) for t in range(100, 200, 5)]
    assert session.temps_jusquau_calme(releves, c) == 100.0
    assert session.temps_jusquau_calme(list(reversed(releves)), c) == 100.0  # l'ordre ne compte pas
    bref = [(c + 0, 50.0), (c + 5, 10.0), (c + 10, 10.0), (c + 15, 90.0), (c + 20, 5.0), (c + 50, 5.0)]
    assert session.temps_jusquau_calme(bref, c) == 20.0  # un creux de 10 s ne suffit pas
    assert session.temps_jusquau_calme([(c + 5, 50.0)], c) is None
    assert session.temps_jusquau_calme([(c - 50, 1.0), (c - 10, 1.0)], c) is None  # avant la connexion : ignoré
    assert session.temps_jusquau_calme(releves, c, seuil_pct=5.0) is None


def test_fuseau_retabli():
    assert os.environ["TZ"] == "Europe/Paris"
