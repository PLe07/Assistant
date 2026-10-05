"""Le vrai Mac (systeme.py) avec des commandes inoffensives présentes partout."""

import sys

from modules.demarrage.systeme import Mac


def test_executer_sans_shell():
    r = Mac().executer(["echo", "a b; rm -rf /"])
    assert r.ok and r.sortie == "a b; rm -rf /\n" and r.duree_s >= 0


def test_environnement_ajoute():
    r = Mac().executer(
        [sys.executable, "-c", "import os; print(os.environ['DEMARRAGE_ESSAI'])"], env={"DEMARRAGE_ESSAI": "oui"}
    )
    assert r.sortie.strip() == "oui"


def test_commande_introuvable_et_delai():
    assert Mac().executer(["commande-qui-n-existe-pas-42"]).code == 127
    r = Mac().executer([sys.executable, "-c", "import time; time.sleep(5)"], delai=0.2)
    assert r.code == 124 and "pas de réponse" in r.erreur


def test_chemin_horloge_commandes():
    m = Mac()
    assert str(m.chemin("/Library")) == "/Library"
    assert m.maintenant() > 1_700_000_000
    m.attendre(0)
    assert m.a_la_commande("echo") and not m.a_la_commande("commande-qui-n-existe-pas-42")
