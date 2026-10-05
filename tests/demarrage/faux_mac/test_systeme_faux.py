"""Le faux Mac lui-même : s'il ment, tous les autres tests mentent."""

import pytest

from modules.demarrage.systeme import RefusAdministrateur, Resultat


def test_racine_deplacee(mac):
    assert mac.chemin("/Library/LaunchAgents") == mac.racine / "Library" / "LaunchAgents"
    assert mac.chemin("relatif/x").as_posix() == "relatif/x"
    p = mac.fichier("/Users/utilisateur/Library/LaunchAgents/a.plist", "x")
    assert p.read_text() == "x" and p.is_relative_to(mac.racine)
    assert mac.chemin(mac.maison).is_dir()


def test_reponses_exactes_puis_par_debut(mac):
    mac.repondre(["launchctl", "list"], "exacte")
    mac.repondre_debut(["launchctl"], "court")
    mac.repondre_debut(["launchctl", "print"], "long")
    assert mac.executer(["launchctl", "list"]).sortie == "exacte"
    assert mac.executer(["launchctl", "print", "gui/501"]).sortie == "long"
    assert mac.executer(["launchctl", "blame", "x"]).sortie == "court"
    assert mac.executer(["ps"]).code == 1  # rien de prévu
    mac.repondre_debut(["launchctl"], "remplacée")
    assert mac.executer(["launchctl", "blame", "x"]).sortie == "remplacée"


def test_reponse_calculee_et_code(mac):
    mac.repondre_debut(["codesign"], lambda c, m: Resultat(0, "", f"Executable={c[-1]}"))
    mac.repondre(["crontab", "-l"], "", code=1, erreur="crontab: no crontab")
    assert mac.executer(["codesign", "-dv", "/x"]).erreur == "Executable=/x"
    r = mac.executer(["crontab", "-l"])
    assert not r.ok and r.erreur.startswith("crontab")


def test_commande_absente(mac):
    mac.commandes.discard("sfltool")
    assert mac.executer(["sfltool", "dumpbtm"]).code == 127
    assert not mac.a_la_commande("sfltool") and mac.a_la_commande("launchctl")


def test_sudo_refuse_avant_tout(mac):
    with pytest.raises(RefusAdministrateur):
        mac.executer(["sudo", "launchctl", "bootout", "system/x"])
    with pytest.raises(RefusAdministrateur):
        mac.executer(["/usr/bin/su", "-"])
    with pytest.raises(ValueError):
        mac.executer([])
    assert mac.appels == []


def test_horloge_et_registre(mac):
    t = mac.maintenant()
    mac.attendre(5)
    mac.attendre(-3)
    assert mac.maintenant() == t + 5
    mac.executer(["launchctl", "list"], env={"A": "1"})
    assert mac.lancees("launchctl") == [["launchctl", "list"]] and mac.environnements == [{"A": "1"}]
