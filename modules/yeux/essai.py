"""Essai guidé, en vrai : le Terminal te dit quoi faire, puis vérifie que chaque étape a marché.

    python -m modules.yeux --essai              les 3 étapes
    python -m modules.yeux --essai --etape 2    une seule étape

1. le bouton « 👁 M'aider avec cet écran » sur un petit exercice ouvert dans TextEdit ;
2. une erreur laissée à l'écran → vérification automatique « puis-je aider ? » ;
3. « Couper l'écran », puis « Rallumer l'écran ».

Les deux textes d'essai sont des fichiers temporaires, effacés à la fin. Rien d'autre n'est créé.
"""

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from core import config, etat
from core.journal import FICHIER as JOURNAL
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
DELAIS = {"bouton": 180, "redaction": 180, "lecture": 300, "declencheur": 420, "ecran": 120}  # secondes d'attente au plus
DECLENCHEUR = re.compile(r"Déclencheur « erreur » \(TextEdit\) → Claude : (aide proposée|pas d'aide utile) \(confiance (\d+)\)")


def _ouvrir(texte: str, nom: str) -> Path:
    chemin = Path(tempfile.gettempdir()) / nom
    chemin.write_text(texte, encoding="utf-8")
    subprocess.run(["open", "-a", "TextEdit", str(chemin)], check=False)
    return chemin


def _appeler() -> None:
    """Un petit son, et le Terminal revient devant toi : impossible de rater le moment
    (même si macOS n'affiche pas les notifications)."""
    try:
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False, timeout=5)
    except Exception:
        pass
    appli = {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm"}.get(os.environ.get("TERM_PROGRAM", ""))
    if appli:
        subprocess.run(["open", "-a", appli], check=False)


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


def _fenetre_ouverte(id_aide: int, debut: float) -> bool:
    """L'icône marque une aide « vue » quand elle ouvre sa fenêtre."""
    return bool(_attendre(lambda: next((x["vue"] for x in etat.aides_recentes(debut) if x["id"] == id_aide), 0), 15, 1))


def _icone_affiche(signe: str, secondes: float = 10) -> tuple[bool, str]:
    """L'icône affiche-t-elle ce signe, à jour ? (ce qu'elle affiche est noté dans l'état toutes les 10 s)."""
    vu = {}

    def ok():
        vu["r"] = etat.resume()["icone_vue"]
        return vu["r"] is not None and vu["r"][0] < 15 and signe in vu["r"][1]

    if _attendre(ok, secondes, 1):
        return True, vu["r"][1]
    r = vu.get("r")
    if etat.resume()["icone_fenetre"] is not None:
        return False, ("elle est figée par une fenêtre de l'Assistant restée ouverte (peut-être cachée derrière"
                       " tes autres fenêtres) : trouve-la et clique « Fermer »")
    return False, ("aucune nouvelle de l'icône" if r is None else
                   f"elle affiche « {r[1]} », mise à jour il y a {int(r[0])} s") + " : relance-la, python service.py installer"


def _fenetre_fermee(secondes: float) -> bool:
    """Tant qu'une fenêtre de l'Assistant est ouverte, l'icône est figée : on attend que tu la fermes."""
    return bool(_attendre(lambda: etat.resume()["icone_fenetre"] is None, secondes, 1))


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
    if r["icone_fenetre"] is not None:
        return ("une fenêtre de l'Assistant est restée ouverte (peut-être cachée derrière tes autres fenêtres) :"
                " trouve-la et clique « Fermer », puis relance l'essai")
    if r["icone_vue"] is None or r["icone_vue"][0] > 30:
        return "l'icône du haut de l'écran ne répond pas : python service.py installer"
    return None


def _vider_clavier() -> None:
    """Oublie ce qui a été tapé pendant l'attente : une touche en trop ne doit pas sauter une étape."""
    try:
        import termios

        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def _pret_a(actions: list[str]) -> None:
    print("   Ce que tu vas faire :")
    for numero, action in zip("①②③④⑤", actions):
        print(f"   {numero} {action}")
    _vider_clavier()
    input("   ➜ Appuie sur Entrée pour commencer… ")
    print("   (Ne tape plus rien ici : le Terminal voit tout seul ce qui se passe.)")


def _bouton(resultats: list) -> None:
    print("\n━━ 1/3 · Le bouton « M'aider avec cet écran » ━━")
    _pret_a(["Appuie sur Entrée : une fenêtre TextEdit s'ouvre avec un petit exercice de TVA.",
             "Tout en haut à droite de l'écran (près de l'heure), clique sur l'icône 🎙👁.",
             "Dans le menu qui s'ouvre, clique sur « 👁 M'aider avec cet écran ».",
             "Attends 10 à 30 s : une fenêtre s'ouvre avec l'aide de Claude. Lis-la, puis « Fermer »."])
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
        ouverte = _fenetre_ouverte(a["id"], debut)
        print("   ✅ Aide rédigée, et sa fenêtre s'est ouverte. Lis-la, puis clique « Fermer »." if ouverte
              else "   ⚠️  Aide rédigée, mais l'icône n'a pas ouvert sa fenêtre.")
        resultats.append(f"✅ 1. Bouton : écran lu ({a['titre']}), aide rédigée et ouverte" if ouverte
                         else f"⚠️ 1. Bouton : aide rédigée ({a['titre']}), mais fenêtre pas ouverte")
        if ouverte and not _fenetre_fermee(DELAIS["lecture"]):  # sinon l'icône reste figée pour la suite
            print("   ⚠️  La fenêtre de l'aide est toujours ouverte : ferme-la (« Fermer »), sinon l'icône reste figée.")
    else:
        raison = fini["texte"][:150] if fini else "pas de réponse à temps"
        print(f"   ❌ Pas d'aide : {raison}")
        resultats.append(f"❌ 1. Bouton : écran lu mais pas d'aide ({raison})")


def _declencheur(resultats: list) -> None:
    print("\n━━ 2/3 · Une erreur qui reste à l'écran ━━")
    _pret_a(["Appuie sur Entrée : TextEdit affiche une fausse erreur Python.",
             "Laisse cette fenêtre devant toi environ 4 minutes. Ne change pas de fenêtre ;\n"
             "     bouge juste la souris de temps en temps (sinon il te croit absent).",
             "Au bout de 3 à 4 min, un petit son retentit et ce Terminal revient devant toi :\n"
             "     il te dira alors exactement où cliquer pour lire l'aide de Claude."])
    debut, position = time.time(), _taille_journal()
    _ouvrir(ERREUR, "assistant-essai-erreur.txt")
    print(f"   J'attends le déclencheur ({DELAIS['declencheur'] // 60} min au plus)…")

    def vu():
        texte = _journal_depuis(position)
        if "ignoré : limite de vérifications" in texte:
            return ("limite", 0)
        m = DECLENCHEUR.search(texte)
        return (m.group(1), int(m.group(2))) if m else None

    _resultat_declencheur(_attendre(vu, DELAIS["declencheur"], 5), debut, resultats)
    _appeler()  # fin de l'étape : retour au Terminal, même sans notification


def _resultat_declencheur(r, debut: float, resultats: list) -> None:
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
    affiche, detail = _icone_affiche("💡")
    print(f"   ✅ L'icône affiche bien la 💡 (« {detail} »)." if affiche
          else f"   ⚠️  L'icône n'affiche pas la 💡 : {detail}.")
    position = _taille_journal()
    _appeler()
    print("\n   🔔 Ta 💡 est prête ! " + ("L'icône tout en haut à droite affiche maintenant 💡. " if affiche else "")
          + "Alors :")
    print("      1. clique sur l'icône ;")
    print("      2. passe la souris (sans cliquer) sur « 💡 Aides (… à lire) » : une petite liste s'ouvre à côté ;")
    print(f"      3. clique sur la ligne « 💡 {titre} ».")
    print(f"   Claude rédige alors l'aide et sa fenêtre s'ouvre (10 à 30 s). J'attends ({DELAIS['redaction'] // 60} min au plus)…")
    fini = a and _attendre(lambda: next((x for x in etat.aides_recentes(debut) if x["id"] == a["id"]
                                         and x["statut"] in ("prete", "echec", "expiree")), None), DELAIS["redaction"])
    if fini and fini["statut"] == "prete":
        ouverte = _fenetre_ouverte(a["id"], debut)
        print("   ✅ Aide rédigée, et sa fenêtre s'est ouverte. Lis-la, puis clique « Fermer »." if ouverte
              else "   ⚠️  Aide rédigée, mais l'icône n'a pas ouvert sa fenêtre.")
        if ouverte and not _fenetre_fermee(DELAIS["lecture"]):
            print("   ⚠️  La fenêtre de l'aide est toujours ouverte : ferme-la (« Fermer »), sinon l'icône reste figée.")
        resultats.append(f"✅ 2. Erreur à l'écran : 💡 proposée (confiance {r[1]}), aide rédigée et ouverte" if ouverte
                         else f"⚠️ 2. Erreur à l'écran : 💡 proposée (confiance {r[1]}), aide rédigée, fenêtre pas ouverte")
    else:
        clic = "demandée depuis l'icône (💡)" in _journal_depuis(position)
        print("   ⚠️  Ton clic est bien arrivé à l'icône, mais l'aide n'a pas été rédigée à temps." if clic else
              "   ⚠️  L'icône n'a reçu aucun clic sur la ligne 💡 (dans « 💡 Aides »).")
        resultats.append(f"⚠️ 2. Erreur à l'écran : 💡 proposée (confiance {r[1]}), icône "
                         + ("avec 💡" if affiche else "SANS 💡") + (", clic reçu mais aide pas rédigée" if clic
                                                                     else ", aucun clic reçu"))


def _couper(resultats: list) -> None:
    print("\n━━ 3/3 · Couper et rallumer l'écran ━━")
    _pret_a(["Appuie sur Entrée.",
             "Clique sur l'icône 🎙👁, puis sur « 👁 Couper l'écran » : le 👁 disparaît de l'icône.",
             "Reclique sur l'icône, puis sur « 👁 Rallumer l'écran » : le 👁 revient."])
    coupe = _attendre(lambda: config.charger()["pause_ecran"] and _yeux_statut() != "actif", DELAIS["ecran"])
    if not coupe:
        print("   ❌ L'écran n'a pas été coupé.")
        resultats.append("❌ 3. Couper l'écran : pas vu")
        return
    print("   ✅ Écran coupé : le module yeux est arrêté, 👁 a disparu de l'icône.")
    rallume = _attendre(lambda: not config.charger()["pause_ecran"] and _yeux_statut() == "actif", DELAIS["ecran"])
    print("   ✅ Écran rallumé : 👁 est revenu." if rallume else "   ❌ L'écran n'a pas été rallumé.")
    resultats.append("✅ 3. Couper / rallumer l'écran" if rallume else "⚠️ 3. Écran coupé, mais pas rallumé")


def essai(etape: int | None = None) -> int:
    raison = _pas_pret()
    if raison:
        print(f"⛔ Avant l'essai : {raison}")
        return 1
    etapes = [(1, _bouton), (2, _declencheur), (3, _couper)]
    etapes = [e for e in etapes if etape is None or e[0] == etape]
    print("ESSAI GUIDÉ DES YEUX, en vrai : 3 étapes, environ 8 minutes, 2 à 4 appels à Claude." if etape is None
          else f"ESSAI GUIDÉ DES YEUX, en vrai : étape {etape} seulement.")
    print("On vérifie que : ① le bouton d'aide marche, ② l'Assistant remarque tout seul une erreur")
    print("qui reste affichée, ③ tu peux couper l'écran. Ctrl + C pour arrêter à tout moment.")
    resultats: list[str] = []
    try:
        for _, faire in etapes:
            faire(resultats)
    except KeyboardInterrupt:
        print("\nEssai interrompu.")
    finally:
        for nom in ("assistant-essai-exercice.txt", "assistant-essai-erreur.txt"):
            (Path(tempfile.gettempdir()) / nom).unlink(missing_ok=True)
    print("\n━━━━━━━━ RÉSULTAT DE L'ESSAI ━━━━━━━━")
    print("\n".join(resultats) or "(aucune étape terminée)")
    print("👉 Ferme maintenant les fenêtres TextEdit de l'essai (Cmd + W, puis « Ne pas enregistrer ») :")
    print("   sinon les yeux continuent de voir la fausse erreur. Les textes d'essai sont déjà effacés.")
    print("Colle ce résultat à Claude.")
    return 0 if resultats and all(r.startswith("✅") for r in resultats) else 1
