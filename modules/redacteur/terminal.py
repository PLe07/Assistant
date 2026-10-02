"""Le rédacteur dans le Terminal : python assistant.py rediger [style|profil|"ta demande"]."""

import subprocess
import sys

from core.cerveau import ClaudeIndisponible
from modules.redacteur import parametres as p
from modules.redacteur import redaction, style


def faire_style() -> int:
    print("✒️ Je lis tes derniers mails envoyés (sur ton Mac), puis Claude fait ta fiche de style (20 à 40 s)…\n")
    try:
        f = style.creer_fiche()
    except (style.PasDeTextes, ClaudeIndisponible) as e:
        print(f"⛔ {e}")
        return 1
    print(style.texte_fiche(f))
    return 0


def ouvrir_profil() -> int:
    nouveau = style.creer_profil()
    print(("👤 Ton profil vient d'être créé : complète-le (formation, alternance recherchée, expériences…).\n"
           if nouveau else "👤 Ton profil (pour les lettres de motivation) :\n") + f"   {p.PROFIL}")
    if sys.platform == "darwin":
        subprocess.run(["open", "-e", str(p.PROFIL)], check=False)  # dans TextEdit
    return 0


def lancer(demande: str) -> int:
    print("✒️ Claude écrit dans ton style (10 à 30 s)…\n")
    try:
        r = redaction.rediger(demande, "terminal")
    except (redaction.PasDeFiche, ClaudeIndisponible) as e:
        print(f"⛔ {e}")
        return 1
    print(redaction.texte_brouillon(r))
    print(f"\n(gardé dans {r['fichier']})")
    return 0
