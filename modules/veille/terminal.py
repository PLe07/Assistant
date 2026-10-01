"""La veille dans le Terminal : python assistant.py veille [sources|page]."""

import subprocess
import sys

from modules.veille import parametres as p
from modules.veille import revue


def lancer() -> int:
    print(f"📰 Je lis {len(p.sources())} site(s), puis Claude trie (20 à 40 s)…\n")
    r = revue.lancer()
    print(revue.texte_revue(r))
    print(f"\nLa page avec les liens :  python assistant.py veille page   ({p.PAGE})")
    return 0


def sources() -> int:
    """Chaque site est-il lisible ? (rien n'est gardé, aucun appel à Claude)"""
    print("📰 Je vérifie les sources de la veille (sans Claude)…\n")
    etats = revue.verifier_sources()
    print(revue.texte_sources(etats))
    if any(s["erreur"] for s in etats):
        print("\nUne source en ⛔ ? Copie-moi ces lignes : je trouverai sa nouvelle adresse.")
    return 1 if etats and all(s["erreur"] for s in etats) else 0


def page() -> int:
    if not p.PAGE.exists():
        print("Pas encore de page : lance d'abord  python assistant.py veille")
        return 1
    if sys.platform == "darwin":
        subprocess.run(["open", str(p.PAGE)], check=False)
        print(f"📄 Page ouverte dans ton navigateur ({p.PAGE})")
    else:
        print(p.PAGE)
    return 0
