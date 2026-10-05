"""Le scan complet (S1-S4 + S6) sur un petit faux Mac garni à la main."""

import pytest

from modules.demarrage import scan
from modules.demarrage.collecteurs import agents_utilisateur
from modules.demarrage.signatures import CacheSignatures
from tests.demarrage.outils import SIGNE_APPLE, app, codesign, plist, programme, signe_par

LA = "/Users/utilisateur/Library/LaunchAgents"
T = "\t"


@pytest.fixture
def petit_mac(mac):
    zoom = app(mac, "/Applications/zoom.us.app", "us.zoom.xos", "zoom.us", executable="zoom.us")
    programme(mac, "/Applications/zoom.us.app/Contents/MacOS/ZoomUpdater")
    plist(mac, f"{zoom}/Contents/Library/LaunchAgents/us.zoom.updater.plist", Label="us.zoom.updater",
          BundleProgram="Contents/MacOS/ZoomUpdater", RunAtLoad=True)  # fmt: skip
    app(mac, f"{zoom}/Contents/Library/LoginItems/ZoomHelper.app", "us.zoom.helper", "Zoom Helper")
    # S1
    programme(mac, "/opt/outil/agent")
    plist(mac, f"{LA}/com.outil.agent.plist", Label="com.outil.agent", ProgramArguments=["/opt/outil/agent"],
          RunAtLoad=True, KeepAlive=True)  # fmt: skip
    plist(mac, f"{LA}/com.parti.plist", Label="com.parti", Program="/Applications/Parti.app/Contents/MacOS/Parti")
    plist(mac, f"{LA}/com.attendue.plist", Label="com.attendue", Program="/opt/outil/agent",
          AssociatedBundleIdentifiers=["com.desinstallee"])  # fmt: skip
    plist(mac, f"{LA}/com.assistant.superviseur.plist", Label="com.assistant.superviseur",
          ProgramArguments=["/usr/bin/python3", "/Users/utilisateur/Assistant/superviseur.py"])  # fmt: skip
    programme(mac, "/Users/utilisateur/Assistant/superviseur.py")
    plist(mac, f"{LA}/com.apple.faux.plist", Label="com.apple.faux", Program="/opt/outil/agent")
    programme(mac, "/usr/bin/caffeinate")
    plist(mac, f"{LA}/com.tiers.cafe.plist", Label="com.tiers.cafe", ProgramArguments=["/usr/bin/caffeinate", "-i"])
    plist(mac, f"{LA}/doublon-a.plist", Label="com.doublon", Program="/opt/outil/agent")
    plist(mac, f"{LA}/doublon-b.plist", Label="com.doublon", Program="/opt/outil/agent")
    app(mac, "/Applications/Utilities/Déplacée.app", "com.deplacee")
    plist(
        mac,
        f"{LA}/com.deplacee.plist",
        Label="com.deplacee",
        Program="/Applications/Déplacée.app/Contents/MacOS/Déplacée",
    )
    # S2 et S3
    plist(mac, "/Library/LaunchDaemons/com.vpn.daemon.plist", Label="com.vpn.daemon", Program="/opt/outil/agent")
    plist(mac, "/Library/LaunchAgents/com.outil.agent.plist", Label="com.outil.agent", Program="/opt/outil/agent")
    for i in range(3):
        plist(
            mac, f"/System/Library/LaunchAgents/com.apple.a{i}.plist", Label=f"com.apple.a{i}", Program="/usr/libexec/a"
        )
    plist(mac, "/System/Library/LaunchDaemons/com.apple.d.plist", Label="com.apple.d", Program="/usr/libexec/d")
    # S6
    mac.repondre(
        ["launchctl", "print", "gui/501"],
        f"""gui/501 = {{
{T}services = {{
{T}{T}     101      -      com.outil.agent
{T}{T}       0      1      us.zoom.updater
{T}{T}     303      -      com.inconnu.charge
{T}{T}     404      -      application.com.spotify.client.1.2
{T}{T}       0      -      com.apple.a0
{T}}}
{T}disabled services = {{
{T}{T}"com.parti" => disabled
{T}}}
}}
""",
    )
    mac.repondre(["launchctl", "list"], "PID\tStatus\tLabel\n101\t0\tcom.outil.agent\n")
    mac.repondre(
        ["launchctl", "print-disabled", "gui/501"], 'disabled services = {\n\t"com.tiers.cafe" => enabled\n}\n'
    )
    loin = f"gui/501/com.inconnu.charge = {{\n{T}program = /Applications/Loin.app/Contents/MacOS/x\n{T}runs = 2\n}}\n"
    mac.repondre(["launchctl", "print", "gui/501/com.inconnu.charge"], loin)
    mac.repondre(
        ["launchctl", "print", "gui/501/com.outil.agent"], f"x = {{\n{T}runs = 40\n{T}last exit code = 1\n}}\n"
    )
    zoom_sig = signe_par("Zoom Video Communications, Inc.", "BJ4HAAB9B3")
    mac.repondre_debut(["codesign"], codesign({
        "/opt/outil/agent": signe_par("Outil SAS", "OUTIL12345"),
        f"{zoom}/Contents/MacOS/ZoomUpdater": zoom_sig,
        f"{zoom}/Contents/Library/LoginItems/ZoomHelper.app/Contents/MacOS/ZoomHelper": zoom_sig,
        "/usr/bin/caffeinate": SIGNE_APPLE,
    }))  # fmt: skip
    mac.repondre(
        ["mdls", "-raw", "-name", "kMDItemLastUsedDate", "/Applications/zoom.us.app"], "2026-09-01 10:00:00 +0000"
    )
    return mac


def test_scan_complet(petit_mac, reglages):
    inv = scan.scanner(petit_mac, reglages)
    etats = {c.nom: c.etat for c in inv.collecteurs}
    attendus = {"S1": "ok", "S2": "ok", "S3": "ok", "S4": "ok", "S6": "ok", "S8": "ok", "S10": "ok"}
    assert etats == {**attendus, "S5": "dégradé", "S7": "dégradé", "S9": "dégradé"}  # rien de préparé pour eux
    f = {(x.source, x.label): x for x in inv.fiches}
    agent = f[("agent_utilisateur", "com.outil.agent")]
    assert agent.charge and agent.pids == [101] and agent.actif and agent.desactive is False
    assert agent.editeur == "Outil SAS" and agent.signature == "developpeur" and not agent.est_apple
    assert agent.details["relances"] == 40 and agent.details["dernier_code"] == 1
    assert agent.doublon and f[("agent_global", "com.outil.agent")].doublon  # même label, deux endroits
    assert f[("agent_utilisateur", "com.parti")].desactive and f[("agent_utilisateur", "com.parti")].actif is False
    parti = f[("agent_utilisateur", "com.parti")]
    assert parti.programme_existe is False and parti.app_attendue_absente and "app_deplacee_vers" not in parti.details
    deplacee = f[("agent_utilisateur", "com.deplacee")]
    assert (
        deplacee.app_attendue_absente
        and deplacee.details["app_deplacee_vers"] == "/Applications/Utilities/Déplacée.app"
    )
    attendue = f[("agent_utilisateur", "com.attendue")]
    assert attendue.app_attendue_absente and attendue.details["apps_attendues"] == ["com.desinstallee"]
    assert f[("agent_utilisateur", "com.assistant.superviseur")].c_est_moi
    faux_apple = f[("agent_utilisateur", "com.apple.faux")]
    assert not faux_apple.est_apple and faux_apple.details["se_dit_apple"]
    cafe = f[("agent_utilisateur", "com.tiers.cafe")]
    assert not cafe.est_apple and cafe.details["programme_systeme"] and cafe.editeur is None and cafe.desactive is False
    doublons = [x for x in inv.fiches if x.label == "com.doublon"]
    assert len(doublons) == 2 and len({x.id for x in doublons}) == 2 and all(x.doublon for x in doublons)
    zoom = f[("agent_app", "us.zoom.updater")]
    assert zoom.app_parente == "/Applications/zoom.us.app" and zoom.charge and zoom.actif and zoom.pids == []
    assert zoom.details["dernier_code"] == 1 and zoom.derniere_utilisation_app is not None
    helper = f[("ouverture_app", "us.zoom.helper")]
    assert helper.charge is False and helper.actif is False and helper.editeur.startswith("Zoom")
    vpn = f[("daemon_global", "com.vpn.daemon")]
    assert vpn.charge is None and vpn.desactive is None and vpn.actif is None  # domaine système illisible
    apples = [x for x in inv.fiches if x.source == "apple"]
    assert len(apples) == 4 and all(x.est_apple and x.signature == "apple" for x in apples)
    assert {x.details["domaine"] for x in apples} == {"gui", "system"}
    assert f[("apple", "com.apple.a0")].charge and f[("apple", "com.apple.d")].charge is None
    inconnu = f[("launchd", "com.inconnu.charge")]
    assert (
        inconnu.pids == [303] and inconnu.app_parente == "/Applications/Loin.app" and inconnu.details["relances"] == 2
    )
    assert not any(x.label.startswith("application.") for x in inv.fiches)
    assert not any(
        c[0] == "codesign" and c[-1].startswith("/usr/libexec") for c in petit_mac.appels
    )  # S3 : pas de codesign


def test_cache_des_signatures(petit_mac, reglages):
    cache = CacheSignatures()
    scan.scanner(petit_mac, reglages, cache)
    avant = len(petit_mac.lancees("codesign"))
    scan.scanner(petit_mac, reglages, CacheSignatures(cache.entrees))
    assert avant > 0 and len(petit_mac.lancees("codesign")) == avant


def test_collecteur_en_panne_et_mode_degrade(petit_mac, reglages, monkeypatch):
    def panne(_):
        raise RuntimeError("format inattendu")

    monkeypatch.setattr(agents_utilisateur, "collecter", panne)
    petit_mac.commandes -= {"launchctl", "codesign", "mdls"}
    inv = scan.scanner(petit_mac, reglages)
    etats = {c.nom: (c.etat, c.detail) for c in inv.collecteurs}
    assert etats["S1"] == ("indisponible", "RuntimeError : format inattendu")
    assert etats["S6"] == ("dégradé", "launchctl absent")
    assert inv.fiches and all(x.signature == "inconnue" for x in inv.fiches if not x.est_apple and x.programme_existe)


def test_etape_en_panne(petit_mac, reglages, monkeypatch):
    monkeypatch.setattr(scan, "appliquer_relances", lambda *a: 1 / 0)
    inv = scan.scanner(petit_mac, reglages)
    assert ("relances", "dégradé") in {(c.nom, c.etat) for c in inv.collecteurs}


def test_index_des_apps_en_panne(petit_mac, reglages, monkeypatch):
    from modules.demarrage.collecteurs import applications

    monkeypatch.setattr(applications, "indexer", lambda s: 1 / 0)
    inv = scan.scanner(petit_mac, reglages)
    assert ("apps", "indisponible") in {(c.nom, c.etat) for c in inv.collecteurs}
    assert not any(x.source == "agent_app" for x in inv.fiches)
