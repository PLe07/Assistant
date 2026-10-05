from modules.demarrage.collecteurs import applications
from tests.demarrage.outils import app, plist


def test_index(mac):
    app(mac, "/Applications/Zoom.app", "us.zoom.xos", "zoom.us", executable="zoom.us")
    app(mac, "/Applications/Utilities/Outil.app", "com.outil")
    app(mac, "/Users/utilisateur/Applications/Perso.app", "com.perso")
    app(mac, "/System/Applications/Notes.app", "com.apple.Notes", "Notes")
    mac.chemin("/Applications/Sans Info.app/Contents").mkdir(parents=True)
    plist(mac, "/Applications/Bizarre.app/Contents/Info.plist", CFBundleIdentifier=3, CFBundleName=" ")
    mac.chemin("/Applications/.cache").mkdir()
    mac.fichier("/Applications/LISEZMOI.txt", "x")
    index = applications.indexer(mac)
    assert index.par_bundle("US.ZOOM.XOS").chemin == "/Applications/Zoom.app"
    assert index.par_bundle("us.zoom.xos").executable == "/Applications/Zoom.app/Contents/MacOS/zoom.us"
    assert index.par_bundle("com.outil").nom == "Outil"
    assert index.par_bundle("com.perso") and index.par_bundle("com.apple.Notes").nom == "Notes"
    sans = index.par_chemin("/Applications/Sans Info.app")
    assert sans.bundle_id is None and sans.nom == "Sans Info" and sans.executable is None
    assert index.par_chemin("/Applications/Bizarre.app").bundle_id is None
    assert index.par_bundle("absent") is None and index.par_chemin("/x") is None


def test_index_dossiers_absents(mac):
    assert applications.indexer(mac).apps == []
