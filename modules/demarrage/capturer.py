"""Capturer les vraies sorties du Mac pour les tests (lecture seule, anonymisées, jamais envoyées sur GitHub).

    .venv/bin/python -m modules.demarrage.capturer [--masquer mot1,mot2]

Chaque commande lancée ici ne fait que lire. Les sorties sont rangées dans tests/demarrage/fixtures/reelles/,
après anonymisation. Un fichier où ton nom de compte (ou un mot à masquer) resterait visible n'est pas écrit.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from modules.demarrage.anonymat import Secrets, anonymiser, fuites
from modules.demarrage.systeme import Mac

DOSSIER = Path(__file__).resolve().parents[2] / "tests" / "demarrage" / "fixtures" / "reelles"


def _premier_label_tiers(sortie_list: str) -> str | None:
    for ligne in sortie_list.splitlines()[1:]:
        morceaux = ligne.split("\t")
        if len(morceaux) == 3 and morceaux[0].strip().isdigit():
            label = morceaux[2].strip()
            if not label.startswith(("com.apple.", "application.")):
                return label
    return None


def _premier_programme_tiers(sortie_ps: str) -> str | None:
    for ligne in sortie_ps.splitlines():
        morceaux = ligne.split(None, 7)
        if len(morceaux) == 8 and morceaux[7].startswith("/Applications/"):
            return morceaux[7]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture anonymisée des sorties du Mac (lecture seule)")
    parser.add_argument("--masquer", default="", help="mots en plus à cacher, séparés par des virgules")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("❌ À lancer sur le Mac.")
        return 1
    mac = Mac()
    lire = lambda *c: mac.executer(list(c), delai=20).sortie.strip()  # noqa: E731
    secrets = Secrets(
        maison=mac.maison,
        compte=mac.utilisateur,
        nom_complet=lire("id", "-F"),
        ordinateurs=[n for n in (lire("scutil", "--get", n) for n in ("ComputerName", "LocalHostName")) if n]
        + [lire("hostname").split(".")[0]],
        autres=[m.strip() for m in args.masquer.split(",") if m.strip()],
    )
    uid = str(mac.uid)
    commandes: dict[str, list[str]] = {
        "sw_vers": ["sw_vers"],
        "uname": ["uname", "-m"],
        "launchctl_list": ["launchctl", "list"],
        "launchctl_print_gui": ["launchctl", "print", f"gui/{uid}"],
        "launchctl_print_disabled": ["launchctl", "print-disabled", f"gui/{uid}"],
        "launchctl_print_system": ["launchctl", "print", "system"],
        "ps": ["ps", "-axo", "pid=,ppid=,uid=,%cpu=,rss=,etime=,time=,comm=", "-ww"],
        "ps_lstart": ["ps", "-axo", "pid=,uid=,lstart=,comm=", "-ww"],
        "top": ["top", "-l", "2", "-s", "1", "-stats", "pid,command,cpu,mem,power", "-o", "power", "-n", "25"],
        "pmset_assertions": ["pmset", "-g", "assertions"],
        "systemextensionsctl_list": ["systemextensionsctl", "list"],
        "sfltool_dumpbtm": ["sfltool", "dumpbtm"],
        "codesign_apple": ["codesign", "-dv", "--verbose=2", "/System/Library/CoreServices/Finder.app"],
        "mdls_date": ["mdls", "-raw", "-name", "kMDItemLastUsedDate", "/System/Applications/Calculator.app"],
        "sysctl_boottime": ["sysctl", "-n", "kern.boottime"],
        "last_console": ["last", "-20", mac.utilisateur],
    }
    sorties: dict[str, tuple[int, str]] = {}
    for nom, commande in commandes.items():
        r = mac.executer(commande, delai=30)
        sorties[nom] = (r.code, r.sortie if r.sortie.strip() else r.erreur)
    label = _premier_label_tiers(sorties["launchctl_list"][1])
    if label:
        r = mac.executer(["launchctl", "print", f"gui/{uid}/{label}"], delai=10)
        sorties["launchctl_print_service"] = (r.code, r.sortie or r.erreur)
    programme = _premier_programme_tiers(sorties["ps"][1])
    if programme:
        r = mac.executer(["codesign", "-dv", "--verbose=2", programme], delai=10)
        sorties["codesign_tiers"] = (r.code, r.erreur or r.sortie)  # codesign écrit sur la sortie d'erreur

    DOSSIER.mkdir(parents=True, exist_ok=True)
    ecrits, refuses = 0, []
    for nom, (code, texte) in sorties.items():
        propre = anonymiser(texte, secrets)
        if fuites(propre, secrets):
            refuses.append(nom)
            continue
        suffixe = "" if code == 0 else f".code{code}"
        (DOSSIER / f"{re.sub(r'[^a-z_]', '', nom)}{suffixe}.txt").write_text(propre, encoding="utf-8")
        ecrits += 1
    print(f"✅ {ecrits} sortie(s) anonymisée(s) dans {DOSSIER}")
    if refuses:
        print(f"⚠️ Pas écrites (un mot sensible restait visible) : {', '.join(refuses)}")
    print("Ensuite : .venv/bin/python -m pytest tests/demarrage/unitaires/test_fixtures_reelles.py -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
