"""Le démarrage automatique (launchd) du superviseur et de l'icône.

    python service.py installer     les démarre maintenant, puis à chaque ouverture de session
    python service.py etat          sont-ils bien en marche ?
    python service.py redemarrer    relance le superviseur et ses modules (après un git pull ou un nouveau jeton)
    python service.py desinstaller  retire le démarrage automatique (tes données et réglages ne bougent pas)

launchd est le planificateur intégré à macOS : on lui dépose une « fiche » (.plist) dans
~/Library/LaunchAgents qui dit quoi lancer. Le superviseur est relancé s'il tombe ;
l'icône aussi, sauf si tu la quittes toi-même depuis son menu.
"""

import argparse
import fcntl
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from core import config

AGENTS = Path.home() / "Library" / "LaunchAgents"
ANCIEN_TRI = "com.assistant.tri-mails"
SERVICES = {
    "superviseur": ("com.assistant.superviseur", "superviseur.py", True),
    "icone": ("com.assistant.icone", "menubar.py", {"SuccessfulExit": False}),  # quittée à la main : reste quittée
}


def _cible() -> str:
    return f"gui/{os.getuid()}"  # ta session utilisateur


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _plist(label: str) -> Path:
    return AGENTS / f"{label}.plist"


def _charge(label: str) -> bool:
    return _launchctl("print", f"{_cible()}/{label}").returncode == 0


def _claude() -> str:
    return shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")


def contenu_plist(nom: str) -> dict:
    label, script, garder_en_vie = SERVICES[nom]
    claude = _claude()
    return {
        "Label": label,
        # Le Python de .venv : celui qui a les bibliothèques installées.
        "ProgramArguments": [sys.executable, str(config.RACINE / script)],
        "WorkingDirectory": str(config.RACINE),
        "RunAtLoad": True,  # au démarrage du Mac / à l'ouverture de session
        "KeepAlive": garder_en_vie,  # relancé s'il tombe
        "ThrottleInterval": 30,  # jamais plus d'une relance toutes les 30 s
        "LimitLoadToSessionType": "Aqua",  # ta session graphique (notifications, icône)
        "EnvironmentVariables": {
            # launchd ne lit pas ~/.zshrc : on lui indique où trouver Claude Code.
            "PATH": f"{Path(claude).parent}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "CLAUDE_BIN": claude,
            "PYTHONUNBUFFERED": "1",
        },
        # Ne reçoit que les plantages inattendus ; le journal normal est logs/assistant.log.
        "StandardOutPath": str(config.LOGS / f"{nom}.launchd.log"),
        "StandardErrorPath": str(config.LOGS / f"{nom}.launchd.log"),
    }


def _superviseur_manuel_actif() -> bool:
    """Un superviseur lancé à la main dans un Terminal tient le verrou."""
    config.DONNEES.mkdir(exist_ok=True)
    with open(config.DONNEES / "superviseur.verrou", "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(f, fcntl.LOCK_UN)
    return False


def installer() -> int:
    if sys.prefix == sys.base_prefix:
        print("⛔ Active d'abord l'environnement Python :  source .venv/bin/activate")
        return 1
    if _charge(ANCIEN_TRI):
        print("⛔ L'ancien service du tri des mails tourne encore. Retire-le d'abord :")
        print("   tri-mails/.venv/bin/python tri-mails/service.py desinstaller")
        return 1
    if not any(_charge(label) for label, _, _ in SERVICES.values()) and _superviseur_manuel_actif():
        print("⛔ Un superviseur tourne déjà dans un Terminal : arrête-le (Ctrl + C), puis relance cette commande.")
        return 1
    config.LOGS.mkdir(exist_ok=True)
    AGENTS.mkdir(parents=True, exist_ok=True)
    for nom, (label, _, _) in SERVICES.items():
        if _charge(label):  # réinstallation : on retire l'ancienne version d'abord
            _launchctl("bootout", f"{_cible()}/{label}")
            time.sleep(1)
        with open(_plist(label), "wb") as f:
            plistlib.dump(contenu_plist(nom), f)
        for _ in range(3):
            r = _launchctl("bootstrap", _cible(), str(_plist(label)))
            if r.returncode == 0:
                break
            time.sleep(2)
        else:
            print(f"⛔ launchd a refusé « {nom} » : {(r.stderr or r.stdout).strip()}")
            return 1
        print(f"✅ {nom} : installé et démarré")
    print("\n   Ils redémarreront tout seuls à chaque ouverture de session.")
    print("   macOS peut afficher une fois « Éléments d'arrière-plan ajoutés » : c'est normal.")
    print("   Vérifie dans 10 secondes :  python service.py etat  et  python assistant.py etat")
    return 0


def etat() -> int:
    for nom, (label, _, _) in SERVICES.items():
        if not _charge(label):
            print(f"⛔ {nom} : non installé (python service.py installer)")
            continue
        infos = _launchctl("print", f"{_cible()}/{label}").stdout
        pid = re.search(r"\bpid = (\d+)", infos)
        code = re.search(r"last exit code = (\S+)", infos)
        print(f"✅ {nom} : " + (f"en marche (pid {pid.group(1)})" if pid else "chargé, pas en marche pour l'instant")
              + (f" · dernier code de sortie : {code.group(1)}" if code else ""))
    if _charge(ANCIEN_TRI):
        print(f"⚠️  L'ancien service du tri ({ANCIEN_TRI}) est encore installé.")
    return 0


def redemarrer() -> int:
    label = SERVICES["superviseur"][0]
    if not _charge(label):
        print("⛔ Le superviseur n'est pas installé : python service.py installer")
        return 1
    _launchctl("kickstart", "-k", f"{_cible()}/{label}")  # arrêt propre puis relance
    print("🔄 Superviseur relancé : ses modules redémarrent avec la dernière version du code.")
    return 0


def desinstaller() -> int:
    for nom, (label, _, _) in SERVICES.items():
        if _charge(label):
            _launchctl("bootout", f"{_cible()}/{label}")
        _plist(label).unlink(missing_ok=True)
        print(f"✅ {nom} : arrêté et retiré du démarrage automatique")
    print("   Tes données, réglages et étiquettes Gmail ne bougent pas. Pour remettre : python service.py installer")
    return 0


def main() -> int:
    actions = {"installer": installer, "etat": etat, "redemarrer": redemarrer, "desinstaller": desinstaller}
    parser = argparse.ArgumentParser(description="Démarrage automatique de l'assistant (launchd)")
    parser.add_argument("action", choices=actions)
    return actions[parser.parse_args().action]()


if __name__ == "__main__":
    sys.exit(main())
