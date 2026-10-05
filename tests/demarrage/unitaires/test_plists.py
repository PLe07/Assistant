import os
import plistlib
from pathlib import Path

import pytest

from modules.demarrage.collecteurs import plists
from modules.demarrage.collecteurs.plists import app_contenant, declaration, est_systeme, lire
from tests.demarrage.conftest import FORMATS
from tests.demarrage.outils import plist, programme

PLISTS = FORMATS / "plists"


def test_lire_xml_binaire_et_pieges(tmp_path):
    assert lire(PLISTS / "com.exemple.xml.plist")[0]["Label"] == "com.exemple.xml"
    assert lire(PLISTS / "com.exemple.binaire.plist")[0]["Label"] == "com.exemple.binaire"
    assert lire(PLISTS / "com.exemple.casse.plist") == (None, "plist corrompu (illisible par launchd aussi)")
    assert lire(PLISTS / "pas-un-dict.plist")[1] == "plist inattendu (pas un dictionnaire)"
    (tmp_path / "vide.plist").write_bytes(b"  \n")
    assert lire(tmp_path / "vide.plist")[1] == "fichier vide"
    assert lire(tmp_path / "absent.plist")[1].startswith("illisible")
    gros = tmp_path / "gros.plist"
    gros.write_bytes(b"x" * (plists.TAILLE_MAX + 1))
    assert lire(gros)[1].startswith("fichier trop gros")


def test_declaration_complete():
    d = declaration(lire(PLISTS / "com.exemple.xml.plist")[0])
    assert d.label == "com.exemple.xml" and d.programme == "/Applications/Exemple.app/Contents/MacOS/exemple-agent"
    assert d.arguments[1] == "--fond" and d.erreurs == []
    assert d.declencheurs.au_chargement and d.declencheurs.intervalle_s == 3600
    assert d.declencheurs.chemins_surveilles == ["/Users/utilisateur/Documents/Exemple"]


def test_keepalive_en_dictionnaire_et_bundleprogram():
    contenu = lire(PLISTS / "com.exemple.keepalive.plist")[0]
    d = declaration(contenu, "/Applications/Exemple.app/Contents/Library/LaunchAgents/com.exemple.keepalive.plist")
    assert d.declencheurs.garder_en_vie and d.declencheurs.garder_conditions == ["NetworkState", "SuccessfulExit"]
    assert d.programme == "/Applications/Exemple.app/Contents/MacOS/aide"
    assert d.bundles_associes == ["com.exemple.app"]
    assert d.declencheurs.calendrier == [{"Hour": 9, "Minute": 0}, {"Weekday": 1, "Hour": 18}]
    assert declaration(contenu).programme == "Contents/MacOS/aide"  # hors d'une app : tel quel


def test_programme_vide_sans_label_et_valeurs_bizarres():
    d = declaration(lire(PLISTS / "com.exemple.vide.plist")[0])
    assert d.programme is None and "aucun programme" in d.erreurs[0]
    d = declaration(lire(PLISTS / "sans-label.plist")[0])
    assert d.label is None and d.erreurs == ["pas de Label"]
    d = declaration({"Label": " ", "Program": 3, "ProgramArguments": "pas une liste", "KeepAlive": "oui",
                     "StartInterval": True, "StartCalendarInterval": {"Hour": True, "Minute": 5},
                     "WatchPaths": "/un", "QueueDirectories": ["/deux", 3], "Disabled": True, "StartOnMount": True,
                     "WorkingDirectory": "/w"})  # fmt: skip
    assert d.label is None and d.programme is None and not d.declencheurs.garder_en_vie
    assert d.declencheurs.intervalle_s is None and d.declencheurs.calendrier == [{"Minute": 5}]
    assert d.declencheurs.chemins_surveilles == ["/un", "/deux"] and d.desactive_plist and d.declencheurs.au_montage
    assert d.repertoire == "/w"


def test_accents_et_disabled():
    d = declaration(lire(PLISTS / "com.exemple.accents.plist")[0])
    assert d.label == "com.exemple.Étiquette avec espaces" and d.desactive_plist
    assert d.programme == "/Applications/Éditeur Café.app/Contents/MacOS/Éditeur Café"


@pytest.mark.parametrize(
    ("arguments", "programme", "interprete"),
    [
        (["/bin/sh", "/Users/u/run.sh"], "/Users/u/run.sh", "/bin/sh"),
        (["/bin/bash", "-l", "/Users/u/run.sh", "--x"], "/Users/u/run.sh", "/bin/bash"),
        (["/bin/zsh", "-c", "FOO=1 exec /opt/x/serveur --port 3"], "/opt/x/serveur", "/bin/zsh"),
        (["/bin/sh", "-c", "cd /x && ./go"], "/bin/sh", None),
        (["/bin/sh", "-c", "'mal fermé"], "'mal", "/bin/sh"),
        (["/usr/bin/python3", "-u", "/Users/u/bot.py"], "/Users/u/bot.py", "/usr/bin/python3"),
        (["/usr/bin/env", "PATH=/x", "-i", "node", "/srv/app.js"], "/srv/app.js", "/usr/bin/env"),
        (["/usr/bin/nice", "-n", "10", "/usr/bin/python3", "/x/agent.py", "/tmp/t"], "/x/agent.py", "/usr/bin/nice"),
        (["/usr/bin/caffeinate", "-i", "-t", "60", "/opt/x/outil"], "/opt/x/outil", "/usr/bin/caffeinate"),
        (["/usr/bin/arch", "-arm64", "/opt/y"], "/opt/y", "/usr/bin/arch"),
        (["/usr/bin/env", "-u", "HOME", "/opt/z"], "/opt/z", "/usr/bin/env"),
        (["/usr/bin/osascript", "-e", "display dialog 1"], "/usr/bin/osascript", None),
        (["/usr/bin/osascript", "/Users/u/s.scpt"], "/Users/u/s.scpt", "/usr/bin/osascript"),
        (["/usr/bin/nohup", "/opt/x/y"], "/opt/x/y", "/usr/bin/nohup"),
        (["/usr/bin/nohup"], "/usr/bin/nohup", None),
        (["/usr/bin/env"], "/usr/bin/env", None),
        (["/usr/bin/open", "-a", "Spotify"], "/Applications/Spotify.app", "/usr/bin/open"),
        (["/usr/bin/open", "/Applications/Zoom.app/"], "/Applications/Zoom.app", "/usr/bin/open"),
        (["/usr/bin/open", "-g"], "/usr/bin/open", None),
        (["/usr/bin/caffeinate", "-i"], "/usr/bin/caffeinate", None),
    ],
)
def test_interpretes(arguments, programme, interprete):
    d = declaration({"Label": "x", "ProgramArguments": arguments})
    assert (d.programme, d.interprete) == (programme, interprete)


def test_app_contenant_et_systeme():
    assert (
        app_contenant("/Applications/Spotify.app/Contents/Frameworks/H.app/Contents/MacOS/H")
        == "/Applications/Spotify.app"
    )
    assert app_contenant("/usr/local/bin/x") is None and app_contenant(None) is None
    assert est_systeme("/usr/libexec/x") and est_systeme("/System/Library/x") and not est_systeme("/usr/local/bin/x")
    assert not est_systeme(None)


def test_fiche_depuis_plist(mac):
    programme(mac, "/opt/outil/bin/agent")
    plist(mac, "/Users/utilisateur/Library/LaunchAgents/com.outil.plist", Label="com.outil",
          ProgramArguments=["/opt/outil/bin/agent"], RunAtLoad=True, Disabled=True)  # fmt: skip
    f = plists.fiche_depuis_plist(mac, "/Users/utilisateur/Library/LaunchAgents/com.outil.plist", "agent_utilisateur")
    assert f.label == "com.outil" and f.programme_existe and f.declencheurs.au_chargement
    assert f.desactive is True and f.details["cle_disabled"] and f.app_parente is None


def test_fiche_plist_lien_symbolique_et_casse(mac):
    dossier = "/Users/utilisateur/Library/LaunchAgents"
    plist(mac, "/opt/homebrew/opt/redis/homebrew.mxcl.redis.plist", Label="homebrew.mxcl.redis",
          ProgramArguments=["/opt/homebrew/opt/redis/bin/redis-server"])  # fmt: skip
    mac.chemin(dossier).mkdir(parents=True)
    os.symlink("/opt/homebrew/opt/redis/homebrew.mxcl.redis.plist", mac.chemin(f"{dossier}/homebrew.mxcl.redis.plist"))
    os.symlink("/disparu.plist", mac.chemin(f"{dossier}/casse.plist"))
    mac.fichier(f"{dossier}/com.exemple.casse.plist", (PLISTS / "com.exemple.casse.plist").read_bytes())
    mac.fichier(f"{dossier}/._com.outil.plist", b"metadonnees")
    mac.fichier(f"{dossier}/notes.txt", b"pas un plist")
    fiches, erreur = plists.fiches_du_dossier(mac, dossier, "agent_utilisateur")
    assert erreur is None
    par_label = {f.label: f for f in fiches}
    assert set(par_label) == {"homebrew.mxcl.redis", "casse", "com.exemple.casse"}
    redis = par_label["homebrew.mxcl.redis"]
    assert redis.details["lien_vers"] == "/opt/homebrew/opt/redis/homebrew.mxcl.redis.plist"
    assert redis.programme_existe is False
    assert par_label["casse"].erreurs == ["lien cassé ou fichier disparu"]
    assert "corrompu" in par_label["com.exemple.casse"].erreurs[0]


def test_dossier_absent_ou_illisible(mac, monkeypatch):
    assert plists.fiches_du_dossier(mac, "/Library/LaunchAgents", "agent_global") == ([], None)
    mac.chemin("/Library/LaunchDaemons").mkdir(parents=True)

    def refus(self):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "iterdir", refus)
    fiches, erreur = plists.fiches_du_dossier(mac, "/Library/LaunchDaemons", "daemon_global")
    assert fiches == [] and "illisible" in erreur


def test_plist_binaire_dans_un_dossier(mac):
    plist(mac, "/Library/LaunchDaemons/com.b.plist", binaire=True, Label="com.b", Program="/x")
    assert mac.chemin("/Library/LaunchDaemons/com.b.plist").read_bytes().startswith(b"bplist")
    fiches, _ = plists.fiches_du_dossier(mac, "/Library/LaunchDaemons", "daemon_global")
    assert fiches[0].label == "com.b" and fiches[0].programme_existe is False
    assert plistlib.loads(mac.chemin("/Library/LaunchDaemons/com.b.plist").read_bytes())["Program"] == "/x"
