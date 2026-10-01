"""Essai guidé, en vrai : le Terminal te dit quoi faire, puis vérifie que chaque étape a marché.

    python -m modules.yeux --essai

1. le bouton « 👁 M'aider avec cet écran » sur un petit exercice ouvert dans TextEdit ;
2. une erreur laissée à l'écran → vérification automatique « puis-je aider ? » ;
3. « Couper l'écran », puis « Rallumer l'écran ».

Les deux textes d'essai sont des fichiers temporaires, effacés à la fin. Rien d'autre n'est créé.
"""

import re
import subprocess
import tempfile
import time
from pathlib import Path

from core import config, etat
from core.journal import FICHIER as JOURNAL
from core.notifications import notifier
from modules.yeux import parametres as p

EXERCICE = """Exercice (essai de l'Assistant)
Une facture de 1 200 € HT est soumise à une TVA de 20 %.
Quel est le montant TTC, et quelle écriture comptable faut-il passer ?
"""
ERREUR = """Traceback (most recent call last):
  File "analyse.py", line 3, in <module>
    import pandas
ModuleNotFoundError: No module named 'pandas'
"""
DELAIS = {"bouton": 180, "redaction": 180, "declencheur": 420, "ecran": 120}  # secondes d'attente au plus
DECLENCHEUR = re.compile(r"Déclencheur « erreur » \(TextEdit\) → Claude : (aide proposée|pas d'aide utile) \(confiance (\d+)\)")


def _ouvrir(texte: str, nom: str) -> Path:
    chemin = Path(tempfile.gettempdir()) / nom
    chemin.write_text(texte, encoding="utf-8")
    subprocess.run(["open", "-a", "TextEdit", str(chemin)], check=False)
    return chemin


def _attendre(condition, secondes: float, pas: float = 2):
    fin = time.time() + secondes
    while time.time() < fin:
        resultat = condition()
        if resultat:
            return resultat
        time.sleep(pas)
    return None


def _taille_journal() -> int:
    return JOURNAL.stat().st_size if JOURNAL.exists() else 0


def _journal_depuis(position: int) -> str:
    try:
        with open(JOURNAL, encoding="utf-8", errors="replace") as f:
            f.seek(position if JOURNAL.stat().st_size >= position else 0)  # le journal a pu être archivé
            return f.read()
    except OSError:
        return ""


def _yeux_statut() -> str | None:
    return next((m["statut"] for m in etat.modules() if m["nom"] == "yeux"), None)


def _pas_pret() -> str | None:
    r = etat.resume()
    if not r["superviseur_actif"]:
        return "le superviseur est arrêté : python service.py installer"
    if r["pause"]:
        return "tout est en pause : python assistant.py reprendre"
    if r["pause_ecran"]:
        return "l'écran est coupé : python assistant.py ecran on"
    if _yeux_statut() != "actif":
        return "le module yeux n'est pas actif : python assistant.py activer yeux"
    if p.mode() != "reel":
        return "les yeux sont en mode journal : python -m modules.yeux --mode reel"
    return None


def _pret_a(texte: str) -> None:
    input(f"\n{texte}\n   Appuie sur Entrée quand tu es prêt… ")


def _bouton(resultats: list) -> None:
    print("\n━━ 1/3 · Le bouton « M'aider avec cet écran » ━━")
    _pret_a("   Je vais ouvrir TextEdit avec un petit exercice.\n"
            "   Ensuite : clique l'icône 🎙👁 en haut à droite → « 👁 M'aider avec cet écran ».")
    debut = time.time()
    _ouvrir(EXERCICE, "assistant-essai-exercice.txt")
    print(f"   J'attends ton clic ({DELAIS['bouton'] // 60} min au plus)…")

    def demande():
        return next((a for a in etat.aides_recentes(debut) if a["module"] == "yeux" and a["titre"].startswith("Aide sur")
                     and a["statut"] != "a_capturer"), None)

    a = _attendre(demande, DELAIS["bouton"])
    if a is None:
        print("   ❌ Je n'ai vu aucune demande (as-tu cliqué « 👁 M'aider avec cet écran » ?)")
        resultats.append("❌ 1. Bouton : aucune demande vue")
        return
    print(f"   ✅ Écran lu : « {a['titre']} ». Claude rédige l'aide…")
    fini = _attendre(lambda: next((x for x in etat.aides_recentes(debut) if x["id"] == a["id"]
                                   and x["statut"] in ("prete", "echec", "expiree")), None), DELAIS["redaction"])
    if fini and fini["statut"] == "prete":
        print("   ✅ Aide rédigée : sa fenêtre a dû s'ouvrir toute seule.")
        resultats.append(f"✅ 1. Bouton : écran lu ({a['titre']}) et aide rédigée")
    else:
        raison = fini["texte"][:150] if fini else "pas de réponse à temps"
        print(f"   ❌ Pas d'aide : {raison}")
        resultats.append(f"❌ 1. Bouton : écran lu mais pas d'aide ({raison})")


def _declencheur(resultats: list) -> None:
    print("\n━━ 2/3 · Une erreur qui reste à l'écran ━━")
    _pret_a("   Je vais ouvrir TextEdit avec une erreur Python.\n"
            "   Ensuite : laisse cette fenêtre DEVANT toi environ 4 minutes, en bougeant la souris de temps\n"
            "   en temps. Une notification te dira de revenir ici.")
    debut, position = time.time(), _taille_journal()
    _ouvrir(ERREUR, "assistant-essai-erreur.txt")
    print(f"   J'attends le déclencheur ({DELAIS['declencheur'] // 60} min au plus)…")

    def vu():
        texte = _journal_depuis(position)
        if "ignoré : limite de vérifications" in texte:
            return ("limite", 0)
        m = DECLENCHEUR.search(texte)
        return (m.group(1), int(m.group(2))) if m else None

    r = _attendre(vu, DELAIS["declencheur"], 5)
    notifier("Assistant", "Essai : l'étape 2 est finie, reviens sur le Terminal.", module="essai", test=True)
    if r is None:
        print("   ❌ Aucun déclencheur vu. La fenêtre est-elle restée devant ? (5 min sans souris = « absent »)")
        resultats.append("❌ 2. Erreur à l'écran : aucun déclencheur")
        return
    if r[0] == "limite":
        print("   ⚠️  Limite de vérifications par heure atteinte : réessaie dans une heure.")
        resultats.append("⚠️ 2. Erreur à l'écran : limite de vérifications par heure atteinte")
        return
    if r[0] == "pas d'aide utile":
        print(f"   ✅ Déclencheur vu, Claude consulté : il a jugé ne pas pouvoir aider (confiance {r[1]}), donc pas de 💡.")
        resultats.append(f"✅ 2. Erreur à l'écran : déclencheur vu, Claude consulté (pas d'aide, confiance {r[1]})")
        return
    # Le journal est écrit juste avant que la 💡 soit enregistrée : on lui laisse un instant.
    a = _attendre(lambda: next((x for x in etat.aides_recentes(debut) if x["module"] == "yeux"
                                and x["statut"] != "a_capturer"), None), 30, 1)
    titre = a["titre"] if a else "?"
    print(f"   ✅ Déclencheur vu, Claude propose une aide (confiance {r[1]}) : « {titre} »")
    print("   → Clique l'icône, puis la ligne 💡 : Claude rédige l'aide (10 à 30 s).")
    fini = a and _attendre(lambda: next((x for x in etat.aides_recentes(debut) if x["id"] == a["id"]
                                         and x["statut"] in ("prete", "echec", "expiree")), None), DELAIS["redaction"])
    if fini and fini["statut"] == "prete":
        print("   ✅ Aide rédigée : sa fenêtre a dû s'ouvrir.")
        resultats.append(f"✅ 2. Erreur à l'écran : 💡 proposée (confiance {r[1]}) et aide rédigée")
    else:
        print("   ⚠️  L'aide n'a pas été rédigée (pas de clic sur 💡 ?)")
        resultats.append(f"⚠️ 2. Erreur à l'écran : 💡 proposée (confiance {r[1]}), mais aide pas ouverte")


def _couper(resultats: list) -> None:
    print("\n━━ 3/3 · Couper et rallumer l'écran ━━")
    print("   → Clique l'icône, puis « 👁 Couper l'écran ».")
    coupe = _attendre(lambda: config.charger()["pause_ecran"] and _yeux_statut() != "actif", DELAIS["ecran"])
    if not coupe:
        print("   ❌ L'écran n'a pas été coupé.")
        resultats.append("❌ 3. Couper l'écran : pas vu")
        return
    print("   ✅ Écran coupé : le module yeux est arrêté, 👁 a disparu de l'icône.")
    print("   → Maintenant « 👁 Rallumer l'écran ».")
    rallume = _attendre(lambda: not config.charger()["pause_ecran"] and _yeux_statut() == "actif", DELAIS["ecran"])
    print("   ✅ Écran rallumé : 👁 est revenu." if rallume else "   ❌ L'écran n'a pas été rallumé.")
    resultats.append("✅ 3. Couper / rallumer l'écran" if rallume else "⚠️ 3. Écran coupé, mais pas rallumé")


def essai() -> int:
    raison = _pas_pret()
    if raison:
        print(f"⛔ Avant l'essai : {raison}")
        return 1
    print("ESSAI GUIDÉ DES YEUX, en vrai (3 étapes, environ 8 minutes, 2 à 4 appels à Claude).")
    print("Ctrl + C pour arrêter à tout moment.")
    resultats: list[str] = []
    try:
        _bouton(resultats)
        _declencheur(resultats)
        _couper(resultats)
    except KeyboardInterrupt:
        print("\nEssai interrompu.")
    finally:
        for nom in ("assistant-essai-exercice.txt", "assistant-essai-erreur.txt"):
            (Path(tempfile.gettempdir()) / nom).unlink(missing_ok=True)
    print("\n━━━━━━━━ RÉSULTAT DE L'ESSAI ━━━━━━━━")
    print("\n".join(resultats) or "(aucune étape terminée)")
    print("Les textes d'essai sont effacés : ferme les fenêtres TextEdit sans enregistrer.")
    print("Colle ce résultat à Claude.")
    return 0 if resultats and all(r.startswith("✅") for r in resultats) else 1
