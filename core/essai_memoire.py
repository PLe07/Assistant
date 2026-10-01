"""Essai guidé de la phase 4, en vrai : le Terminal te dit quoi faire, puis vérifie que chaque étape a marché.

    python assistant.py essai-memoire              les 5 étapes (environ 6 minutes, 2 ou 3 appels à Claude)
    python assistant.py essai-memoire --etape 3    une seule étape

1. ✍️ noter une phrase depuis l'icône ;
2. 🔎 la retrouver ;
3. ⏰ un rappel en mode test (rien n'est créé dans l'app Rappels) ;
4. 🧠 une question à ton second cerveau ;
5. ⏰ un vrai rappel dans l'app Rappels (seulement si tu tapes « oui »).

Les souvenirs créés pendant l'essai restent dans ta mémoire (python assistant.py oublier <n°> pour les effacer).
"""

import re
import time

from core import config, etat, memoire
from core.essai import appeler, attendre, journal_depuis, pret_a, taille_journal, vider_clavier

DELAIS = {"saisie": 180, "reponse": 120, "lecture": 300}  # secondes d'attente au plus
NOTE = "Mon rendez-vous chez le dentiste est le 15 octobre à 14 h"
RAPPEL = "rappelle-moi demain à 9 h d'appeler la banque"
QUESTION = "qu'est-ce que j'avais noté sur le dentiste ?"
RAPPEL_REEL = "rappelle-moi dans 10 minutes de boire un verre d'eau"
ICONE = "Clique sur l'icône en haut à droite de l'écran, puis sur « ✍️ Noter ou demander… »."


def _nouveau(genre: str, debut: float, mot: str = "") -> dict | None:
    """Le souvenir de ce genre arrivé depuis le début de l'étape (et contenant ce mot)."""
    for x in memoire.derniers(30):
        if x["quand"] >= debut and x["genre"] == genre and mot.lower() in f"{x['texte']} {x['detail']}".lower():
            return x
    return None


def _fenetre_fermee() -> None:
    """Tant qu'une fenêtre de l'Assistant est ouverte, l'icône est figée : on attend que tu la fermes."""
    if not attendre(lambda: etat.resume()["icone_fenetre"] is None, DELAIS["lecture"], 1):
        print("   ⚠️  La fenêtre est toujours ouverte : ferme-la (« Fermer »), sinon l'icône reste figée.")


def _pas_pret() -> str | None:
    r = etat.resume()
    if r["pause"]:
        return "tout est en pause : python assistant.py reprendre"
    if r["icone_fenetre"] is not None:
        return ("une fenêtre de l'Assistant est restée ouverte (peut-être cachée derrière tes autres fenêtres) :"
                " trouve-la et clique « Fermer », puis relance l'essai")
    if not attendre(lambda: (etat.resume()["icone_vue"] or (99,))[0] < 30, 20, 1):  # elle vient peut-être de démarrer
        return "l'icône du haut de l'écran ne répond pas : python service.py installer"
    return None


def _noter(resultats: list) -> None:
    print("\n━━ 1/5 · Noter quelque chose ━━")
    print(f"   Le texte à taper (ou à copier-coller) :  {NOTE}")
    pret_a(["Appuie sur Entrée.", ICONE, "Tape le texte ci-dessus, puis clique « Envoyer ».",
            "Une notification « 📝 Noté dans ta mémoire » apparaît en haut à droite."])
    debut = time.time()
    print(f"   J'attends ta note ({DELAIS['saisie'] // 60} min au plus)…")
    x = attendre(lambda: _nouveau("note", debut, "dentiste"), DELAIS["saisie"])
    if x is None:
        print("   ❌ Aucune note reçue (as-tu cliqué « Envoyer » ?)")
        resultats.append("❌ 1. Noter : aucune note reçue")
        return
    print(f"   ✅ Notée dans ta mémoire (souvenir n° {x['id']}) : « {x['texte']} »")
    resultats.append(f"✅ 1. Noter : note n° {x['id']} gardée dans ta mémoire")


def _chercher(resultats: list) -> None:
    print("\n━━ 2/5 · La retrouver ━━")
    pret_a(["Appuie sur Entrée.", "Clique sur l'icône, puis sur « 🔎 Chercher dans ma mémoire… ».",
            "Tape :  dentiste   puis clique « Chercher ».",
            "Une fenêtre montre ce que ta mémoire contient sur le dentiste. Lis-la, puis « Fermer »."])
    position = taille_journal()
    print(f"   J'attends ta recherche ({DELAIS['saisie'] // 60} min au plus)…")
    m = attendre(lambda: re.search(r"Recherche dans la mémoire depuis l'icône \((\d+) résultat", journal_depuis(position)),
                 DELAIS["saisie"])
    if m is None:
        print("   ❌ Aucune recherche vue (as-tu cliqué « Chercher » ?)")
        resultats.append("❌ 2. Chercher : aucune recherche vue")
        return
    n = int(m[1])
    print(f"   ✅ Recherche faite sur ton Mac, sans Claude : {n} souvenir(s) trouvé(s)." if n
          else "   ⚠️  Recherche faite, mais rien trouvé (as-tu bien tapé « dentiste » ?)")
    resultats.append(f"✅ 2. Chercher : {n} souvenir(s) trouvé(s)" if n else "⚠️ 2. Chercher : rien trouvé")
    _fenetre_fermee()


def _rappel_test(resultats: list) -> None:
    print("\n━━ 3/5 · Un rappel, en mode test ━━")
    reel = config.charger()["rappels"]["mode"] == "reel"
    if reel:
        print("   (Les rappels sont déjà en mode réel : celui-ci sera VRAIMENT ajouté à l'app Rappels.)")
    print(f"   Le texte à taper :  {RAPPEL}")
    pret_a(["Appuie sur Entrée.", ICONE, "Tape le texte ci-dessus, puis clique « Envoyer ».",
            "10 à 20 s plus tard, une notification te dit ce que l'Assistant a compris"
            + ("." if reel else " :\n     « 🧪 Essai : j'aurais créé … » (rien n'est créé : mode test).")])
    debut = time.time()
    print(f"   J'attends ton rappel ({(DELAIS['saisie'] + DELAIS['reponse']) // 60} min au plus)…")
    x = attendre(lambda: _nouveau("rappel", debut), DELAIS["saisie"] + DELAIS["reponse"])
    if x is None:
        print("   ❌ Aucun rappel reçu (as-tu cliqué « Envoyer » ? sinon : python assistant.py journal)")
        resultats.append("❌ 3. Rappel (test) : aucun rappel reçu")
        return
    print(f"   ✅ Compris : « {x['texte']} » · {x['detail']}")
    bien = "demain" in x["detail"] and "09:00" in x["detail"]
    if not bien:
        print("   ⚠️  La date comprise n'est pas « demain à 09:00 » : dis-le-moi.")
    resultats.append(f"{'✅' if bien else '⚠️'} 3. Rappel (test) : « {x['texte']} » · {x['detail']}")


def _second_cerveau(resultats: list) -> None:
    print("\n━━ 4/5 · Une question à ton second cerveau ━━")
    print(f"   Le texte à taper :  {QUESTION}")
    pret_a(["Appuie sur Entrée.", ICONE, "Tape la question ci-dessus, puis clique « Envoyer ».",
            "10 à 30 s plus tard, la réponse s'ouvre toute seule dans une fenêtre. Lis-la, puis « Fermer »."])
    debut = time.time()
    print(f"   J'attends ta question ({(DELAIS['saisie'] + DELAIS['reponse']) // 60} min au plus)…")
    x = attendre(lambda: _nouveau("question", debut, "dentiste"), DELAIS["saisie"] + DELAIS["reponse"])
    if x is None:
        print("   ❌ Aucune réponse (as-tu cliqué « Envoyer » ? sinon : python assistant.py journal)")
        resultats.append("❌ 4. Second cerveau : aucune réponse")
        return
    reponse = " ".join(x["detail"].split())
    print(f"   ✅ Réponse : « {reponse[:200]}{'…' if len(reponse) > 200 else ''} »")
    ouverte = attendre(lambda: any(a["vue"] for a in etat.aides_recentes(debut) if a["module"] == "memoire"), 30, 1)
    cite = "15" in reponse
    print("   ✅ Sa fenêtre s'est ouverte." if ouverte else "   ⚠️  La réponse est prête, mais sa fenêtre ne s'est pas ouverte.")
    if not cite:
        print("   ⚠️  La réponse ne cite pas ta note (le 15 octobre) : dis-le-moi.")
    resultats.append(("✅" if ouverte and cite else "⚠️") + " 4. Second cerveau : réponse "
                     + ("qui cite ta note" if cite else "SANS ta note") + (", fenêtre ouverte" if ouverte else ", fenêtre PAS ouverte"))
    if ouverte:
        _fenetre_fermee()


def _rappel_reel(resultats: list) -> None:
    print("\n━━ 5/5 · Un VRAI rappel dans l'app Rappels ━━")
    liste = config.charger()["rappels"]["liste"]
    print("   Jusqu'ici, rien n'a été créé dans l'app Rappels (mode test). Cette étape passe les rappels")
    print(f"   en mode RÉEL : ils seront ajoutés à l'app Rappels, dans la liste « {liste} » (créée au besoin).")
    print("   L'Assistant ajoute des rappels ; il ne modifie ni n'efface jamais ceux qui existent.")
    print("   La première fois, macOS te demande : « Python souhaite contrôler Rappels » → clique « Autoriser ».")
    print("   (Pour revenir en mode test plus tard :  python assistant.py rappels test)")
    vider_clavier()
    if input("   ➜ Tape oui pour passer en mode réel (autre chose = passer cette étape) : ").strip().lower() != "oui":
        print("   ⏭  Étape passée : les rappels restent en mode test.")
        resultats.append("⏭ 5. Rappel réel : passé (rappels en mode test)")
        return
    config.changer_mode_rappels("reel")
    print(f"   ⏰ Rappels en mode réel.\n   Le texte à taper :  {RAPPEL_REEL}")
    pret_a(["Appuie sur Entrée.", ICONE, "Tape le texte ci-dessus, puis clique « Envoyer ».",
            "Si macOS demande l'autorisation de contrôler « Rappels » : clique « Autoriser ».",
            f"Une notification confirme : « ✅ Rappel créé dans « {liste} » … »."])
    debut = time.time()
    print(f"   J'attends ton rappel ({(DELAIS['saisie'] + DELAIS['reponse']) // 60} min au plus)…")
    x = attendre(lambda: _nouveau("rappel", debut), DELAIS["saisie"] + DELAIS["reponse"])
    appeler()
    if x is None:
        print("   ❌ Aucun rappel reçu (as-tu cliqué « Envoyer » ? sinon : python assistant.py journal)")
        resultats.append("❌ 5. Rappel réel : aucun rappel reçu")
    elif "créé dans Rappels" in x["detail"]:
        print(f"   ✅ Créé : « {x['texte']} » · {x['detail']}")
        print(f"   👉 Ouvre l'app Rappels : il est dans la liste « {liste} ».")
        resultats.append(f"✅ 5. Rappel réel : « {x['texte']} » créé dans « {liste} »")
    else:
        print(f"   ❌ {x['detail']}")
        resultats.append(f"❌ 5. Rappel réel : {x['detail'][:160]}")


def essai(etape: int | None = None) -> int:
    raison = _pas_pret()
    if raison:
        print(f"⛔ Avant l'essai : {raison}")
        return 1
    etapes = [(1, _noter), (2, _chercher), (3, _rappel_test), (4, _second_cerveau), (5, _rappel_reel)]
    etapes = [e for e in etapes if etape is None or e[0] == etape]
    print("ESSAI GUIDÉ DE LA MÉMOIRE, en vrai : 5 étapes, environ 6 minutes, 2 ou 3 appels à Claude." if etape is None
          else f"ESSAI GUIDÉ DE LA MÉMOIRE, en vrai : étape {etape} seulement.")
    print("Tout se fait depuis l'icône en haut à droite. Ctrl + C pour arrêter à tout moment.")
    resultats: list[str] = []
    try:
        for _, faire in etapes:
            faire(resultats)
    except KeyboardInterrupt:
        print("\nEssai interrompu.")
    print("\n━━━━━━━━ RÉSULTAT DE L'ESSAI ━━━━━━━━")
    print("\n".join(resultats) or "(aucune étape terminée)")
    print("Les souvenirs de l'essai restent dans ta mémoire :  python assistant.py memoire dentiste")
    print("(pour en effacer un :  python assistant.py oublier <n°>)")
    print("Colle ce résultat à Claude.")
    return 0 if resultats and all(r[0] in "✅⏭" for r in resultats) else 1
