"""Les outils communs aux essais guidés en vrai (yeux, mémoire…) : attendre, guider, rappeler l'attention."""

import os
import subprocess
import sys
import time

from core.journal import FICHIER as JOURNAL


def appeler() -> None:
    """Un petit son, et le Terminal revient devant toi : impossible de rater le moment
    (même si macOS n'affiche pas les notifications)."""
    try:
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False, timeout=5)
    except Exception:
        pass
    appli = {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm"}.get(os.environ.get("TERM_PROGRAM", ""))
    if appli:
        subprocess.run(["open", "-a", appli], check=False)


def attendre(condition, secondes: float, pas: float = 2):
    fin = time.time() + secondes
    while time.time() < fin:
        resultat = condition()
        if resultat:
            return resultat
        time.sleep(pas)
    return None


def taille_journal() -> int:
    return JOURNAL.stat().st_size if JOURNAL.exists() else 0


def journal_depuis(position: int) -> str:
    try:
        with open(JOURNAL, encoding="utf-8", errors="replace") as f:
            f.seek(position if JOURNAL.stat().st_size >= position else 0)  # le journal a pu être archivé
            return f.read()
    except OSError:
        return ""


def vider_clavier() -> None:
    """Oublie ce qui a été tapé pendant l'attente : une touche en trop ne doit pas sauter une étape."""
    try:
        import termios

        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def pret_a(actions: list[str]) -> None:
    print("   Ce que tu vas faire :")
    for numero, action in zip("①②③④⑤", actions):
        print(f"   {numero} {action}")
    vider_clavier()
    input("   ➜ Appuie sur Entrée pour commencer… ")
    print("   (Ne tape plus rien ici : le Terminal voit tout seul ce qui se passe.)")
