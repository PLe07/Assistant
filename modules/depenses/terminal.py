"""Les dépenses dans le Terminal : python assistant.py depenses [ajouter <photo>|test|reel|tableur|dossier|AAAA-MM]."""

import subprocess
import sys
from pathlib import Path

from core import config
from core.cerveau import ClaudeIndisponible
from modules.depenses import parametres as p
from modules.depenses import recu, tableur


def bilan(mois: str | None = None) -> int:
    print(f"🧾 Mes dépenses · {recu.resume_etat()}\n")
    print(tableur.texte_bilan(tableur.bilan(mois)))
    print(f"\nLe tableur :  python assistant.py depenses tableur   ({p.TABLEUR})")
    return 0


def ajouter(chemins: list[str]) -> int:
    code = 0
    for c in chemins:
        chemin = Path(c).expanduser()
        if not chemin.is_file():
            print(f"⛔ {c} : fichier introuvable")
            code = 1
            continue
        print(f"🧾 {chemin.name} : je lis le reçu sur ton Mac, puis Claude en tire le montant (5 à 15 s)…")
        try:
            print("   " + recu.traiter(chemin, "terminal")["message"])
        except ClaudeIndisponible as e:
            print(f"   ⛔ {e}")
            code = 1
    return code


def changer_mode(mode: str) -> int:
    config.regler_module("depenses", "mode", mode)
    if mode == "reel":
        print("🧾 Dépenses en mode RÉEL : chaque reçu ajoute une ligne à ton tableur (une copie de la photo est rangée).")
    else:
        print("🧪 Dépenses en mode test : rien n'est écrit, une notification dit ce qui l'aurait été.")
    return 0


def ouvrir(quoi: str) -> int:
    cible = p.TABLEUR if quoi == "tableur" else p.dossier_recus()
    if quoi == "tableur" and not cible.exists():
        print("Pas encore de tableur : il est créé au premier reçu ajouté en mode réel.")
        return 1
    if quoi == "dossier":
        cible.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.run(["open", str(cible)], check=False)
    print(f"📂 {cible}")
    return 0
