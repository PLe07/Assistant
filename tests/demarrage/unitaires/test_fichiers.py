import os

from modules.demarrage.fichiers import existe, localiser, resoudre
from tests.demarrage.outils import programme


def test_lien_absolu_suivi_sous_la_racine(mac):
    programme(mac, "/opt/homebrew/Cellar/outil/1.0/bin/outil")
    mac.chemin("/opt/homebrew/bin").mkdir(parents=True)
    os.symlink("/opt/homebrew/Cellar/outil/1.0/bin/outil", mac.chemin("/opt/homebrew/bin/outil"))
    assert resoudre(mac, "/opt/homebrew/bin/outil") == "/opt/homebrew/Cellar/outil/1.0/bin/outil"
    assert existe(mac, "/opt/homebrew/bin/outil")


def test_lien_relatif_et_dossier_lie(mac):
    programme(mac, "/private/tmp/x/prog")
    os.symlink("private/tmp", mac.chemin("/tmp"))
    assert resoudre(mac, "/tmp/x/prog") == "/private/tmp/x/prog"
    assert resoudre(mac, "/tmp/x/../x/./prog") == "/private/tmp/x/prog"


def test_lien_casse_boucle_et_relatif(mac):
    mac.chemin("/a").mkdir()
    os.symlink("/nulle/part", mac.chemin("/a/casse"))
    os.symlink("/a/boucle", mac.chemin("/a/boucle"))
    assert resoudre(mac, "/a/casse") is None
    assert resoudre(mac, "/a/boucle") is None
    assert resoudre(mac, "relatif/x") is None
    assert not existe(mac, None) and not existe(mac, "")


def test_localiser(mac):
    programme(mac, "/usr/local/bin/outil")
    programme(mac, "/Users/utilisateur/scripts/run.sh")
    assert localiser(mac, "/absolu/x") == "/absolu/x"
    assert localiser(mac, "outil") == "/usr/local/bin/outil"
    assert localiser(mac, "inconnu") is None
    assert localiser(mac, "scripts/run.sh", "/Users/utilisateur") == "/Users/utilisateur/scripts/run.sh"
    assert localiser(mac, "scripts/run.sh") is None
    assert localiser(mac, "run.sh", "/Users/utilisateur/scripts") == "/Users/utilisateur/scripts/run.sh"
