from modules.demarrage.collecteurs import launchd_etat as le
from tests.demarrage.conftest import fixture


def test_list():
    s = le.analyser_list(fixture("launchctl_list.txt"))
    assert s["com.google.keystone.agent"] == le.Service(1234, 0)
    assert s["com.exemple.casse"] == le.Service(None, 78)
    assert s["com.exemple.tue"] == le.Service(None, -9)
    assert s["com.apple.homed"].pid is None
    assert "PID" not in s and s["ligne.sans.tabulation  avec  espaces"].pid is None  # espaces gardés


def test_print_domaine():
    texte = fixture("launchctl_print_gui.txt")
    s = le.analyser_print_domaine(texte)
    assert s["com.docker.helper"] == le.Service(4512, None)
    assert s["com.exemple.casse"] == le.Service(None, 78)
    assert s["com.exemple.tue"] == le.Service(None, -9)
    assert s["com.exemple.Étiquette avec espaces"].pid is None
    assert "com.apple.xpc.launchd.unmanaged.loginwindow.391" not in s  # d'un autre bloc
    d = le.analyser_desactives(texte)
    assert d == {"com.apple.ScreenReaderUIServer": True, "com.microsoft.update.agent": True, "com.docker.helper": False}


def test_print_disabled_recent_et_ancien():
    assert le.analyser_desactives(fixture("launchctl_print_disabled.txt"))["com.exemple.Étiquette avec espaces"]
    ancien = le.analyser_desactives(fixture("launchctl_print_disabled_ancien.txt"))
    assert ancien == {
        "com.apple.ScreenReaderUIServer": True,
        "com.microsoft.update.agent": True,
        "com.docker.helper": False,
    }


def test_formats_inattendus():
    assert le.analyser_print_domaine("") == {}
    assert le.analyser_print_domaine("services = {\n\tligne bizarre\n\t\t\n") == {}  # bloc jamais fermé
    assert le.analyser_desactives('disabled services = {\n\t"x" => peut-être\n}\n') == {}
    assert le.analyser_list("n'importe quoi\n\t\t\n1\t2\t \n") == {}


def test_print_service():
    d = le.analyser_print_service(fixture("launchctl_print_service.txt"))
    assert d.programme.endswith("GoogleSoftwareUpdateAgent") and d.chemin.endswith("com.google.keystone.agent.plist")
    assert (d.relances, d.dernier_code, d.pid, d.etat) == (3, 0, 1234, "running")
    b = le.analyser_print_service(fixture("launchctl_print_service_boucle.txt"))
    assert (b.relances, b.dernier_code, b.etat) == (412, 1, "spawn scheduled")
    assert b.programme == "/Applications/Exemple Boucle.app/Contents/MacOS/aide-boucle"


def test_collecter(mac):
    mac.repondre(["launchctl", "print", "gui/501"], fixture("launchctl_print_gui.txt"))
    mac.repondre(["launchctl", "list"], fixture("launchctl_list.txt"))
    mac.repondre(["launchctl", "print-disabled", "gui/501"], fixture("launchctl_print_disabled.txt"))
    mac.repondre(["launchctl", "print", "system"], "", code=1, erreur="Operation not permitted")
    e = le.collecter(mac)
    assert e.gui["com.google.keystone.agent"].pid == 1234
    assert e.gui["application.com.spotify.client.24242424.24242431"].pid == 2210  # vu seulement par list
    assert e.desactives_gui["com.exemple.Étiquette avec espaces"] is True
    assert not e.systeme_lisible and e.systeme == {} and e.erreurs == []


def test_collecter_systeme_lisible_et_list_seule(mac):
    mac.repondre(["launchctl", "print", "gui/501"], "", code=113, erreur="Could not find domain")
    mac.repondre(["launchctl", "list"], fixture("launchctl_list.txt"))
    mac.repondre(["launchctl", "print", "system"], "services = {\n\t  88  -  com.exemple.daemon\n}\n")
    mac.repondre(
        ["launchctl", "print-disabled", "system"], 'disabled services = {\n\t"com.exemple.daemon" => enabled\n}\n'
    )
    e = le.collecter(mac)
    assert e.systeme_lisible and e.systeme["com.exemple.daemon"].pid == 88
    assert e.desactives_systeme == {"com.exemple.daemon": False}
    assert e.gui["com.docker.helper"].pid == 4512 and len(e.erreurs) == 1


def test_collecter_sans_launchctl_ou_en_panne(mac):
    mac.commandes.discard("launchctl")
    assert le.collecter(mac).erreurs == ["launchctl absent"]
    mac.commandes.add("launchctl")
    e = le.collecter(mac)
    assert len(e.erreurs) == 2 and e.gui == {}


def test_detail(mac):
    mac.repondre(["launchctl", "print", "gui/501/com.exemple.boucle"], fixture("launchctl_print_service_boucle.txt"))
    assert le.detail(mac, "gui/501", "com.exemple.boucle").relances == 412
    assert le.detail(mac, "gui/501", "absent") is None
