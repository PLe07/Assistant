"""Les commandes de l'assistant (dans ~/Assistant, avec .venv activé) :

    python assistant.py pause           met TOUT en pause, tout de suite (micro et écran compris)
    python assistant.py reprendre       relance tout
    python assistant.py etat            qui tourne ? notifications et appels à Claude du jour
    python assistant.py journal         les 30 dernières lignes du journal
    python assistant.py test-notif      affiche une notification de test
    python assistant.py test-claude     un tout petit appel à Claude (modèles rapide et fort)
    python assistant.py test-plantage   fait planter le module « battement » une fois (test de relance)
"""

import argparse
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


def main() -> int:
    actions = {
        "pause": pause, "reprendre": reprendre, "etat": afficher_etat, "journal": journal,
        "test-notif": test_notif, "test-claude": test_claude, "test-plantage": test_plantage,
    }
    parser = argparse.ArgumentParser(description="Commandes de l'assistant")
    parser.add_argument("action", choices=actions)
    return actions[parser.parse_args().action]()


if __name__ == "__main__":
    sys.exit(main())
