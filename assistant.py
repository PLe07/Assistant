"""Les commandes de l'assistant (dans ~/Assistant, avec .venv activé) :

    python assistant.py pause           met TOUT en pause, tout de suite (micro et écran compris)
    python assistant.py reprendre       relance tout
    python assistant.py etat            qui tourne ? notifications et appels à Claude du jour
    python assistant.py journal         les 30 dernières lignes du journal
    python assistant.py test-notif      affiche une notification de test
    python assistant.py test-claude     un tout petit appel à Claude (modèles rapide et fort)
    python assistant.py test-plantage   fait planter le module « battement » une fois (test de relance)
    python assistant.py renouveler-jeton  nouveau jeton Claude (il dure 1 an), enregistré sans l'afficher
    python assistant.py activer mails     active un module (il démarre dans les 2 secondes)
    python assistant.py desactiver mails  désactive un module (il s'arrête dans les 2 secondes)
"""

import argparse
import os
import sys

from core import config, etat
from core.journal import dernieres_lignes

STATUTS = {"actif": "✅", "en pause": "⏸ ", "désactivé": "⚫", "relance": "⚠️ ", "introuvable": "⛔", "démarrage": "…"}


def pause() -> int:
    config.mettre_en_pause(True)
    print("⏸  Tout est en pause : les modules s'arrêtent dans les 2 secondes.")
    return 0


def reprendre() -> int:
    config.mettre_en_pause(False)
    print("▶️  Relancé : les modules activés redémarrent dans les 2 secondes.")
    return 0


def afficher_etat() -> int:
    r = etat.resume()
    print(f"{r['icone']}  Superviseur : {'actif' if r['superviseur_actif'] else 'ARRÊTÉ (python superviseur.py)'}"
          + ("  ·  EN PAUSE (python assistant.py reprendre)" if r["pause"] else ""))
    print(f"   Proactivité : {r['proactivite']} ({config.NIVEAUX_PROACTIVITE[r['proactivite']]})")
    if r["modules"]:
        print("\nModules")
        for m in r["modules"]:
            detail = f" · {m['detail']}" if m["detail"] else ""
            print(f"   {STATUTS.get(m['statut'], '?')} {m['nom']} : {m['statut']}{detail}")
    envoyees, bloquees = r["notifications"]
    appels, plafond, entree, sortie = r["claude"]
    print("\nAujourd'hui")
    print(f"   Notifications : {envoyees} affichée(s), {bloquees} retenue(s) par le garde anti-spam")
    print(f"   Claude : {appels}/{plafond} appels · {entree:,} tokens lus · {sortie:,} écrits".replace(",", " "))
    _, erreurs = config.charger_avec_erreurs()
    for e in erreurs:
        print(f"⚠️  Réglage : {e}")
    return 0


def journal() -> int:
    print("\n".join(dernieres_lignes(30)) or "Le journal est encore vide.")
    return 0


def test_notif() -> int:
    from core.notifications import notifier

    affichee, raison = notifier("Assistant", "Notification de test ✅ : le socle fonctionne.", test=True)
    print("✅ Notification affichée." if affichee else f"⛔ Notification non affichée : {raison}")
    return 0 if affichee else 1


def test_claude() -> int:
    from core.cerveau import ClaudeIndisponible, demander

    code = 0
    for modele in ("rapide", "fort"):
        nom = config.charger()["claude"][f"modele_{modele}"]
        try:
            r = demander("Réponds uniquement par le mot : OK", module="test", modele=modele)
            print(f"✅ Modèle {modele} ({nom}) : « {r.texte.strip()} » · {r.tokens_entree} tokens lus, {r.tokens_sortie} écrits")
        except ClaudeIndisponible as e:
            print(f"⛔ Modèle {modele} ({nom}) : {e}")
            code = 1
    return code


def test_plantage() -> int:
    from modules.battement import CLE_PLANTAGE

    etat.ecrire(CLE_PLANTAGE, 1)
    print("💥 Demande envoyée : « battement » va planter dans la seconde.")
    print("   Le superviseur doit le relancer tout seul après 1 minute : python assistant.py etat")
    return 0


def _enregistrer_jeton(jeton: str) -> None:
    env = config.RACINE / ".env"
    lignes = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    lignes = [l for l in lignes if not l.startswith("CLAUDE_CODE_OAUTH_TOKEN=")]
    lignes.append(f"CLAUDE_CODE_OAUTH_TOKEN={jeton}")
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")
    os.chmod(env, 0o600)  # lisible par toi seul, même si le fichier existait déjà


def renouveler_jeton() -> int:
    import getpass
    import subprocess

    from core.cerveau import ClaudeIndisponible, binaire_claude, demander

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
        if jeton.startswith("sk-ant-oat01-") and len(jeton) > 60:
            break
        print("   ⛔ Ce n'est pas un jeton sk-ant-oat01-… : réessaie.")
    else:
        return 1
    _enregistrer_jeton(jeton)
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = jeton
    etat.effacer("claude_pause_jusqua")  # l'ancien jeton avait peut-être mis Claude en pause
    print("\n3) Test du jeton…")
    try:
        demander("Réponds uniquement par le mot : OK", module="test", modele="rapide")
    except ClaudeIndisponible as e:
        print(f"⛔ {e}")
        return 1
    print("✅ Jeton enregistré dans .env et fonctionnel.")
    print("   • Fais Cmd + K pour effacer le jeton de l'écran.")
    print("   • Sur https://claude.ai/settings/claude-code, révoque les anciens jetons (garde le plus récent).")
    print("   • Pour que le superviseur l'utilise : python service.py redemarrer")
    return 0


def _module_existe(nom: str) -> bool:
    dossier = config.RACINE / "modules"
    return (dossier / f"{nom}.py").exists() or (dossier / nom / "__main__.py").exists()


def changer_module(nom: str | None, actif: bool) -> int:
    if not nom:
        print("Précise le module, par exemple :  python assistant.py activer mails")
        return 2
    if actif and not _module_existe(nom):
        print(f"⛔ Module « {nom} » introuvable dans modules/.")
        return 1
    config.activer_module(nom, actif)
    print(f"✅ Module « {nom} » {'activé : il démarre' if actif else 'désactivé : il s’arrête'} dans les 2 secondes"
          + (" (sauf pause globale)." if actif else "."))
    return 0


def main() -> int:
    actions = {
        "pause": pause, "reprendre": reprendre, "etat": afficher_etat, "journal": journal,
        "test-notif": test_notif, "test-claude": test_claude, "test-plantage": test_plantage,
        "renouveler-jeton": renouveler_jeton,
    }
    parser = argparse.ArgumentParser(description="Commandes de l'assistant")
    parser.add_argument("action", choices=[*actions, "activer", "desactiver"])
    parser.add_argument("module", nargs="?", help="pour activer / desactiver : le nom du module")
    args = parser.parse_args()
    if args.action in ("activer", "desactiver"):
        return changer_module(args.module, args.action == "activer")
    return actions[args.action]()


if __name__ == "__main__":
    sys.exit(main())
