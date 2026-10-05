"""Les commandes de l'assistant (dans ~/Assistant, avec .venv activé) :

    python assistant.py pause           met TOUT en pause, tout de suite (micro et écran compris)
    python assistant.py reprendre       relance tout
    python assistant.py etat            qui tourne ? notifications et appels à Claude du jour
    python assistant.py journal         les 30 dernières lignes du journal
    python assistant.py test-notif      affiche une notification de test
    python assistant.py test-claude     un tout petit appel à Claude (modèles rapide et fort)
    python assistant.py test-plantage   fait planter le module « battement » une fois (test de relance)
    python assistant.py renouveler-jeton  nouveau jeton Claude (il dure 1 an), enregistré sans l'afficher
    python assistant.py micro off         COUPE le micro tout de suite (micro on pour le rallumer)
    python assistant.py ecran off         COUPE l'écran tout de suite (ecran on pour le rallumer)
    python assistant.py traduction on     🇬🇧 chaque phrase française finie par un point devient anglaise (off : arrêter)
    python assistant.py corvees rapport   🔁 tes corvées répétées repérées (corvees seul : toutes ses commandes)
    python assistant.py demarrage rapport 🧹 ce qui se lance tout seul au démarrage, et ce que ça coûte
    python assistant.py activer mails     active un module (il démarre dans les 2 secondes)
    python assistant.py desactiver mails  désactive un module (il s'arrête dans les 2 secondes)
                                          (au bouton aussi : desactiver cine → son bouton ne fait plus rien)
    python assistant.py proactivite 2     0 muet · 1 discret · 2 normal · 3 présent (sans chiffre : le détail)

Mémoire, rappels, second cerveau (phase 4) :
    python assistant.py noter "…"         une note, un rappel (« rappelle-moi demain à 9 h de… ») ou une question
    python assistant.py demander "…"      une question à ton second cerveau (ta mémoire + Claude)
    python assistant.py memoire [mots]    cherche dans ta mémoire (sans mots : les derniers souvenirs)
    python assistant.py oublier 12        efface le souvenir n° 12 (oublier tout : TOUT effacer, avec confirmation)
    python assistant.py rappels [test|reel]  les derniers rappels ; passe en mode test ou réel
    python assistant.py habitudes         ce que l'Assistant a appris de tes habitudes (aucun contenu)
    python assistant.py essai-memoire     essai guidé, en vrai (--etape N pour une seule étape)

Coach DCG (phase 5), seulement quand tu le demandes :
    python assistant.py coach             choisis une UE et 3 à 10 questions, réponds ici, puis la correction
    python assistant.py coach cours       les cours trouvés, UE par UE (dossier donnees/coach/cours)
    python assistant.py coach bilan       tes progrès et tes points faibles

Veille patrimoine + DCG (phase 5), seulement quand tu la demandes :
    python assistant.py veille            lit les sites officiels, Claude choisit ce qui compte pour toi
    python assistant.py veille sources    vérifie que chaque site se lit bien (sans Claude, rien n'est gardé)
    python assistant.py veille page       ouvre la page de ta dernière veille (avec les liens)

Recherche sourcée (phase 5) :
    python assistant.py recherche "…"     Claude cherche sur le web : réponse en 5 lignes + sources vérifiées
    python assistant.py recherche page    la page de tes 20 dernières recherches (liens cliquables)

Rédacteur dans ta voix (phase 5) :
    python assistant.py rediger style     fait ta fiche de style (tes mails envoyés) + un échantillon
    python assistant.py rediger profil    ton profil pour les lettres de motivation (s'ouvre dans TextEdit)
    python assistant.py rediger "…"       un brouillon dans ton style (mail, lettre de motivation, post)

Brief du jour (phase 5), sans Claude :
    python assistant.py brief             ton agenda du jour, tes mails à traiter, tes rappels du jour

Concierge ciné (phase 5) :
    python assistant.py cine "envie de rire, 1h30"   3 films ou séries pour ce soir

Revue du dimanche (phase 5) :
    python assistant.py revue             le bilan de ta semaine : fait, appris, dépensé, à venir (+ le mot de Claude)
    python assistant.py revue derniere    relit la dernière revue (sans Claude)

Dépenses (phase 5) :
    python assistant.py depenses          le total du mois, par catégorie (depenses 2026-09 : un autre mois)
    python assistant.py depenses ajouter photo.jpg   ajoute un reçu (photo ou PDF)
    python assistant.py depenses test     mode test : rien n'est écrit (depenses reel : pour de vrai)
    python assistant.py depenses tableur  ouvre le tableur · depenses dossier : ouvre le dossier Reçus surveillé
"""

import argparse
import os
import sys
import time

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


MICRO_MUET = {  # pourquoi le micro ne transmet rien, d'après ce que macOS dit au module
    "refusee": "\n      → macOS REFUSE le micro à Python : Réglages Système → Confidentialité et sécurité → Micro",
    "restreinte": "\n      → macOS REFUSE le micro à Python : Réglages Système → Confidentialité et sécurité → Micro",
    "jamais_demandee": "\n      → Python n'a pas l'autorisation du micro : Réglages Système → Confidentialité et sécurité → Micro",
    "accordee": "\n      → macOS l'autorise : vérifie Réglages Système → Son → Entrée (le niveau doit bouger quand tu parles)",
    "inconnue": " (autorisation macOS ? micro changé ?)",
}


def afficher_etat() -> int:
    r = etat.resume()
    print(f"{r['icone']}  Superviseur : {'actif' if r['superviseur_actif'] else 'ARRÊTÉ (python superviseur.py)'}"
          + ("  ·  EN PAUSE (python assistant.py reprendre)" if r["pause"] else ""))
    print(f"   Proactivité : {r['proactivite']} ({config.NIVEAUX_PROACTIVITE[r['proactivite']]})")
    son, muet = r["micro_son"], r["micro_muet"]
    duree = "" if son is None else f"{int(son)} s" if son < 120 else f"{int(son // 60)} min"
    detail = ("" if not r["micro_actif"]
              else f" · ⚠️ AUCUN son reçu depuis {duree}" + MICRO_MUET.get(muet, MICRO_MUET["inconnue"]) if muet
              else " · démarrage…" if son is None
              else f" · son reçu il y a {int(son)} s" if son < 30
              else f" · ⚠️ AUCUN son reçu depuis {duree} (autorisation macOS ?)")
    ouvert = "ouvert" + (f" ({r['micro_nom']})" if r["micro_nom"] else " (écoute en cours)")
    print("   🎙 Micro : " + (ouvert if r["micro_actif"] else "coupé" if r["pause_micro"] else "fermé") + detail)
    vu, alerte = r["ecran_regard"], r["ecran_alerte"]
    detail = ("" if not r["ecran_actif"] else f" · mode {r['mode_yeux']}" + (
        " · ⚠️ PAS D'AUTORISATION macOS pour Python (Enregistrement de l'écran)" if alerte == "autorisation"
        else " · ⚠️ capture impossible (voir : python assistant.py journal)" if alerte == "capture"
        else " · aucun coup d'œil encore" if vu is None
        else f" · dernier coup d'œil il y a {int(vu)} s" if vu < 120
        else " · en veille (absent, écran verrouillé ou appli exclue)"))
    print("   👁 Écran : " + ("observé" if r["ecran_actif"] else "coupé" if r["pause_ecran"] else "non observé") + detail)
    allumee = config.charger()["modules"].get("traduction", {}).get("actif", False)
    if allumee or r["traduction_actif"]:
        from modules.traduction.traitement import compter

        alerte = r["traduction_alerte"]
        print("   🇬🇧 Traduction : " + (
            "⚠️ modèle à télécharger (python -m modules.traduction --telecharger)" if alerte == "modele"
            else "⚠️ autorisations macOS manquantes (python -m modules.traduction --diagnostic)" if alerte
            else f"allumée · {compter()} phrase(s) traduite(s) aujourd'hui" if r["traduction_actif"]
            else "allumée, démarrage…"))
    else:
        print("   🇬🇧 Traduction : éteinte (python assistant.py traduction on)")
    if config.module_actif("corvees"):
        try:
            from modules.corvees import daemon as corvees

            s = corvees.status()
            print("   🔁 Corvées : " + ("en pause" if s["pause"] else "observe" if s["vivant"] else "démarrage…")
                  + f" · {s['corvees']} repérée(s) (python assistant.py corvees rapport)")
        except Exception as e:
            print(f"   🔁 Corvées : ⚠️ {e}")
    if config.module_actif("demarrage"):
        try:
            from modules.demarrage import module as demarrage

            s = demarrage.status(time.time())
            age = f" (battement il y a {int(time.time() - float(s['battement']))} s)" if s["vivant"] else ""
            print("   🧹 Démarrage : " + ("surveille" + age if s["vivant"] else "démarrage…")
                  + f" · {s['sessions']} ouverture(s) mesurée(s) (python assistant.py demarrage rapport)")
        except Exception as e:
            print(f"   🧹 Démarrage : ⚠️ {e}")
    if r["aides"]:
        print(f"   💡 {len(r['aides'])} aide(s) t'attendent dans le menu de l'icône")
    vue = r["icone_vue"]
    if vue is not None and vue[0] <= 60:
        print(f"   Icône : affiche « {vue[1]} » (vérifié il y a {int(vue[0])} s)")
    elif vue is None and r["icone_fenetre"] is None:  # juste après « service.py installer » : elle démarre
        print("   Icône : pas encore de nouvelles (elle démarre ; si ça dure plus d'une minute : python service.py installer)")
    elif r["icone_fenetre"] is not None:
        print("   ⚠️  L'icône est figée : une fenêtre de l'Assistant est restée ouverte (peut-être cachée derrière"
              "\n       tes autres fenêtres). Trouve-la et clique « Fermer » : l'icône repart aussitôt.")
    else:
        print("   ⚠️  L'icône du haut de l'écran ne se met plus à jour" + (f" (depuis {int(vue[0] // 60)} min)" if vue else "")
              + " : python service.py installer")
    try:
        from core import memoire

        rp = r["rappels"]
        print(f"   🧠 Mémoire : {memoire.compter()} souvenir(s) · rappels en mode "
              + ("réel" if rp["mode"] == "reel" else "test (rien n'est créé)") + f", liste « {rp['liste']} »")
    except Exception as e:  # la mémoire ne doit jamais empêcher « etat » de répondre
        print(f"   🧠 Mémoire illisible : {e}")
    try:
        from modules.coach import seance

        if seance.derniere():
            print(f"   🎓 Coach : dernière séance le {seance.derniere()[:10]} · {seance.a_revoir()} question(s) à revoir")
    except Exception as e:
        print(f"   🎓 Coach illisible : {e}")
    try:
        from modules.veille import revue

        ligne = revue.resume_etat()
        if ligne:
            print(f"   📰 Veille : {ligne}")
    except Exception as e:
        print(f"   📰 Veille illisible : {e}")
    try:
        from modules.redacteur import style

        print(f"   ✒️ Rédacteur : {style.resume_etat()}")
    except Exception as e:
        print(f"   ✒️ Rédacteur illisible : {e}")
    try:
        from modules.depenses import recu

        print(f"   🧾 Dépenses : {recu.resume_etat()}")
    except Exception as e:
        print(f"   🧾 Dépenses illisibles : {e}")
    try:
        from modules.recherche import recherche as rech

        ligne = rech.resume_etat()
        if ligne:
            print(f"   🌐 Recherche : {ligne}")
    except Exception as e:
        print(f"   🌐 Recherche illisible : {e}")
    try:
        from modules.revue import revue as revue_semaine

        ligne = revue_semaine.resume_etat()
        if ligne:
            print(f"   🗓 Revue : {ligne}")
    except Exception as e:
        print(f"   🗓 Revue illisible : {e}")
    if r["modules"]:
        print("\nModules")
        for m in r["modules"]:
            detail = f" · {m['detail']}" if m["detail"] else ""
            print(f"   {STATUTS.get(m['statut'], '?')} {m['nom']} : {m['statut']}{detail}")
    print("\nAu bouton (seulement quand tu les demandes)\n   " + " · ".join(
        f"{'✅' if config.module_actif(nom) else '⚫'} {nom}" for nom in config.AU_BOUTON))
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
    if not affichee:
        print(f"⛔ Notification non envoyée : {raison}")
        return 1
    print("📨 Notification envoyée à macOS : elle doit apparaître en haut à droite d'ici 2 secondes.")
    print("   Rien ne s'affiche ? macOS la bloque (c'est « Éditeur de script » qui l'affiche pour l'Assistant) :")
    print("   1. Réglages Système → Notifications → « Éditeur de script » → active « Autoriser les notifications »")
    print("      et choisis le style « Bannières » (ou « Alertes »).")
    print("   2. Pas d'« Éditeur de script » dans la liste ? Ouvre l'app Éditeur de script (Applications → Utilitaires),")
    print("      tape  display notification \"test\"  puis clique ▶ : accepte la demande de macOS.")
    print("   3. Vérifie que « Ne pas déranger » (Centre de contrôle → Concentration) est désactivé.")
    return 0


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


def ecran(valeur: str | None) -> int:
    if valeur not in ("on", "off"):
        print("Utilise :  python assistant.py ecran off  (couper)  ou  ecran on  (rallumer)")
        return 2
    config.mettre_capteur_en_pause("ecran", valeur == "off")
    print("👁  Écran coupé : plus aucun coup d'œil dans les 2 secondes." if valeur == "off"
          else "👁  Écran rallumé : l'observation reprend dans les 2 secondes (si le module yeux est activé).")
    return 0


def traduction(valeur: str | None) -> int:
    from modules.traduction import moteur

    if valeur not in ("on", "off"):
        print("Utilise :  python assistant.py traduction on  (allumer)  ou  traduction off  (éteindre)")
        return 2
    if valeur == "on" and not moteur.present():
        print("⛔ Le modèle de traduction n'est pas encore là (~1,3 Go, une fois) :  python -m modules.traduction --telecharger")
        return 1
    config.activer_module("traduction", valeur == "on")
    print("🇬🇧 Traduction allumée (dans les 2 secondes) : finis une phrase française par un point, elle devient anglaise."
          if valeur == "on" else "🇬🇧 Traduction éteinte : plus rien n'est traduit.")
    return 0


def micro(valeur: str | None) -> int:
    if valeur not in ("on", "off"):
        print("Utilise :  python assistant.py micro off  (couper)  ou  micro on  (rallumer)")
        return 2
    config.mettre_capteur_en_pause("micro", valeur == "off")
    print("🎙  Micro coupé : l'écoute s'arrête dans les 2 secondes." if valeur == "off"
          else "🎙  Micro rallumé : l'écoute reprend dans les 2 secondes (si le module oreilles est activé).")
    return 0


def _module_existe(nom: str) -> bool:
    dossier = config.RACINE / "modules"
    return (dossier / f"{nom}.py").exists() or (dossier / nom / "__main__.py").exists()


def changer_module(nom: str | None, actif: bool) -> int:
    if not nom:
        print("Précise le module, par exemple :  python assistant.py activer mails")
        return 2
    if nom in config.AU_BOUTON:  # ne tourne jamais en fond : son bouton, sa commande et la voix suivent ce réglage
        config.activer_module(nom, actif)
        print(f"✅ « {nom} » ({config.AU_BOUTON[nom]}) {'activé' if actif else 'désactivé'} : son bouton, sa commande "
              f"et la voix {'marchent' if actif else 'ne font plus rien'}, tout de suite.")
        return 0
    if actif and not _module_existe(nom):
        print(f"⛔ Module « {nom} » introuvable dans modules/.")
        return 1
    if not actif and not _module_existe(nom):  # un ancien module (ex. le coach, devenu un simple bouton)
        config.retirer_module(nom)
        print(f"✅ « {nom} » retiré des réglages : ce n'est plus un module qui tourne en fond.")
        return 0
    config.activer_module(nom, actif)
    print(f"✅ Module « {nom} » {'activé : il démarre' if actif else 'désactivé : il s’arrête'} dans les 2 secondes"
          + (" (sauf pause globale)." if actif else "."))
    return 0


# --- Mémoire, rappels, second cerveau ---------------------------------------------------------


def _date(quand: float) -> str:
    from datetime import datetime

    return f"{datetime.fromtimestamp(quand):%d/%m/%Y %H:%M}"


def _afficher_souvenir(x: dict) -> None:
    from core.memoire import GENRES

    print(f"  n° {x['id']} · {_date(x['quand'])} · {GENRES.get(x['genre'], '·')} {x['genre']} ({x['source']})")
    print(f"     {x['texte']}")
    if x["detail"]:
        detail = x["detail"] if len(x["detail"]) <= 400 else x["detail"][:400] + "…"
        print("     → " + detail.replace("\n", "\n       "))


def noter(texte: str | None) -> int:
    from core import consignes

    if not texte:
        print('Utilise :  python assistant.py noter "le code du portail est 1234"')
        return 2
    genre = consignes.classer(texte)
    if genre == "recherche":
        return recherche(texte)
    if genre == "redaction":
        return rediger(texte)
    if genre == "cine":
        return cine(texte)
    if genre in ("souvenir", "question"):
        return demander_memoire(texte)
    if genre == "rappel":
        print("⏰ Rappel : Claude comprend quoi et quand…")
        message = consignes.rappeler(texte, "terminal", notif=False)
        if message is not None:
            print(message)
            return 1 if message.startswith("⛔") else 0
        print("   (Claude n'y voit pas un rappel : je le garde comme note.)")
    print(consignes.noter(texte, "terminal", notif=False))
    return 0


def demander_memoire(question: str | None) -> int:
    from core import consignes

    if not question:
        print('Utilise :  python assistant.py demander "qu\'est-ce que j\'avais noté sur le dentiste ?"')
        return 2
    print("🧠 Je cherche dans ta mémoire…\n")
    print(consignes.repondre(question, "terminal"))
    return 0


def afficher_memoire(requete: str | None) -> int:
    from core import memoire

    total = memoire.compter()
    trouves = memoire.chercher(requete, 20) if requete else memoire.derniers(15)
    if requete:
        print(f"🔎 « {requete} » : {len(trouves)} souvenir(s) trouvé(s) sur {total}\n")
    else:
        print(f"🧠 Ta mémoire : {total} souvenir(s). Les plus récents :\n")
    for x in trouves:
        _afficher_souvenir(x)
    if not trouves:
        print("   (rien)" if requete else '   (vide : python assistant.py noter "…" pour commencer)')
    print("\nEffacer un souvenir :  python assistant.py oublier <n°>")
    return 0


def oublier(cible: str | None) -> int:
    from core import memoire

    if cible == "tout":
        n = memoire.compter()
        print(f"⚠️  Tu vas effacer TOUTE ta mémoire ({n} souvenirs) et tes habitudes. C'est irréversible.")
        if input("   Tape OUI (en majuscules) pour confirmer : ").strip() != "OUI":
            print("Annulé : rien n'a été effacé.")
            return 1
        print(f"🗑  Mémoire effacée ({memoire.oublier_tout()} souvenirs).")
        return 0
    if not cible or not cible.isdigit():
        print("Utilise :  python assistant.py oublier 12   (le n° vient de « python assistant.py memoire »)")
        return 2
    x = memoire.lire(int(cible))
    if x is None:
        print(f"Aucun souvenir n° {cible}.")
        return 1
    _afficher_souvenir(x)
    if input("   Effacer ce souvenir ? Tape oui pour confirmer : ").strip().lower() != "oui":
        print("Annulé : rien n'a été effacé.")
        return 1
    memoire.oublier(x["id"])
    print(f"🗑  Souvenir n° {cible} effacé.")
    return 0


def rappels(mode: str | None) -> int:
    from core import memoire

    if mode in ("test", "reel"):
        config.changer_mode_rappels(mode)
        if mode == "test":
            print("🧪 Rappels en mode test : rien n'est créé, une notification dit ce qui l'aurait été.")
        else:
            liste = config.charger()["rappels"]["liste"]
            print(f"⏰ Rappels en mode réel : ils sont ajoutés à l'app Rappels (liste « {liste} », créée au besoin).")
            print("   La première fois, macOS demande : « Python souhaite contrôler Rappels » → clique « Autoriser ».")
            print("   (Depuis le Terminal, c'est « Terminal » qui le demande.)")
        return 0
    if mode is not None:
        print("Utilise :  python assistant.py rappels   (voir)  ·  rappels test  ·  rappels reel")
        return 2
    r = config.charger()["rappels"]
    print(f"⏰ Rappels : mode {'RÉEL (ajoutés à l’app Rappels)' if r['mode'] == 'reel' else 'TEST (rien n’est créé)'}"
          f" · liste « {r['liste']} »\n")
    derniers = [x for x in memoire.derniers(200) if x["genre"] == "rappel"][:10]
    for x in derniers:
        _afficher_souvenir(x)
    if not derniers:
        print('   Aucun rappel pour l\'instant. Essaie :  python assistant.py noter "rappelle-moi demain à 9 h de …"')
    return 0


def habitudes() -> int:
    import time
    from collections import Counter
    from datetime import datetime

    from core import memoire
    from core.memoire import GENRES

    h = memoire.habitudes(time.time() - 30 * 86400)
    print("Tes habitudes (30 derniers jours) · aucun contenu n'est gardé : seulement quand, où et quel type.\n")
    s = h["souvenirs"]
    print(f"Ce que tu lui as confié : {sum(s.values())} souvenir(s)"
          + (" (" + " · ".join(f"{GENRES.get(g, '·')} {n} {g}" for g, n in sorted(s.items())) + ")" if s else ""))
    it = h["intentions"]
    print(f"Ce que l'Assistant a remarqué ou fait pour toi : {len(it)} fois")
    if not it:
        print("   (rien encore : ça se remplit tout seul quand les oreilles et les yeux sont actifs)")
        return 0
    for source in ("oreilles", "yeux"):
        types = Counter(x["type"] for x in it if x["source"] == source)
        if types:
            print(f"   {'🎙' if source == 'oreilles' else '👁'} {source} : {sum(types.values())} ("
                  + ", ".join(f"{t} {n}" for t, n in types.most_common()) + ")")
    proposees = [x for x in it if x["decision"] in ("proposee", "demandee")]
    ouvertes = [x for x in proposees if x["ouverte"]]
    if proposees:
        print(f"   💡 proposées : {len(proposees)} · ouvertes : {len(ouvertes)} ({100 * len(ouvertes) // len(proposees)} %)")
        jamais = [t for t, n in Counter(x["type"] for x in proposees).items()
                  if n >= 3 and not any(x["ouverte"] for x in proposees if x["type"] == t)]
        if jamais:
            print(f"   Tu n'ouvres jamais les 💡 « {', '.join(jamais)} » : dis-le-moi si tu veux qu'il arrête de les proposer.")
    limites = sum(1 for x in it if x["decision"] == "limite")
    if limites:
        print(f"   Limite par heure atteinte {limites} fois (réglage : niveau_proactivite)")
    moments = Counter("matin (6 h-12 h)" if 6 <= d.hour < 12 else "après-midi (12 h-18 h)" if 12 <= d.hour < 18
                      else "soir (18 h-23 h)" if 18 <= d.hour < 23 else "nuit"
                      for d in (datetime.fromtimestamp(x["quand"]) for x in it))
    print("Tes moments : " + " · ".join(f"{m} {n}" for m, n in moments.most_common()))
    applis = Counter(x["appli"] for x in it if x["appli"])
    if applis:
        print("Tes applis : " + " · ".join(f"{a} {n}" for a, n in applis.most_common(6)))
    return 0


def coach(quoi: str | None) -> int:
    from modules.coach import terminal

    actions = {None: terminal.seance_terminal, "cours": terminal.afficher_cours, "bilan": terminal.afficher_bilan}
    if quoi not in actions:
        print("Utilise :  python assistant.py coach   (tes questions)  ·  coach cours  ·  coach bilan")
        return 2
    return actions[quoi]()


def veille(quoi: str | None) -> int:
    from modules.veille import terminal

    actions = {None: terminal.lancer, "sources": terminal.sources, "page": terminal.page}
    if quoi not in actions:
        print("Utilise :  python assistant.py veille   (quoi de neuf ?)  ·  veille sources  ·  veille page")
        return 2
    return actions[quoi]()


def recherche(question: str | None) -> int:
    from modules.recherche import terminal

    if not question:
        print('Utilise :  python assistant.py recherche "quel est le plafond du PEA ?"  ·  recherche page')
        return 2
    return terminal.page() if question == "page" else terminal.lancer(question)


def rediger(quoi: str | None) -> int:
    from modules.redacteur import terminal

    if not quoi:
        print('Utilise :  python assistant.py rediger style  ·  rediger profil  ·  rediger "mail à mon prof pour…"')
        return 2
    return {"style": terminal.faire_style, "profil": terminal.ouvrir_profil}.get(quoi, lambda: terminal.lancer(quoi))()


def depenses(suite: str | None) -> int:
    import re

    from modules.depenses import terminal

    mots = (suite or "").split(maxsplit=1)
    if not mots:
        return terminal.bilan()
    if mots[0] in ("test", "reel"):
        return terminal.changer_mode(mots[0])
    if mots[0] in ("tableur", "dossier"):
        return terminal.ouvrir(mots[0])
    if mots[0] == "ajouter" and len(mots) == 2:
        return terminal.ajouter([mots[1]])
    if re.fullmatch(r"\d{4}-\d{2}", mots[0]):
        return terminal.bilan(mots[0])
    print("Utilise :  python assistant.py depenses  ·  depenses ajouter <photo>  ·  depenses test|reel  ·  "
          "depenses tableur|dossier  ·  depenses 2026-09")
    return 2


def cine(demande: str | None) -> int:
    from modules.cine import terminal

    return terminal.lancer(demande)


def brief() -> int:
    from modules.brief import terminal

    return terminal.lancer()


def revue(suite: str | None) -> int:
    from modules.revue import terminal

    return terminal.lancer((suite or "").split())


def proactivite(niveau: str | None) -> int:
    from core.aides import SEUIL_CONFIANCE
    from core.notifications import LIMITE_PAR_HEURE

    if niveau is None:
        actuel = config.charger()["niveau_proactivite"]
        print("🔔 Proactivité : ce que l'Assistant ose faire de lui-même (quand TU demandes, il répond toujours).\n")
        for n, nom in config.NIVEAUX_PROACTIVITE.items():
            aide = f"te propose une 💡 si Claude est sûr à {SEUIL_CONFIANCE[n]} %" if SEUIL_CONFIANCE[n] else "aucune initiative"
            print(f"   {'→' if n == actuel else ' '} {n} · {nom:8} {aide} · {LIMITE_PAR_HEURE[n]} notification(s)/h au plus")
        print("\nPour changer :  python assistant.py proactivite 1   (ou icône → 🔔 Proactivité)")
        return 0
    if niveau not in ("0", "1", "2", "3"):
        print("⛔ Niveau 0, 1, 2 ou 3 attendu (0 muet · 1 discret · 2 normal · 3 présent).")
        return 2
    config.regler_proactivite(int(niveau))
    print(f"🔔 Proactivité : {niveau} ({config.NIVEAUX_PROACTIVITE[int(niveau)]}), pris en compte tout de suite.")
    return 0


# Les commandes des modules au bouton : désactivées dans reglages.json, elles le disent et s'arrêtent là.
AU_BOUTON_COMMANDES = {"coach": "coach", "veille": "veille", "recherche": "recherche", "rediger": "redacteur",
                       "brief": "brief", "cine": "cine", "revue": "revue"}


def _module_coupe(action: str) -> bool:
    nom = AU_BOUTON_COMMANDES.get(action)
    if nom and not config.module_actif(nom):
        print(f"⛔ Le module « {nom} » ({config.AU_BOUTON[nom]}) est désactivé dans tes réglages."
              f"\n   Pour le réactiver :  python assistant.py activer {nom}")
        return True
    return False


def essai_memoire(etape: int | None) -> int:
    from core.essai_memoire import essai

    return essai(etape)


def main() -> int:
    if sys.argv[1:2] == ["corvees"]:  # le détecteur a ses propres commandes (accept ID --installer…)
        from modules.corvees.cli import main as corvees

        return corvees(sys.argv[2:])
    if sys.argv[1:2] == ["demarrage"]:  # le Nettoyeur de démarrage a ses propres commandes (scan, mesurer…)
        from modules.demarrage.cli import main as demarrage

        return demarrage(sys.argv[2:])
    actions = {
        "pause": pause, "reprendre": reprendre, "etat": afficher_etat, "journal": journal,
        "test-notif": test_notif, "test-claude": test_claude, "test-plantage": test_plantage,
        "renouveler-jeton": renouveler_jeton, "brief": brief,
    }
    avec_texte = {"noter": noter, "demander": demander_memoire, "memoire": afficher_memoire, "oublier": oublier,
                  "rappels": rappels, "micro": micro, "ecran": ecran, "traduction": traduction, "coach": coach,
                  "veille": veille, "recherche": recherche, "rediger": rediger, "depenses": depenses,
                  "cine": cine, "revue": revue, "proactivite": proactivite}
    parser = argparse.ArgumentParser(description="Commandes de l'assistant")
    parser.add_argument("action", choices=[*actions, *avec_texte, "activer", "desactiver", "habitudes", "essai-memoire",
                                           "corvees", "demarrage"])
    parser.add_argument("suite", nargs="*", help="activer / desactiver : le module ; micro, ecran : on ou off ; "
                                                 "noter, demander, memoire, recherche, rediger : ton texte")
    parser.add_argument("--etape", type=int, choices=[1, 2, 3, 4, 5], help="essai-memoire : une seule étape")
    args = parser.parse_args()
    suite = " ".join(args.suite).strip() or None
    if _module_coupe(args.action):
        return 1
    if args.action in avec_texte:
        return avec_texte[args.action](suite)
    if args.action in ("activer", "desactiver"):
        return changer_module(suite, args.action == "activer")
    if args.action == "habitudes":
        return habitudes()
    if args.action == "essai-memoire":
        return essai_memoire(args.etape)
    return actions[args.action]()


if __name__ == "__main__":
    sys.exit(main())
