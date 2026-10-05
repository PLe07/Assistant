from modules.demarrage import environnement


def test_reconnaitre_un_mac(mac):
    mac.repondre(["uname", "-m"], "arm64\n")
    mac.repondre(["sw_vers", "-productVersion"], "26.0.1\n")
    env = environnement.reconnaitre(mac)
    assert env.architecture == "arm64" and env.macos == "26.0.1"
    assert env.manquantes == []
    assert set(env.commandes) == set(environnement.COMMANDES)


def test_commandes_absentes(mac):
    mac.commandes -= {"sfltool", "systemextensionsctl", "sw_vers", "uname"}
    env = environnement.reconnaitre(mac)
    assert env.macos.startswith("inconnu") and env.architecture == "inconnue"
    assert set(env.manquantes) == {"sfltool", "systemextensionsctl"}
