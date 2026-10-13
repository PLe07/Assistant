"""La liste blanche des intentions : tout ce que Voix sait faire, et rien d'autre.

Chaque intention a une famille (pour l'aide-mémoire), des exemples (aide-mémoire et suggestions), et deux drapeaux :
- `sensible` : passe **toujours** par une confirmation (« Tu confirmes ? », 5 s, sinon annulé) ;
- `reversible` : « annule » sait la défaire (volume, mode sombre, Wi-Fi, concentration, mode silencieux).
Les intentions de la famille « Refus » ne font rien : « Je ne fais pas ça, par sécurité. »
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Intention:
    ident: str
    famille: str
    titre: str
    exemples: tuple[str, ...]
    sensible: bool = False
    reversible: bool = False
    lecture_seule: bool = False  # ne change rien (heure, batterie, aide…)


FAMILLES = (
    "Apps",
    "Fichiers et dossiers",
    "Web",
    "Son et musique",
    "Système",
    "Concentration",
    "Minuteur et rappel",
    "Raccourcis Apple",
    "Routines",
    "Mes modules",
    "Contrôle",
    "Refus",
)

_LISTE = [
    # --- Apps -------------------------------------------------------------------------------------------------------
    Intention("app.ouvrir", "Apps", "Ouvrir une app", ("ouvre Notion", "lance Spotify", "démarre Slack")),
    Intention("app.fermer", "Apps", "Fermer une app", ("ferme Notion", "quitte Spotify")),
    Intention("app.cacher", "Apps", "Cacher une app", ("cache Slack", "masque Discord")),
    Intention("app.afficher", "Apps", "Aller sur une app ouverte",
              ("va sur Safari", "passe sur Notes", "montre Slack")),
    Intention("app.cacher_autres", "Apps", "Cacher toutes les autres apps", ("cache tout sauf Notion",)),
    Intention("app.fermer_tout", "Apps", "Fermer toutes les apps", ("ferme tout", "quitte toutes les apps"),
              sensible=True),
    Intention("app.fermer_tout_sauf", "Apps", "Fermer tout sauf une app", ("ferme tout sauf Safari",), sensible=True),
    # --- Fichiers et dossiers -----------------------------------------------------------------------------------------
    Intention("dossier.ouvrir", "Fichiers et dossiers", "Ouvrir un dossier",
              ("ouvre mes téléchargements", "ouvre le bureau", "ouvre le dossier Documents")),
    Intention("fichier.dernier_pdf", "Fichiers et dossiers", "Ouvrir ton dernier PDF", ("ouvre mon dernier PDF",)),
    Intention("fichier.dernier_telecharge", "Fichiers et dossiers", "Ouvrir le dernier fichier téléchargé",
              ("ouvre le dernier fichier téléchargé", "ouvre mon dernier téléchargement")),
    Intention("fichier.derniere_capture", "Fichiers et dossiers", "Ouvrir ta dernière capture d'écran",
              ("ouvre ma dernière capture d'écran",)),
    Intention("fichier.chercher", "Fichiers et dossiers", "Chercher un fichier (Spotlight)",
              ("cherche facture Fnac", "trouve le fichier contrat")),
    Intention("fichier.ouvrir_resultat", "Fichiers et dossiers", "Ouvrir un résultat de recherche",
              ("ouvre le 2", "ouvre le deuxième")),
    Intention("fichier.reveler_resultat", "Fichiers et dossiers", "Montrer un résultat dans le Finder",
              ("montre le 2 dans le Finder",)),
    Intention("alias.ouvrir", "Fichiers et dossiers", "Ouvrir un de tes alias", ("ouvre la compta",)),
    # --- Web ---------------------------------------------------------------------------------------------------------
    Intention("web.ouvrir_site", "Web", "Ouvrir un site", ("ouvre YouTube", "va sur Wikipédia")),
    Intention("web.chercher_google", "Web", "Chercher sur Google", ("cherche sur Google recette de crêpes",)),
    Intention("web.chercher_youtube", "Web", "Chercher sur YouTube", ("cherche sur YouTube concert de jazz",)),
    Intention("web.chercher_wikipedia", "Web", "Chercher sur Wikipédia", ("cherche Victor Hugo sur Wikipédia",)),
    Intention("web.chercher_plans", "Web", "Chercher un lieu sur Plans", ("montre la tour Eiffel sur Plans",
                                                                        "itinéraire vers la gare")),
    Intention("web.traduire", "Web", "Traduire un texte", ("traduis bonjour en anglais",)),
    # --- Son et musique ---------------------------------------------------------------------------------------------
    Intention("son.monter", "Son et musique", "Monter le son", ("monte le son", "plus fort"), reversible=True),
    Intention("son.baisser", "Son et musique", "Baisser le son", ("baisse le son", "moins fort"), reversible=True),
    Intention("son.couper", "Son et musique", "Couper le son", ("coupe le son",), reversible=True),
    Intention("son.remettre", "Son et musique", "Remettre le son", ("remets le son",), reversible=True),
    Intention("son.regler", "Son et musique", "Régler le volume", ("volume à 30 %", "mets le son à 50"),
              reversible=True),
    Intention("son.niveau", "Son et musique", "Dire le volume", ("quel est le volume",), lecture_seule=True),
    Intention("musique.lecture", "Son et musique", "Lancer la musique", ("lecture", "joue de la musique")),
    Intention("musique.pause", "Son et musique", "Mettre la musique en pause", ("pause", "mets la musique en pause")),
    Intention("musique.suivant", "Son et musique", "Morceau suivant", ("suivant", "chanson suivante")),
    Intention("musique.precedent", "Son et musique", "Morceau précédent", ("précédent", "chanson précédente")),
    Intention("musique.titre", "Son et musique", "Dire le morceau en cours", ("c'est quoi cette chanson",),
              lecture_seule=True),
    Intention("musique.playlist", "Son et musique", "Lancer une playlist", ("lance la playlist Révisions",)),
    # --- Système ------------------------------------------------------------------------------------------------------
    Intention("systeme.verrouiller", "Système", "Verrouiller l'écran", ("verrouille l'écran",)),
    Intention("systeme.veille", "Système", "Mettre le Mac en veille", ("mets en veille",), sensible=True),
    Intention("systeme.ecran_eteindre", "Système", "Éteindre l'écran", ("éteins l'écran",)),
    Intention("systeme.mode_sombre", "Système", "Passer en mode sombre", ("passe en mode sombre",), reversible=True),
    Intention("systeme.mode_clair", "Système", "Passer en mode clair", ("passe en mode clair",), reversible=True),
    Intention("systeme.wifi_activer", "Système", "Activer le Wi-Fi", ("active le wifi",), reversible=True),
    Intention("systeme.wifi_desactiver", "Système", "Couper le Wi-Fi", ("coupe le wifi",), sensible=True,
              reversible=True),
    Intention("systeme.batterie", "Système", "État de la batterie", ("état de la batterie",), lecture_seule=True),
    Intention("systeme.heure", "Système", "Quelle heure est-il", ("quelle heure est-il",), lecture_seule=True),
    Intention("systeme.date", "Système", "Quel jour sommes-nous", ("quel jour sommes-nous",), lecture_seule=True),
    Intention("systeme.meteo", "Système", "La météo", ("quel temps fait-il", "la météo")),
    # --- Concentration -----------------------------------------------------------------------------------------------
    Intention("concentration.activer", "Concentration", "Activer la concentration",
              ("active la concentration", "mode ne pas déranger"), reversible=True),
    Intention("concentration.desactiver", "Concentration", "Désactiver la concentration",
              ("désactive la concentration",), reversible=True),
    # --- Minuteur et rappel -----------------------------------------------------------------------------------------
    Intention("minuteur.lancer", "Minuteur et rappel", "Lancer un minuteur",
              ("minuteur 10 minutes", "mets un minuteur de 5 minutes")),
    Intention("rappel.creer", "Minuteur et rappel", "Créer un rappel",
              ("rappelle-moi dans 20 minutes de sortir le linge", "rappelle-moi à 18 h d'appeler Paul")),
    Intention("minuteur.annuler", "Minuteur et rappel", "Annuler le minuteur", ("annule le minuteur",)),
    Intention("minuteur.restant", "Minuteur et rappel", "Temps restant", ("combien de temps reste-t-il",),
              lecture_seule=True),
    # --- Raccourcis Apple ------------------------------------------------------------------------------------------
    Intention("raccourci.lancer", "Raccourcis Apple", "Lancer un raccourci", ("lance le raccourci Envoyer au Mac",)),
    Intention("raccourci.lister", "Raccourcis Apple", "Lister tes raccourcis", ("quels sont mes raccourcis",),
              lecture_seule=True),
    # --- Routines -----------------------------------------------------------------------------------------------------
    Intention("routine.lancer", "Routines", "Lancer une routine", ("lance ma révision", "lance la routine matin")),
    # --- Mes modules ----------------------------------------------------------------------------------------------
    Intention("module.tableau_ouvrir", "Mes modules", "Ouvrir le Tableau de bord", ("ouvre le tableau de bord",)),
    Intention("module.tableau_etat", "Mes modules", "État de tes modules", ("comment vont mes modules",),
              lecture_seule=True),
    Intention("module.ambiance_mode", "Mes modules", "Changer le mode d'Ambiance", ("mode code", "mode concentration")),
    Intention("module.ambiance_mood", "Mes modules", "Nouveau mood d'Ambiance", ("nouveau mood",)),
    Intention("module.quotidien_menu", "Mes modules", "Le menu de la semaine", ("menu de la semaine",)),
    Intention("module.bouclier_presse_papiers", "Mes modules", "Vérifier le presse-papiers (Bouclier)",
              ("vérifie le presse-papiers",)),
    # --- Contrôle -------------------------------------------------------------------------------------------------
    Intention("controle.annuler", "Contrôle", "Annuler la dernière action", ("annule", "reviens en arrière")),
    Intention("controle.repeter", "Contrôle", "Répéter la dernière réponse", ("répète",), lecture_seule=True),
    Intention("controle.stop", "Contrôle", "Arrêter de parler", ("stop", "tais-toi")),
    Intention("controle.aide", "Contrôle", "Ce que tu peux dire", ("qu'est-ce que je peux dire ?", "aide"),
              lecture_seule=True),
    Intention("controle.silencieux", "Contrôle", "Mode silencieux (sans voix ni sons)", ("mode silencieux",),
              reversible=True),
    Intention("controle.parler", "Contrôle", "Réponses parlées", ("réponds à voix haute", "réactive la voix"),
              reversible=True),
    Intention("controle.pause", "Contrôle", "Mettre Voix en pause", ("mets-toi en pause", "arrête d'écouter")),
    Intention("controle.oui", "Contrôle", "Confirmer", ("oui", "je confirme")),
    Intention("controle.non", "Contrôle", "Refuser", ("non", "laisse tomber")),
    # --- Refus : non pris en charge, par choix ---------------------------------------------------------------------
    Intention("refus", "Refus", "Éteindre, redémarrer, supprimer, vider la Corbeille, envoyer, payer",
              ("éteins l'ordinateur", "supprime ce fichier", "envoie un message à Paul"), lecture_seule=True),
]  # fmt: skip

INTENTIONS: dict[str, Intention] = {i.ident: i for i in _LISTE}
SENSIBLES = frozenset(i.ident for i in _LISTE if i.sensible)
REVERSIBLES = frozenset(i.ident for i in _LISTE if i.reversible)


def par_famille() -> dict[str, list[Intention]]:
    groupes: dict[str, list[Intention]] = {f: [] for f in FAMILLES}
    for i in _LISTE:
        groupes[i.famille].append(i)
    return groupes
