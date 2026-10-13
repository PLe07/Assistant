"""Deuxième jeu de phrases (§9.1), écrit **après** le premier réglage de la grammaire, avec des tournures qui n'avaient
pas servi à régler. Son premier passage (70,6 % d'intentions justes) est consigné dans DECISIONS D-13 ; il sert
depuis au réglage, comme les jeux suivants.

Les tournures sont celles qu'on dit vraiment à un assistant (« allez hop », « un chouïa », « tu me mets… »), avec les
apps, sites et dossiers du catalogue de référence, tirés avec une autre graine.
"""

from __future__ import annotations

import random

from outils import catalogue_reference as ref
from outils.corpus_phrases import Cas, en_lettres

GRAINE = 77

APPS_OUVRIR = [
    "tu me lances {x}", "allez hop ouvre {x}", "j'ai besoin de {x}", "ouvre-moi vite {x}", "fais démarrer {x}",
    "lance-moi {x} s'il te plaît", "peux-tu me lancer {x}", "il me faut {x}, ouvre-le", "vas-y lance {x}",
    "ouvre donc {x}", "démarre-moi {x}", "on ouvre {x}",
]  # fmt: skip
APPS_FERMER = ["ferme-moi {x}", "tu peux fermer {x}", "quitte {x} s'il te plaît", "allez ferme {x}", "on quitte {x}",
               "ferme donc {x}", "fermer {x} merci"]  # fmt: skip
APPS_AFFICHER = ["remets-moi sur {x}", "passe-moi sur {x}", "retourne sur {x}", "bascule vers {x}", "reviens à {x}"]
APPS_CACHER = ["cache-moi {x}", "planque {x}", "masque l'app {x}"]
SITES = ["va sur le site de {x}", "ouvre le site {x} dans le navigateur", "emmène-moi sur {x}", "affiche-moi {x}",
         "je veux aller sur {x}", "ouvre {x} sur internet"]  # fmt: skip
DOSSIERS = ["ouvre-moi le dossier {x}", "affiche le dossier {x}", "montre mon dossier {x}", "va dans mes {x}",
            "ouvre le répertoire {x}"]  # fmt: skip


def generer() -> list[Cas]:
    r = random.Random(GRAINE)
    cat = ref.catalogue()
    apps = [o for o in cat.du_genre("app") if o.ident != "com.example.Inconnue"]
    sites = cat.du_genre("site")
    dossiers = [
        o for o in cat.du_genre("dossier") if o.ident in ("~/Downloads", "~/Desktop", "~/Documents", "~/Pictures")
    ]
    cas: list[Cas] = []

    def dit(o: object) -> str:
        formes = list(o.formes)
        nom = o.nom
        return r.choice([nom, nom, *formes]) if "(" not in nom else r.choice(formes)

    for _ in range(60):
        o = r.choice(apps)
        cas.append(Cas(r.choice(APPS_OUVRIR).format(x=dit(o)), "app.ouvrir", {"objet": o.ident}))
    for _ in range(30):
        o = r.choice(apps)
        cas.append(Cas(r.choice(APPS_FERMER).format(x=dit(o)), "app.fermer", {"objet": o.ident}))
    for _ in range(15):
        o = r.choice(apps)
        cas.append(Cas(r.choice(APPS_AFFICHER).format(x=dit(o)), "app.afficher", {"objet": o.ident}))
    for _ in range(10):
        o = r.choice(apps)
        cas.append(Cas(r.choice(APPS_CACHER).format(x=dit(o)), "app.cacher", {"objet": o.ident}))
    for _ in range(35):
        o = r.choice(sites)
        cas.append(Cas(r.choice(SITES).format(x=dit(o)), "web.ouvrir_site", {"objet": o.ident}))
    for _ in range(15):
        o = r.choice(dossiers)
        mot = {"~/Downloads": "téléchargements", "~/Desktop": "bureau", "~/Documents": "documents",
               "~/Pictures": "images"}[o.ident]  # fmt: skip
        cas.append(Cas(r.choice(DOSSIERS).format(x=mot), "dossier.ouvrir", {"objet": o.ident}))
    for _ in range(30):
        n = r.choice([10, 20, 25, 35, 40, 55, 65, 80, 85, 100])
        dit_n = str(n) if r.random() < 0.5 else en_lettres(n)
        modele = r.choice(["tu me mets le son à {n}", "on met le volume à {n} %", "le volume à {n} pour cent stp",
                           "règle le son à {n}", "je veux le volume à {n}", "volume {n} pour cent"])  # fmt: skip
        cas.append(Cas(modele.format(n=dit_n), "son.regler", {"niveau": n}))
    fixes: list[tuple[str, str, dict[str, object]]] = [
        ("monte un chouïa le son", "son.monter", {}), ("plus fort s'il te plaît", "son.monter", {}),
        ("augmente un peu la musique", "son.monter", {"pas": 5}), ("monte le volume de 30", "son.monter", {"pas": 30}),
        ("baisse un peu la musique", "son.baisser", {"pas": 5}), ("moins fort stp", "son.baisser", {}),
        ("baisse le volume de quinze", "son.baisser", {"pas": 15}), ("diminue un peu le son", "son.baisser", {"pas": 5}),
        ("coupe-moi le son", "son.couper", {}), ("mets le son en sourdine", "son.couper", {}),
        ("remets-moi le son", "son.remettre", {}), ("rallume le son", "son.remettre", {}),
        ("mets un peu de musique", "musique.lecture", {}), ("relance la musique", "musique.lecture", {}),
        ("remets la musique s'il te plaît", "musique.lecture", {}), ("joue de la musique", "musique.lecture", {}),
        ("mets la musique sur pause", "musique.pause", {}), ("pause la chanson", "musique.pause", {}),
        ("stoppe la musique", "musique.pause", {}), ("passe la chanson", "musique.suivant", {}),
        ("au suivant", "musique.suivant", {}), ("piste suivante", "musique.suivant", {}),
        ("remets la chanson précédente", "musique.precedent", {}), ("morceau d'avant", "musique.precedent", {}),
        ("qu'est-ce qu'on écoute", "musique.titre", {}), ("c'est qui qui chante", "musique.titre", {}),
        ("verrouille-moi l'écran", "systeme.verrouiller", {}), ("bloque l'ordi", "systeme.verrouiller", {}),
        ("mets l'ordi en veille", "systeme.veille", {}), ("passe le Mac en veille", "systeme.veille", {}),
        ("éteins-moi l'écran", "systeme.ecran_eteindre", {}), ("coupe l'affichage", "systeme.ecran_eteindre", {}),
        ("bascule en mode sombre", "systeme.mode_sombre", {}), ("mets le thème sombre", "systeme.mode_sombre", {}),
        ("repasse en mode clair", "systeme.mode_clair", {}), ("enlève le mode sombre", "systeme.mode_clair", {}),
        ("remets le wifi", "systeme.wifi_activer", {}), ("rallume internet", "systeme.wifi_activer", {}),
        ("coupe internet", "systeme.wifi_desactiver", {}), ("déconnecte le wifi", "systeme.wifi_desactiver", {}),
        ("il me reste combien d'autonomie", "systeme.batterie", {}), ("le pourcentage de la batterie", "systeme.batterie", {}),
        ("t'as l'heure", "systeme.heure", {}), ("il est quelle heure là", "systeme.heure", {}),
        ("on est quelle date", "systeme.date", {}), ("c'est quel jour", "systeme.date", {}),
        ("est-ce qu'il va pleuvoir", "systeme.meteo", {}), ("donne-moi la météo", "systeme.meteo", {}),
        ("passe en mode focus", "concentration.activer", {}), ("je voudrais être tranquille", "concentration.activer", {}),
        ("active le mode ne plus déranger", "concentration.activer", {}),
        ("désactive le mode concentration", "concentration.desactiver", {}),
        ("sors du mode ne pas déranger", "concentration.desactiver", {}),
        ("lance un compte à rebours de 3 minutes", "minuteur.lancer", {"duree_s": 180}),
        ("programme un minuteur de vingt minutes", "minuteur.lancer", {"duree_s": 1200}),
        ("minuteur pour un quart d'heure", "minuteur.lancer", {"duree_s": 900}),
        ("chrono de 45 secondes", "minuteur.lancer", {"duree_s": 45}),
        ("mets un timer de 8 minutes", "minuteur.lancer", {"duree_s": 480}),
        ("alerte-moi dans 12 minutes", "minuteur.lancer", {"duree_s": 720}),
        ("fais-moi penser à rappeler Julie dans une heure", "rappel.creer", {"duree_s": 3600, "message": "rappeler Julie"}),
        ("rappelle-moi dans deux heures qu'il faut sortir le chien", "rappel.creer",
         {"duree_s": 7200, "message": "sortir le chien"}),
        ("rappelle-moi de prendre le pain dans 40 minutes", "rappel.creer", {"duree_s": 2400, "message": "prendre le pain"}),
        ("supprime le minuteur", "minuteur.annuler", {}), ("arrête le chrono", "minuteur.annuler", {}),
        ("il reste combien sur le minuteur", "minuteur.restant", {}), ("temps restant du minuteur", "minuteur.restant", {}),
        ("exécute le raccourci heure du café", "raccourci.lancer", {"objet": "raccourci:Heure du café"}),
        ("lance mon raccourci mode lecture", "raccourci.lancer", {"objet": "raccourci:Mode lecture"}),
        ("liste les raccourcis", "raccourci.lister", {}),
        ("on révise", "routine.lancer", {"objet": "révision"}),
        ("démarre la routine révision", "routine.lancer", {"objet": "révision"}),
        ("affiche-moi le tableau de bord", "module.tableau_ouvrir", {}), ("ouvre le dashboard", "module.tableau_ouvrir", {}),
        ("est-ce que les modules vont bien", "module.tableau_etat", {}),
        ("donne-moi le menu de cette semaine", "module.quotidien_menu", {}),
        ("on mange quoi cette semaine", "module.quotidien_menu", {}),
        ("analyse le message copié", "module.bouclier_presse_papiers", {}),
        ("est-ce que ce message est une arnaque", "module.bouclier_presse_papiers", {}),
        ("change le mood", "module.ambiance_mood", {}), ("une autre ambiance", "module.ambiance_mood", {}),
        ("ouvre-moi mon dernier PDF", "fichier.dernier_pdf", {}),
        ("ouvre le fichier que je viens de télécharger", "fichier.dernier_telecharge", {}),
        ("affiche ma dernière copie d'écran", "fichier.derniere_capture", {}),
        ("trouve-moi la facture EDF", "fichier.chercher", {"requete": "facture edf"}),
        ("cherche le document assurance auto", "fichier.chercher", {"requete": "assurance auto"}),
        ("où est le fichier budget", "fichier.chercher", {"requete": "budget"}),
        ("prends le troisième", "fichier.ouvrir_resultat", {"rang": 3}),
        ("ouvre le numéro 2", "fichier.ouvrir_resultat", {"rang": 2}),
        ("lance le premier résultat", "fichier.ouvrir_resultat", {"rang": 1}),
        ("google horaires de la poste", "web.chercher_google", {"requete": "horaires de la poste"}),
        ("fais une recherche google sur les éclipses", "web.chercher_google", {"requete": "les éclipses"}),
        ("cherche dans google comment planter des tomates", "web.chercher_google",
         {"requete": "comment planter des tomates"}),
        ("regarde un tuto de crochet sur YouTube", "web.chercher_youtube", {"requete": "un tuto de crochet"}),
        ("cherche des vidéos de chats sur YouTube", "web.chercher_youtube", {"requete": "des vidéos de chats"}),
        ("cherche Molière sur Wikipédia", "web.chercher_wikipedia", {"requete": "molière"}),
        ("emmène-moi à la gare Saint-Charles", "web.chercher_plans", {"requete": "la gare saint charles"}),
        ("trajet jusqu'à la plage", "web.chercher_plans", {"requete": "la plage"}),
        ("comment on dit fromage en anglais", "web.traduire", {"texte": "fromage", "langue": "en"}),
        ("traduis au revoir en italien", "web.traduire", {"texte": "au revoir", "langue": "it"}),
        ("ferme toutes les applis", "app.fermer_tout", {}), ("quitte toutes les applications", "app.fermer_tout", {}),
        ("ferme tout sauf Spotify", "app.fermer_tout_sauf", {"objet": "com.spotify.client"}),
        ("quitte tout à part Notion", "app.fermer_tout_sauf", {"objet": "notion.id"}),
        ("cache toutes les autres apps", "app.cacher_autres", {}),
        ("annule ce que tu viens de faire", "controle.annuler", {}), ("retourne en arrière", "controle.annuler", {}),
        ("t'as dit quoi", "controle.repeter", {}), ("répète encore", "controle.repeter", {}),
        ("tais-toi", "controle.stop", {}), ("c'est bon arrête", "controle.stop", {}),
        ("tu sais faire quoi", "controle.aide", {}), ("montre-moi l'aide-mémoire", "controle.aide", {}),
        ("passe en mode muet", "controle.silencieux", {}), ("coupe ta voix", "controle.silencieux", {}),
        ("tu peux parler", "controle.parler", {}), ("quitte le mode silencieux", "controle.parler", {}),
        ("arrête de m'écouter", "controle.pause", {}), ("fais une pause", "controle.pause", {}),
        ("oui oui", "controle.oui", {}), ("bien sûr", "controle.oui", {}), ("carrément", "controle.oui", {}),
        ("non non", "controle.non", {}), ("certainement pas", "controle.non", {}), ("pas maintenant", "controle.non", {}),
        ("éteins mon Mac", "refus", {}), ("supprime mes photos", "refus", {}), ("vide-moi la corbeille", "refus", {}),
        ("envoie un texto à Léa", "refus", {}), ("commande des sushis", "refus", {}), ("efface ce dossier", "refus", {}),
        ("redémarre le Mac s'il te plaît", "refus", {}), ("réponds à Paul que j'arrive", "refus", {}),
    ]  # fmt: skip
    for phrase, intention, params in fixes:
        statut = "refus" if intention == "refus" else "compris"
        cas.append(Cas(phrase, intention, dict(params), statut))
    # Bruit de transcription sur une partie : casse, ponctuation.
    for c in cas:
        if r.random() < 0.4:
            c.phrase = c.phrase[0].upper() + c.phrase[1:] + r.choice([".", " ?", " !"])
    return cas[:400] if len(cas) >= 400 else cas


HORS_CATALOGUE_2 = [
    "tu préfères les chats ou les chiens", "c'est l'heure de manger", "fais-moi rire", "j'ai mal à la tête",
    "le volume de la Seine augmente", "la musique adoucit les mœurs", "ouvre les yeux", "ferme les yeux",
    "lance-toi", "monte sur la table", "baisse la tête", "coupe la parole", "mets ta ceinture", "passe-moi le pain",
    "cache ta joie", "va voir ailleurs", "montre-moi le chemin de la sagesse", "cherche pas", "allume ta lampe",
    "éteins la télé du salon", "verrouille la porte de derrière", "règle tes comptes", "joue du piano",
    "ouvre la porte à Paul", "lance la balle au chien", "ouvre le livre page 12", "ferme la parenthèse",
    "quelle heure est-il à Tokyo", "quel temps fait-il à Rome demain", "mon wifi est lent", "le Mac chauffe",
    "j'ai oublié mon mot de passe", "Spotify a planté", "Notion ne s'ouvre plus", "YouTube est en panne",
    "le minuteur de la cuisine", "une demi-heure c'est long", "cent pour cent d'accord", "deux minutes papillon",
    "la routine c'est ennuyeux", "le raccourci par la forêt", "mon dossier médical", "les téléchargements illégaux",
    "le mode d'emploi", "le mode avion", "le mode tortue", "les apps c'est nul", "je déteste les lundis",
    "on va au cinéma ce soir", "rappelle-toi de moi",
]  # fmt: skip


def hors_catalogue() -> list[Cas]:
    return [Cas(p, None, statut="pas_compris") for p in HORS_CATALOGUE_2]
