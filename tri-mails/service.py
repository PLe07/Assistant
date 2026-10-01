"""Le service automatique (launchd) : installer, surveiller, mettre en pause, arrêter.

    python service.py installer      trie tes nouveaux mails toutes les 3 minutes, en arrière-plan
    python service.py etat           le service tourne-t-il ? quand a eu lieu le dernier passage ?
    python service.py journal        les 30 dernières lignes du journal
    python service.py pause          suspend le tri (sans rien désinstaller)
    python service.py reprendre      relance le tri après une pause
    python service.py desinstaller   arrête et retire le service (tes mails et étiquettes ne bougent pas)
"""

import argparse
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import config
from memoire import Memoire

ETIQUETTE = "com.assistant.tri-mails"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{ETIQUETTE}.plist"
INTERVALLE_SECONDES = 180
JOURNAL = config.DOSSIER_LOGS / "tri.log"


def _cible() -> str:
    return f"gui/{os.getuid()}"  # ta session utilisateur


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _claude() -> str:
    return shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")


def contenu_plist() -> dict:
    """La fiche que lit launchd : quoi lancer, où, et tous les combien."""
    claude = _claude()
    return {
        "Label": ETIQUETTE,
        # Le Python de .venv : celui qui a les bibliothèques installées.
        "ProgramArguments": [sys.executable, str(config.DOSSIER / "trier.py"), "--arriere-plan"],
        "WorkingDirectory": str(config.DOSSIER),
        "StartInterval": INTERVALLE_SECONDES,
        "RunAtLoad": True,  # un premier passage dès l'installation et à chaque ouverture de session
        "ProcessType": "Background",  # priorité basse : ne ralentit jamais ton Mac
        "LowPriorityIO": True,
        "Nice": 10,
        "EnvironmentVariables": {
            # launchd ne lit pas ~/.zshrc : on lui indique où trouver Claude Code.
            "PATH": f"{Path(claude).parent}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "CLAUDE_BIN": claude,
            "PYTHONUNBUFFERED": "1",
        },
        # Ne reçoit que les plantages inattendus ; le journal normal est logs/tri.log.
        "StandardOutPath": str(config.DOSSIER_LOGS / "launchd.log"),
        "StandardErrorPath": str(config.DOSSIER_LOGS / "launchd.log"),
    }


def _charge() -> bool:
    return _launchctl("print", f"{_cible()}/{ETIQUETTE}").returncode == 0


def installer() -> int:
    if sys.prefix == sys.base_prefix:
        print("⛔ Active d'abord l'environnement Python :  source .venv/bin/activate")
        return 1
    if not Path(_claude()).exists():
        print("⛔ Claude Code est introuvable (voir l'étape 3).")
        return 1
    config.DOSSIER_LOGS.mkdir(exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    if _charge():  # réinstallation : on retire l'ancienne version d'abord
        _launchctl("bootout", f"{_cible()}/{ETIQUETTE}")
        time.sleep(1)
    with open(PLIST, "wb") as f:
        plistlib.dump(contenu_plist(), f)
    for essai in range(3):
        r = _launchctl("bootstrap", _cible(), str(PLIST))
        if r.returncode == 0:
            break
        time.sleep(2)
    else:
        print(f"⛔ launchd a refusé le service : {(r.stderr or r.stdout).strip()}")
        return 1
    print("✅ Service installé : tes nouveaux mails seront triés toutes les 3 minutes.")
    print(f"   Fiche launchd : {PLIST}")
    print("   macOS peut afficher une fois « Éléments d'arrière-plan ajoutés » : c'est normal.")
    print("   Vérifie dans 1 minute :  python service.py etat")
    return 0


def desinstaller() -> int:
    if _charge():
        _launchctl("bootout", f"{_cible()}/{ETIQUETTE}")
    PLIST.unlink(missing_ok=True)
    print("✅ Service arrêté et retiré. Tes mails, étiquettes et ta mémoire ne bougent pas.")
    print("   Pour le remettre :  python service.py installer")
    return 0


def pause() -> int:
    config.FICHIER_PAUSE.touch()
    print("⏸  Tri en pause : le service tourne toujours mais ne touche plus à rien.")
    print("   Pour reprendre :  python service.py reprendre")
    return 0


def reprendre() -> int:
    config.FICHIER_PAUSE.unlink(missing_ok=True)
    print("▶️  Tri relancé : prochain passage dans 3 minutes au plus.")
    return 0


def _il_y_a(horodatage: float) -> str:
    minutes = int((time.time() - horodatage) // 60)
    if minutes < 1:
        return "à l'instant"
    if minutes < 60:
        return f"il y a {minutes} min"
    if minutes < 48 * 60:
        return f"il y a {minutes // 60} h {minutes % 60:02d}"
    return f"le {datetime.fromtimestamp(horodatage):%d/%m à %H:%M}"


def etat() -> int:
    print("Service automatique")
    if _charge():
        infos = _launchctl("print", f"{_cible()}/{ETIQUETTE}").stdout
        code = re.search(r"last exit code = (\S+)", infos)
        print(f"  ✅ installé et actif (toutes les {INTERVALLE_SECONDES // 60} min)"
              + (f" · dernier code de sortie : {code.group(1)}" if code else ""))
    elif PLIST.exists():
        print("  ⚠️  fiche présente mais service non chargé :  python service.py installer")
    else:
        print("  ⛔ non installé :  python service.py installer")
    if config.FICHIER_PAUSE.exists():
        print("  ⏸  EN PAUSE (fichier PAUSE) :  python service.py reprendre")

    memoire = Memoire()
    try:
        ok = memoire.lire("dernier_passage_ok")
        erreur = memoire.lire("derniere_erreur")
        pause_claude = memoire.lire("pause_jusqua")
        depart = memoire.lire("date_depart")
        aujourdhui = datetime.now().strftime("%Y-%m-%d")
        lignes = memoire.db.execute(
            "SELECT bac, traite_le FROM mails WHERE statut = 'etiquete'"
        ).fetchall()
    finally:
        memoire.fermer()

    print("\nDerniers passages")
    print(f"  dernier passage réussi : {_il_y_a(float(ok)) if ok else 'aucun pour l’instant'}")
    if erreur:
        quand, _, message = erreur.partition("|")
        if not ok or float(quand) > float(ok):
            print(f"  ⚠️  dernière erreur ({_il_y_a(float(quand))}) : {message}")
    if pause_claude and time.time() < float(pause_claude):
        print(f"  ⏳ Claude indisponible : nouvel essai vers {datetime.fromtimestamp(float(pause_claude)):%H:%M}")

    print("\nMails triés")
    if depart:
        print(f"  depuis la mise en service ({datetime.fromtimestamp(float(depart)):%d/%m/%Y %H:%M}) : {len(lignes)}")
    du_jour = Counter(bac for bac, quand in lignes if (quand or "").startswith(aujourdhui))
    detail = " · ".join(f"{config.BACS[b].etiquette} {n}" for b, n in du_jour.items() if b in config.BACS)
    print(f"  aujourd'hui : {sum(du_jour.values())}" + (f"  ({detail})" if detail else ""))
    return 0


def journal(n: int = 30) -> int:
    if not JOURNAL.exists():
        print("Le journal est encore vide.")
        return 0
    lignes = JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lignes[-n:]))
    return 0


def main() -> int:
    actions = {
        "installer": installer,
        "etat": etat,
        "journal": journal,
        "pause": pause,
        "reprendre": reprendre,
        "desinstaller": desinstaller,
    }
    parser = argparse.ArgumentParser(description="Service automatique de tri des mails (launchd)")
    parser.add_argument("action", choices=actions)
    return actions[parser.parse_args().action]()


if __name__ == "__main__":
    sys.exit(main())
