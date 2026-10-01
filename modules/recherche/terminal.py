"""La recherche dans le Terminal : python assistant.py recherche "ta question" (ou : recherche page)."""

import subprocess
import sys

from core.cerveau import ClaudeIndisponible
from modules.recherche import parametres as p
from modules.recherche import recherche


def lancer(question: str) -> int:
    print("🌐 Claude cherche sur le web, puis ton Mac vérifie les liens (20 à 90 s)…\n")
    try:
        r = recherche.chercher(question, "terminal")
    except ClaudeIndisponible as e:
        print(f"⛔ Recherche impossible : {e}")
        return 1
    print(recherche.texte_resultat(r, avec_liens=True))
    print("\nToutes tes recherches, liens cliquables :  python assistant.py recherche page")
    return 0


def page() -> int:
    if not p.PAGE.exists():
        print('Pas encore de recherche : python assistant.py recherche "ta question"')
        return 1
    if sys.platform == "darwin":
        subprocess.run(["open", str(p.PAGE)], check=False)
        print(f"📄 Page ouverte dans ton navigateur ({p.PAGE})")
    else:
        print(p.PAGE)
    return 0
