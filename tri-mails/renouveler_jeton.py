"""Crée un nouveau jeton Claude (abonnement) et l'enregistre dans .env, sans l'afficher.

Usage :  python renouveler_jeton.py
À relancer quand le jeton expire (il dure 1 an) ou s'il a été exposé.
"""

import getpass
import os
import subprocess
import sys

import config
from classificateur import ClaudeIndisponible, binaire_claude, executer_claude

FICHIER_ENV = config.DOSSIER / ".env"
PREFIXE = "sk-ant-oat01-"


def enregistrer(jeton: str) -> None:
    lignes = FICHIER_ENV.read_text(encoding="utf-8").splitlines() if FICHIER_ENV.exists() else []
    lignes = [l for l in lignes if not l.startswith("CLAUDE_CODE_OAUTH_TOKEN=")]
    lignes.append(f"CLAUDE_CODE_OAUTH_TOKEN={jeton}")
    fd = os.open(FICHIER_ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")
    os.chmod(FICHIER_ENV, 0o600)  # lisible par toi seul, même si le fichier existait déjà


def main() -> int:
    print("1) Création d'un nouveau jeton : ton navigateur va s'ouvrir.\n")
    try:
        subprocess.run([binaire_claude(), "setup-token"], check=True)
    except KeyboardInterrupt:
        print("\nAnnulé.")
        return 1
    except (subprocess.CalledProcessError, ClaudeIndisponible) as e:
        print(f"⛔ La création du jeton a échoué : {e}")
        return 1

    print("\n2) Triple-clique sur la ligne sk-ant-oat01-… ci-dessus, Cmd + C,")
    print("   puis colle-la ici avec Cmd + V et Entrée.")
    for _ in range(3):
        jeton = "".join(getpass.getpass("   Jeton (rien ne s'affiche) : ").split())
        if jeton.startswith(PREFIXE) and len(jeton) > 60:
            break
        print("   ⛔ Ce n'est pas un jeton sk-ant-oat01-… : réessaie.")
    else:
        return 1

    enregistrer(jeton)
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = jeton
    print("\n3) Test du jeton…")
    try:
        executer_claude("Réponds uniquement par le mot : OK")
    except ClaudeIndisponible as e:
        print(f"⛔ {e}")
        return 1

    print("✅ Jeton enregistré dans .env et fonctionnel.")
    print("   • Fais Cmd + K pour effacer le jeton de l'écran.")
    print("   • Sur https://claude.ai/settings/claude-code, révoque les anciens jetons (garde le plus récent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
