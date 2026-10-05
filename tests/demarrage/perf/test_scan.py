"""§9.6 — le scan d'un gros faux Mac : 900 éléments Apple, 150 apps, 120 agents tiers, et un codesign qui coûte
80 ms par programme (comme le vrai). Premier passage < 15 s, avec le cache codesign < 5 s."""

import plistlib
import time

from modules.demarrage import scan
from modules.demarrage.signatures import CacheSignatures
from modules.demarrage.systeme import Resultat
from tests.demarrage.outils import app, plist, programme, signe_par

LATENCE_CODESIGN_S = 0.08


def gros_mac(mac):
    for i in range(900):
        dossier = "LaunchAgents" if i % 2 else "LaunchDaemons"
        plist(mac, f"/System/Library/{dossier}/com.apple.service{i}.plist", binaire=True,
              Label=f"com.apple.service{i}", Program=f"/usr/libexec/service{i}", RunAtLoad=True)  # fmt: skip
    for i in range(150):
        chemin = app(mac, f"/Applications/App {i} Été.app", f"fr.editeur{i}.app")
        if i % 3 == 0:
            plist(mac, f"{chemin}/Contents/Library/LaunchAgents/fr.editeur{i}.aide.plist", Label=f"fr.editeur{i}.aide",
                  BundleProgram=f"Contents/MacOS/App {i} Été")  # fmt: skip
    for i in range(120):
        prog = programme(mac, f"/Users/utilisateur/Library/Application Support/Outil {i}/agent")
        plist(mac, f"/Users/utilisateur/Library/LaunchAgents/fr.outil{i}.agent.plist", Label=f"fr.outil{i}.agent",
              ProgramArguments=[prog, "--fond"], RunAtLoad=True, KeepAlive=True)  # fmt: skip

    def codesign(commande, m):
        time.sleep(LATENCE_CODESIGN_S)
        return Resultat(0, "", signe_par("Éditeur", "EDITEUR001"))

    mac.repondre_debut(["codesign"], codesign)
    services = "\n".join(f"\t\t{1000 + i}\t-\tfr.outil{i}.agent" for i in range(120))
    mac.repondre(["launchctl", "print", "gui/501"], f"gui/501 = {{\n\tservices = {{\n{services}\n\t}}\n}}\n")
    mac.repondre_debut(["launchctl", "print", "gui/501/"], "x = {\n\truns = 1\n\tlast exit code = 0\n}\n")
    mac.repondre_debut(["mdls"], "2026-10-01 10:00:00 +0000")


def test_scan_rapide_puis_avec_cache(mac, reglages):
    gros_mac(mac)
    cache = CacheSignatures()
    debut = time.perf_counter()
    inventaire = scan.scanner(mac, reglages, cache)
    premier = time.perf_counter() - debut
    signes = len(mac.lancees("codesign"))
    debut = time.perf_counter()
    scan.scanner(mac, reglages, CacheSignatures(cache.entrees))
    second = time.perf_counter() - debut
    print(f"\n   {len(inventaire.fiches)} éléments · 1er scan {premier:.1f} s ({signes} codesign à "
          f"{LATENCE_CODESIGN_S * 1000:.0f} ms, en parallèle) · avec le cache {second:.1f} s")  # fmt: skip
    assert len(inventaire.fiches) >= 1060 and signes >= 170
    assert len(mac.lancees("codesign")) == signes  # le 2e scan n'a rien redemandé
    assert premier < 15 and second < 5
    assert plistlib.loads(mac.chemin("/System/Library/LaunchAgents/com.apple.service1.plist").read_bytes())
