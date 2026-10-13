"""Ce qu'un appel de programme a le droit d'être : la forme exacte des arguments, programme par programme.
Utilisé par les tests d'injection et l'exécution des corpus : tout appel qui ne colle pas est une faute."""

from __future__ import annotations

import re
from pathlib import Path

from voix.actions import fichiers, minuteur, son
from voix.actions.base import ADRESSE, EXTENSIONS_EXECUTABLES
from voix.actions.pont import BUNDLE

SCRIPTS_PERMIS = {
    tuple(son.LIRE),
    tuple(son.REGLER),
    tuple(son.SOURDINE),
    tuple(son.SANS_SOURDINE),
    tuple(minuteur.NOTIFIER),
}
RACCOURCIS_PERMIS = {"Envoyer au Mac", "Activer concentration", "Désactiver concentration", "Mode lecture",
                     "Heure du café"}  # fmt: skip
MODULES_PERMIS = {
    ("tableau", ("ouvrir",)), ("tableau", ("etat",)), ("ambiance", ("mood",)), ("quotidien", ("menu",)),
    ("bouclier", ("verifier", "--presse-papiers")),
}  # fmt: skip


def _dans(chemin: str, maison: Path) -> bool:
    p = Path(chemin)
    return p.is_absolute() and (p == maison or maison in p.parents) and p.suffix.lower() not in EXTENSIONS_EXECUTABLES


def appel_conforme(prog: str, argv: list[str], maison: Path) -> bool:
    if prog == "open":
        if len(argv) == 2 and argv[0] == "-b":
            return bool(BUNDLE.fullmatch(argv[1]))
        if len(argv) == 2 and argv[0] == "-a":
            return argv[1].endswith(".app")
        if len(argv) == 2 and argv[0] == "-R":
            return _dans(argv[1], maison)
        if len(argv) == 1:
            return _dans(argv[0], maison) or bool(ADRESSE.fullmatch(argv[0]))
        return False
    if prog == "osascript":
        for script in SCRIPTS_PERMIS:
            n = len(script)
            if tuple(argv[:n]) == script:
                reste = argv[n:]
                if script == tuple(son.REGLER):
                    return len(reste) == 1 and reste[0].isdigit() and 0 <= int(reste[0]) <= 100
                if script == tuple(minuteur.NOTIFIER):
                    return len(reste) == 2
                return reste == []
        return False
    if prog == "networksetup":
        return argv in (["-listallhardwareports"],) or (
            len(argv) >= 2 and argv[0] in ("-getairportpower", "-setairportpower")
            and re.fullmatch(r"(?:en|wl)\d{1,2}", argv[1]) is not None
            and (argv[2:] in ([], ["on"], ["off"]))
        )  # fmt: skip
    if prog == "pmset":
        return argv in (["sleepnow"], ["displaysleepnow"], ["-g", "batt"])
    if prog == "defaults":
        return argv in (["read", "-g", "AppleInterfaceStyle"], ["read", "com.apple.screencapture", "location"])
    if prog == "shortcuts":
        return len(argv) == 2 and argv[0] == "run" and argv[1] in RACCOURCIS_PERMIS
    if prog == "mdfind":
        return (len(argv) == 4 and argv[0] == "-onlyin" and argv[1] == str(maison) and argv[2] == "-name"
                and not argv[3].startswith("-"))  # fmt: skip
    if prog == "ambiance" and len(argv) == 2 and argv[0] == "mode":
        return re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", argv[1]) is not None
    return (prog, tuple(argv)) in MODULES_PERMIS


assert fichiers.RESULTATS_MAX <= 9
