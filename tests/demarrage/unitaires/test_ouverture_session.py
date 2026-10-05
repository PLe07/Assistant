from modules.demarrage.collecteurs import ouverture_session as os5
from modules.demarrage.collecteurs.applications import indexer
from modules.demarrage.modele import Fiche
from modules.demarrage.systeme import Resultat
from tests.demarrage.conftest import fixture
from tests.demarrage.outils import app, plist


def test_analyser_dumpbtm():
    elements = os5.analyser_dumpbtm(fixture("sfltool_dumpbtm.txt"))
    par_nom = {e.nom: e for e in elements}
    assert len(elements) == 6
    zoom = par_nom["Zoom"]
    assert (zoom.uid, zoom.genre, zoom.active, zoom.autorise) == (501, "app", True, True)
    assert zoom.chemin == "/Applications/zoom.us.app" and zoom.label == "us.zoom.xos"
    assert zoom.editeur == "Zoom Video Communications, Inc." and zoom.equipe == "BJ4HAAB9B3"
    spotify = par_nom["Spotify"]
    assert spotify.genre == "login item" and not spotify.active
    keystone = par_nom["com.google.keystone.agent.plist"]
    assert keystone.genre == "legacy agent" and keystone.label == "com.google.keystone.agent"
    assert keystone.executable.endswith("GoogleSoftwareUpdateAgent")
    assert (
        par_nom["Éditeur Café"].chemin == "/Applications/Éditeur Café.app" and par_nom["Éditeur Café"].editeur is None
    )
    assert par_nom["com.exemple.vpn.daemon.plist"].uid == 0
    assert par_nom["Exemple Groupe"].genre == "developer" and par_nom["Exemple Groupe"].label == "AB12CD34EF"
    assert os5.analyser_dumpbtm("rien d'utile\n #1:\n Name: orphelin sans UID\n") == []


def test_analyser_system_events():
    lignes = os5.analyser_system_events(fixture("osascript_login_items.txt") + "sans chemin\t\n")
    assert lignes[0] == ("Zoom", "/Applications/zoom.us.app", False)
    assert lignes[1] == ("Éditeur Café", "/Applications/Éditeur Café.app", True)
    assert len(lignes) == 3


def test_deduire():
    lancements = [
        ("/Applications/Spotify.app/Contents/MacOS/Spotify", 1, 20.0),
        ("/Applications/Spotify.app/Contents/Frameworks/H.app/Contents/MacOS/H", 1, 25.0),  # même app
        ("/Users/utilisateur/Applications/Perso.app/Contents/MacOS/Perso", 1, 100.0),
        ("/Applications/Tard.app/Contents/MacOS/Tard", 1, 300.0),  # trop tard
        ("/Applications/Fils.app/Contents/MacOS/Fils", 777, 10.0),  # lancé par un autre programme
        ("/System/Applications/Notes.app/Contents/MacOS/Notes", 1, 10.0),  # Apple
        ("/usr/libexec/x", 1, 5.0),
    ]
    assert os5.deduire(lancements) == ["/Applications/Spotify.app", "/Users/utilisateur/Applications/Perso.app"]


def _mac_avec_apps(mac):
    app(mac, "/Applications/zoom.us.app", "us.zoom.xos", "zoom.us", executable="zoom.us")
    app(mac, "/Applications/Éditeur Café.app", "fr.cafe.editeur", "Éditeur Café")
    return indexer(mac)


def test_sfltool_complete_et_cree(mac):
    index = _mac_avec_apps(mac)
    mac.repondre(["sfltool", "dumpbtm"], fixture("sfltool_dumpbtm.txt"))
    plist_k = "/Users/utilisateur/Library/LaunchAgents/com.google.keystone.agent.plist"
    keystone = Fiche(id="k", label="com.google.keystone.agent", source="agent_utilisateur", chemin_plist=plist_k)
    aide = Fiche(id="h", label="com.spotify.client", source="ouverture_app", charge=True, desactive=False)
    r = os5.collecter(mac, index, [keystone, aide])
    assert r.methode == "sfltool" and r.erreurs == []
    assert keystone.details["btm"]["genre"] == "legacy agent"
    assert aide.actif is False  # désactivé dans les Réglages
    par_label = {f.label: f for f in r.fiches}
    assert set(par_label) == {"us.zoom.xos", "fr.cafe.editeur"}
    zoom = par_label["us.zoom.xos"]
    assert zoom.actif and zoom.programme == "/Applications/zoom.us.app/Contents/MacOS/zoom.us" and zoom.programme_existe
    assert zoom.details["editeur_btm"].startswith("Zoom") and zoom.details["methode"] == "sfltool"
    assert not mac.lancees("osascript")


def test_sfltool_desactive_un_agent_connu(mac):
    texte = (" Records for UID 501 : x\n #1:\n Name: a.plist\n Type: legacy agent (0x10008)\n"
             " Disposition: [disabled, allowed, visible] (0xa)\n Identifier: 16.com.a\n Items:\n")  # fmt: skip
    mac.repondre(["sfltool", "dumpbtm"], texte)
    a = Fiche(id="a", label="com.a", source="agent_utilisateur", actif=True, desactive=False)
    autre_uid = Fiche(id="b", label="com.b", source="agent_utilisateur")
    os5.collecter(mac, indexer(mac), [a, autre_uid])
    assert a.actif is False and a.desactive is True


def test_repli_sur_system_events(mac):
    index = _mac_avec_apps(mac)
    mac.repondre(["sfltool", "dumpbtm"], "", code=1, erreur=fixture("sfltool_refus.txt"))
    mac.repondre_debut(["osascript"], fixture("osascript_login_items.txt") + "Zoom\t/Applications/zoom.us.app\tfalse\n")
    r = os5.collecter(mac, index, [])
    assert r.methode == "osascript" and "administrateur" in r.erreurs[0]
    par_label = {f.label: f for f in r.fiches}
    assert set(par_label) == {"us.zoom.xos", "fr.cafe.editeur", "Parti"}  # Zoom en double : une seule fiche
    assert par_label["Parti"].programme_existe is False and par_label["Parti"].app_parente == "/Applications/Parti.app"
    assert par_label["fr.cafe.editeur"].details["cache"] is True
    commande = mac.lancees("osascript")[0]
    assert commande.count("-e") == len(os5.SCRIPT_SYSTEM_EVENTS) and "delete" not in " ".join(commande)


def test_autorisation_refusee_puis_deduction(mac):
    index = _mac_avec_apps(mac)
    mac.commandes.discard("sfltool")
    mac.repondre_debut(["osascript"], "", code=1, erreur=fixture("osascript_refus.txt"))
    r = os5.collecter(mac, index, [], ["/Applications/zoom.us.app"])
    assert r.methode == "déduction" and r.fiches[0].label == "us.zoom.xos"
    assert any("Automatisation" in e for e in r.erreurs) and "sfltool absent" in r.erreurs


def test_rien_de_possible(mac):
    mac.repondre(["sfltool", "dumpbtm"], "pas de liste")
    mac.repondre_debut(["osascript"], Resultat(124, "", "pas de réponse"))
    r = os5.collecter(mac, indexer(mac), [])
    assert r.methode == "aucune" and r.fiches == []
    assert any("10 s" in e for e in r.erreurs)
    mac.repondre_debut(["osascript"], "", code=2, erreur="autre panne")
    assert any("autre panne" in e for e in os5.collecter(mac, indexer(mac), []).erreurs)
    mac.commandes.discard("osascript")
    assert os5.collecter(mac, indexer(mac), []).methode == "aucune"


def test_app_sans_info_plist(mac):
    plist(mac, "/Applications/Brute.app/Contents/Info.plist", CFBundleName="Brute")
    f = os5._fiche_app(mac, indexer(mac), "/Applications/Brute.app", "", "osascript")
    assert f.label == "Brute" and f.nom == "Brute" and f.programme == "/Applications/Brute.app"
