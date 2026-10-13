"""La grammaire française de Voix : des verbes, des objets et des paramètres, reconnus sur la **phrase entière**.

Chaque règle est une expression sur le texte normalisé (minuscules, sans accents, nombres en chiffres, politesse
retirée) ; elle doit couvrir toute la phrase (jamais « un morceau qui ressemble »). Les règles sont essayées des
plus précises aux plus générales ; la première qui comprend gagne. Les objets (apps, dossiers, sites…) sont ensuite
cherchés dans le catalogue, par ressemblance (voir `comprendre`).
"""

from __future__ import annotations

import re

VERBES: dict[str, str] = {
    "OUVRIR": "ouvre ouvres ouvrent ouvrir ouvrez ouvrons regarde regarder rouvre rouvrir",
    "LANCER": "lance lances lancent lancer lancez lancons relance relancer",
    "DEMARRER": "demarre demarres demarrent demarrer demarrez",
    "FERMER": "ferme fermes ferment fermer fermez degage degager tue tuer vire virer",
    "QUITTER": "quitte quittes quittent quitter quittez",
    "CACHER": (
        "cache caches cachent cacher cachez masque masques masquent masquer masquez planque planques planquer "
        "reduis reduire reduisez minimise minimiser range ranger"
    ),
    "AFFICHER": (
        "affiche affiches affichent afficher affichez montre montres montrent montrer montrez voir ramene ramener"
    ),
    "MONTER": (
        "monte montes montent monter montez augmente augmentes augmentent augmenter augmentez remonte remonter "
        "pousse pousser"
    ),
    "BAISSER": (
        "baisse baisses baissent baisser baissez diminue diminues diminuent diminuer diminuez descends descend "
        "descendre redescends"
    ),
    "COUPER": "coupe coupes coupent couper coupez",
    "METTRE": "mets met mettent mettre mettez mais",
    "REMETTRE": "remets remet remettent remettre remettez",
    "REGLER": "regle regles reglent regler reglez",
    "ACTIVER": "active actives activent activer activez allume allumes allument allumer allumez",
    "DESACTIVER": "desactive desactives desactivent desactiver desactivez",
    "ETEINDRE": "eteins eteint eteignent eteindre eteignez",
    "CHERCHER": (
        "cherche cherches cherchent chercher cherchez recherche recherches recherchent rechercher recherchez "
        "trouve trouves trouvent trouver trouvez retrouve retrouves retrouver"
    ),
    "JOUER": "joue joues jouent jouer jouez reprends reprend reprendre reprenez",
    "ARRETER": "arrete arretes arretent arreter arretez stoppe stoppes stopper stoppez",
    "REPETER": "repete repetes repeter repetez redis redire",
    "ANNULER": "annule annules annulent annuler annulez defais defait defaire",
    "DECLENCHER": "declenche declenches declencher declenchez",
    "VERROUILLER": "verrouille verrouilles verrouiller verrouillez bloque bloques bloquer bloquez",
    "RAPPELER": "rappelle rappelles rappeler rappelez",
    "TRADUIRE": "traduis traduit traduire traduisez",
    "EXECUTER": "execute executes executer executez",
    "VERIFIER": "verifie verifies verifier verifiez analyse analyses analyser analysez",
    "PASSER": "passe passes passent passer passez",
}

_DET = (
    r"(?:le|la|les|l|un|une|des|du|de|d|mon|ma|mes|ton|ta|tes|son|sa|ses|notre|nos|votre|vos|ce|cet|cette|ces"
    r"|au|aux)"
)
MACROS = {
    "DET": _DET,
    "DETS": rf"(?:{_DET} )*",
    "MACHINE": r"(?:ordinateur|ordi|mac|macbook|machine|pc|systeme|imac)",
    "NOMBRE": r"\d{1,3}",
    "RANG": (
        r"\d{1,2}|premier|premiere|deuxieme|second|seconde|troisieme|quatrieme|cinquieme|sixieme|septieme"
        r"|huitieme|neuvieme|dixieme|dernier|derniere|1er|1re|1ere|2e|2eme|3e|3eme|4e|4eme|5e|5eme"
    ),
}


def developper(motif: str) -> str:
    """Remplace {OUVRIR}, {DET}… par leurs alternatives."""

    def verbe(m: re.Match[str]) -> str:
        nom = m.group(1)
        if nom in VERBES:
            return "(?:" + "|".join(sorted(VERBES[nom].split(), key=len, reverse=True)) + ")"
        return MACROS[nom]

    return re.sub(r"\{([A-Z]+)\}", verbe, motif)


def compiler(*motifs: str) -> list[re.Pattern[str]]:
    return [re.compile(developper(m)) for m in motifs]


# --- Oui / non (réponses à une confirmation ou une question) ---------------------------------------------------------
OUI = compiler(
    r"oui(?: oui)*|ouais|ouai|yes|ok|okay|d accord|daccord|vas y|ok vas y|confirme|je confirme|c est ca|"
    r"exactement|absolument|bien sur|carrement|affirmatif|go|valide|oui confirme|oui vas y|oui c est ca|"
    r"tout a fait|oui je confirme|c est bon|parfait|fais le|fait le"
)
NON = compiler(
    r"(?:non(?: non)*|nan) (?:merci|pas maintenant|plus tard|ca ira|c est bon|pas la peine|pas besoin|laisse)|"
    r"pas la peine|pas besoin|plus tard|ca ira|"
    r"(?:non )?ne fais rien|non(?: non)*|nan|no|non merci|surtout pas|pas du tout|laisse tomber|negatif|oublie|"
    r"oublie ca|"
    r"non laisse tomber|non annule|annule pas|pas maintenant|jamais de la vie|certainement pas|non c est pas ca|"
    r"ce n est pas ca|c est pas ca"
)

# --- Refus : non pris en charge, par sécurité (la phrase est reconnue, rien n'est fait) ------------------------------
REFUS = compiler(
    r"(?:{ETEINDRE}|{ARRETER}) (?:tout |completement )?(?:{DETS})?{MACHINE}(?: .*)?",
    r"(?:extinction|shutdown|shut down)(?: .*)?",
    r"(?:redemarre|redemarres|redemarrer|redemarrez|reboot|rebooter|relance|"
    r"relancer)(?: (?:{DETS})?{MACHINE}(?: .*)?)?",
    r"(?:supprime|supprimes|supprimer|supprimez|efface|effaces|effacer|effacez|detruis|detruire|jette|jeter|"
    r"elimine|eliminer|formate|formater)(?! (?:{DETS})?(?:minuteur|minuterie|timer|chrono|rappel)\b)(?: .*)?",
    r"(?:{METTRE}|deplace|envoie) .* (?:a|dans) (?:la )?(?:corbeille|poubelle)",
    r"(?:.* )?(?:vide|vides|vider|videz) (?:{DETS})?(?:corbeille|poubelle)(?: .*)?",
    r"(?:envoie|envoies|envoyer|envoyez|transfere|transferer|textote|whatsappe)(?: .*)?",
    r"(?:ecris|ecrire|ecrivez) (?:a |au |aux |un (?:message|mail|sms|texto|e mail|email)|une reponse)(?:.*)?",
    r"(?:reponds|repondre|repondez)(?! (?:a voix haute|a haute voix|oralement)$)(?: .*)?",
    r"(?:appelle|appeler|appelez|telephone a|telephoner a|facetime)(?! (?:moi|nous)\b)(?: .*)",
    r"(?:achete|acheter|achetez|paie|paye|payer|payez|commande|commander|commandez|reserve|reserver|reservez|"
    r"virement)(?: .*)?",
    r"(?:vire|virer|virez) (?:\d.*|de l argent .*|des sous .*|(?:a|au|aux|sur) .*)",
)

# --- Contrôle --------------------------------------------------------------------------------------------------------
CONTROLE: dict[str, list[re.Pattern[str]]] = {
    "minuteur.annuler": compiler(
        r"(?:{ANNULER}|{ARRETER}|stop|supprime|supprimer|enleve|enlever|{DESACTIVER}|{COUPER}) "
        r"(?:{DETS})?(?:minuteurs?|minuterie|timers?|chrono|chronometre|compte a rebours|rappels?|alarme)"
        r"(?: (?:de |d )?\d+ (?:minutes?|secondes?|heures?|min|h))?"
    ),
    "controle.pause": compiler(
        r"(?:mets|met|mettre) toi en (?:pause|veille)|pause voix|voix pause|{ARRETER} d ecouter|{ARRETER} de m ecouter|"
        r"ne m ecoute plus|n ecoute plus|n ecoute pas|ne m ecoute pas|{DESACTIVER} (?:les )?commandes vocales|"
        r"eteins toi|endors toi|va dormir|"
        r"(?:mets|met) voix en pause|fais une pause|arrete toi d ecouter"
    ),
    "controle.annuler": compiler(
        r"{ANNULER}(?: (?:ca|cela|la derniere action|la derniere commande|ce que tu viens de faire|ce que tu as fait|"
        r"tout))?",
        r"(?:reviens|retour|revenir|retourne) en arriere|undo|annulation",
    ),
    "controle.repeter": compiler(
        r"{REPETER}(?: (?:le|la|ca|cela|stp|la reponse|ce que tu as dit|encore|une fois|s il te plait|"
        r"(?:la|ta) derniere phrase|ta reponse))?",
        r"quoi|pardon|comment|tu as dit quoi|qu est ce que tu as dit|t as dit quoi|j ai pas compris|"
        r"je n ai pas compris|j ai pas entendu|je n ai pas entendu",
    ),
    "controle.silencieux": compiler(
        r"(?:(?:{ACTIVER}|{METTRE}|passe|passer) (?:en |le )?)?mode (?:silencieux|muet|discret|sans voix)",
        r"ne parle plus|{ARRETER} de parler|sans la voix|coupe ta voix|ne me reponds plus a voix haute|"
        r"(?:reponds|repondre) (?:sans parler|par ecrit|en silence|sans la voix)|(?:plus|pas) de voix|sans voix|"
        r"reste (?:silencieux|muet|discret|silencieuse|muette)",
    ),
    "controle.parler": compiler(
        r"(?:(?:{ACTIVER}|{METTRE}|passe|passer) (?:en |le )?)?mode (?:parle|vocal|voix)",
        r"(?:reponds|repondre) (?:a voix haute|a haute voix|oralement)|parle moi|reactive (?:la|ta) voix|"
        r"remets (?:la|ta) voix|(?:{DESACTIVER}|quitte|sors du) (?:le )?mode silencieux|tu peux parler|parler|parle|"
        r"(?:tu peux )?reparler|reparle(?: moi)?|(?:parle|parler) (?:moi )?(?:a nouveau|de nouveau)|"
        r"(?:{DESACTIVER}|quitte|sors du|enleve|retire|{ARRETER}) (?:le )?mode (?:silencieux|muet|discret)",
    ),
    "controle.stop": compiler(
        r"stop|stoppe|arrete|arrete toi|tais toi|chut|silence|ca suffit|assez|c est bon arrete|stop stop"
    ),
    "controle.aide": compiler(
        r"aide|aide moi|au secours|aide memoire|help|qu est ce que je peux dire|que puis je dire|"
        r"je peux (?:te )?dire quoi|je peux (?:te )?demander quoi|"
        r"qu est ce que je peux te dire|qu est ce que tu sais faire|qu est ce que tu peux faire|que sais tu faire|"
        r"tu sais faire quoi|tu fais quoi|quelles sont (?:les|tes) commandes|(?:la )?liste des commandes|"
        r"les commandes|qu est ce que je peux te demander|comment ca marche|montre moi (?:l )?aide memoire|"
        r"(?:{OUVRIR}|{AFFICHER}) (?:l )?aide memoire|qu est ce que tu comprends|a quoi tu sers|tu sers a quoi|"
        r"comment (?:on t utilise|je t utilise|t utiliser|ca s utilise|tu marches|tu fonctionnes)|"
        r"(?:{AFFICHER}|donne) (?:moi )?(?:les|tes) commandes|qu est ce que tu (?:peux|sais) faire(?: pour moi)?"
    ),
}

# --- Minuteur, rappel ------------------------------------------------------------------------------------------------
MINUTEUR = compiler(
    r"(?:(?:{METTRE}|{LANCER}|{DEMARRER}|{ACTIVER}|programme|programmer|{REGLER}|cree|creer|fais|fait) )?"
    r"(?:{DETS})?(?:minuteurs?|minuterie|timers?|chrono|chronometre|compte a rebours|alarme|pomodoro) "
    r"(?:de |d |pour |sur |dans |a )?(?P<duree>.+)",
    r"(?:previens moi|previens nous|alerte moi|dis moi quand ca fait|sonne|{RAPPELER} moi|me {RAPPELER}|"
    r"reveille moi|reveille nous|reveille) "
    r"(?:dans )?(?P<duree>.+)",
    r"(?P<duree>\d.*?) (?:de )?(?:minuteurs?|minuterie|timers?|chrono)",
)
RAPPEL = compiler(
    r"(?:{RAPPELER} (?:moi|nous)|(?:me|nous) {RAPPELER}|fais moi penser(?: a)?|n oublie pas de me rappeler|"
    r"previens moi|rappel|pense a me rappeler|(?:{METTRE}|cree|creer|programme|ajoute|fais) (?:moi )?(?:un )?rappel) "
    r"(?P<reste>.+)",
)
MINUTEUR_RESTANT = compiler(
    r"combien de temps (?:reste t il|il reste|reste il)(?: .*)?|il reste combien(?: de temps)?(?: .*)?|"
    r"ou en est (?:le|mon) (?:minuteur|timer|chrono|rappel)|temps restant|combien reste t il(?: .*)?|"
    r"reste combien(?: de temps)?|(?:le|mon) (?:minuteur|timer) en est ou|"
    r"temps restant (?:du|sur le|de mon|sur mon) (?:minuteur|timer|chrono)"
)

# --- Raccourcis Apple, routines --------------------------------------------------------------------------------------
RACCOURCI = compiler(
    r"(?:{LANCER}|{EXECUTER}|{DECLENCHER}|{DEMARRER}|{OUVRIR}|{ACTIVER}|utilise|fais|joue) (?:{DETS})?raccourcis? "
    r"(?:qui s appelle |nomme |intitule |appele )?(?P<objet>.+)",
    r"(?:{EXECUTER}|{DECLENCHER}) (?P<objet>.+)",
    r"raccourci (?P<objet>.+)",
)
RACCOURCI_LISTE = compiler(
    r"quels sont (?:mes|les) raccourcis|(?:liste|montre|affiche) (?:moi )?(?:mes|les) raccourcis(?: apple)?|"
    r"quels raccourcis (?:j ai|ai je|as tu)|mes raccourcis(?: apple)?|j ai quels raccourcis|"
    r"(?:{AFFICHER}|donne moi|dis moi) (?:la )?liste (?:des|de mes) raccourcis"
)
ROUTINE = compiler(
    r"(?:{LANCER}|{DEMARRER}|{ACTIVER}|fais|joue|commence) (?:{DETS})?routine (?P<objet>.+)",
    r"routine (?P<objet>.+)",
)

# --- Mes modules -----------------------------------------------------------------------------------------------------
TABLEAU_OUVRIR = compiler(
    r"(?:(?:{OUVRIR}|{AFFICHER}|{LANCER}|va sur|vas sur) (?:moi )?)?(?:{DETS})?(?:tableau de bord|dashboard)"
    r"(?: de mes modules| des modules)?"
)
TABLEAU_ETAT = compiler(
    r"comment (?:vont|va) (?:mes|les) modules|(?:l )?etat (?:des|de mes) modules|"
    r"(?:est ce que )?(?:mes|les) modules vont bien|tout va bien (?:sur|avec) mes modules|"
    r"(?:quel est l )?etat de l ecosysteme|comment va mon mac|"
    r"(?:est ce que )?tout (?:fonctionne|marche|va bien|tourne)(?: bien)?(?: (?:sur|avec|dans) (?:mes|les) modules)?"
)
AMBIANCE_MOOD = compiler(
    r"change (?:de|le) mood(?: de la soiree| pour ce soir| ce soir| pour la soiree)|"
    r"(?:un )?(?:nouveau|autre) mood|change (?:de|le) mood|(?:{METTRE}|lance) un (?:nouveau|autre) mood|"
    r"change (?:d|l) ambiance|(?:une )?nouvelle ambiance|(?:une )?autre ambiance|"
    r"(?:{METTRE}|lance) (?:une )?(?:nouvelle|autre) ambiance"
)
AMBIANCE_MODE = compiler(
    r"(?:(?:{METTRE}|passe|passer|{ACTIVER}|lance|bascule) (?:en |sur |le )?)?mode (?P<mode>[a-z]+)",
    r"ambiance (?P<mode>[a-z]+)",
)
_QUAND = r"(?: du jour| d aujourd hui| aujourd hui| de demain| demain| ce matin| ce midi| ce soir| cet apres midi)"
QUOTIDIEN_MENU = compiler(
    r"(?:(?:{OUVRIR}|{AFFICHER}|donne moi|dis moi) )?(?:{DETS})?menu(?: de la semaine| de cette semaine| du jour)?",
    rf"qu est ce qu on mange(?: cette semaine|{_QUAND})?|(?:on )?mange quoi(?: cette semaine|{_QUAND})?",
    rf"qu est ce qu il y a (?:au menu|a manger){_QUAND}?",
)
BOUCLIER = compiler(
    r"{VERIFIER} (?:{DETS})?(?:presse papiers?|message copie|texte copie|ce message|ce sms)",
    r"(?:est ce que c est|c est|est ce|est ce que ce message est) (?:une arnaque|du phishing|une escroquerie)"
    r"(?: (?:ce message|ce sms|ce mail|ce texte|ca))?(?: ou pas)?",
    r"(?:ce message|ce sms|ce mail|ce texte|ca) c est (?:une arnaque|du phishing|une escroquerie)(?: ou pas)?",
)

# --- Son et musique ----------------------------------------------------------------------------------------------
SON_REGLER = compiler(
    r"(?:(?:{METTRE}|{REGLER}|{MONTER}|{BAISSER}|{PASSER}|change|changer|ajuste|ajuster) )?(?:{DETS})?"
    r"(?:volume|son|niveau sonore|niveau du son) (?:a |au |sur |en )?(?P<n>{NOMBRE})(?: pourcent)?",
    r"(?P<n>{NOMBRE}) pourcent de (?:volume|son)",
)
SON_EXTREME = compiler(
    r"(?:(?:{METTRE}|{MONTER}|{BAISSER}|{REGLER}) )?(?:{DETS})?(?:volume|son|musique) "
    r"(?P<ou>a fond(?: la caisse)?|au maximum|au max|au minimum|au min|a la moitie|a moitie|a mi volume)",
)
SON_MONTER = compiler(
    r"{MONTER}(?: (?:{DETS})?(?:son|volume|musique))?(?: (?:de )?(?P<pas>{NOMBRE})(?: pourcent)?|"
    r" (?P<qte>encore un peu|un peu|"
    r"un petit peu|beaucoup|encore|un max|un bon coup))?",
    r"{MONTER} (?P<qte>un peu|un petit peu|beaucoup|encore|un chouia|un chouilla|un poil|legerement) "
    r"(?:{DETS})?(?:son|volume|musique)",
    r"(?:(?P<qte>un peu|un petit peu|beaucoup|encore) )?plus fort|plus de son|(?:on )?monte (?:un peu )?(?:le son)?",
)
SON_BAISSER = compiler(
    r"{BAISSER}(?: (?:{DETS})?(?:son|volume|musique))?(?: (?:de )?(?P<pas>{NOMBRE})(?: pourcent)?|"
    r" (?P<qte>encore un peu|un peu|"
    r"un petit peu|beaucoup|encore|un max|un bon coup))?",
    r"{BAISSER} (?P<qte>un peu|un petit peu|beaucoup|encore|un chouia|un chouilla|un poil|legerement) "
    r"(?:{DETS})?(?:son|volume|musique)",
    r"(?:(?P<qte>un peu|un petit peu|beaucoup|encore) )?moins fort|plus bas|moins de son|(?:un peu )?moins de bruit",
)
SON_COUPER = compiler(
    r"(?:{COUPER}|{DESACTIVER}|{ETEINDRE}) (?:{DETS})?(?:son|volume|audio|haut parleurs?|sons)(?: du mac)?",
    r"mute(?: (?:le son|le volume|le mac|tout))?|{METTRE} en sourdine|sourdine|coupe tout le son|(?:{ACTIVER}|"
    r"{METTRE}) la sourdine|"
    r"{METTRE} (?:{DETS})?(?:son|volume|musique|mac) en sourdine",
)
SON_REMETTRE = compiler(
    r"(?:{REMETTRE}|{ACTIVER}|reactive|retablis|retablir|rallume) (?:{DETS})?(?:son|volume|audio|haut parleurs?)",
    r"unmute|(?:enleve|retire|{DESACTIVER}|coupe) (?:la )?sourdine",
)
SON_NIVEAU = compiler(
    r"quel est le volume|(?:le )?volume est a combien|c est quoi le volume|(?:le )?volume actuel|"
    r"a combien est le volume|(?:le )?niveau du volume|quel volume|le son est a combien"
)
MUSIQUE_PAUSE = compiler(
    r"pause|(?:{METTRE}) (?:en )?pause|(?:{METTRE}) (?:{DETS})?(?:musique|chanson|morceau|lecture|spotify|son|zik) "
    r"(?:en|sur) pause|(?:{ARRETER}|stop|{COUPER}|pause) (?:{DETS})?(?:musique|chanson|morceau|lecture|zik)"
    r"(?: qui passe| en cours)?",
)
MUSIQUE_LECTURE = compiler(
    r"lecture|play|joue|reprends|reprend|reprise|(?:{JOUER}|{LANCER}|{METTRE}|{REMETTRE}|relance|ecoute|ecouter|"
    r"continue|continuer) "
    r"(?:un peu de |du |{DETS})?(?:musique|chanson|morceau|zik|lecture)"
    r"(?: (?:sur|dans|avec) (?P<lecteur>spotify|musique|apple music))?",
)
MUSIQUE_SUIVANT = compiler(
    r"(?:passe (?:a la |au |a )?)?(?:{DETS})?(?:suivant|suivante)|(?:{DETS})?(?:chanson|morceau|titre|piste|musique|"
    r"son) "
    r"suivante?|next|skip|zappe|(?:saute|passe|zappe) (?:cette|la) (?:chanson|musique|piste)|"
    r"passe (?:a la|au) (?:chanson|morceau|titre) suivante?|au suivant|change de (?:chanson|morceau|musique|titre)|"
    r"(?:une )?autre (?:chanson|musique|morceau)|(?:saute|zappe) (?:ce morceau|ce titre|cette piste)|"
    r"passe (?:celle ci|celle la|celui ci|celui la|ce morceau|"
    r"cette chanson|ce titre)|(?:{DETS})?(?:chanson|morceau|titre) d apres",
)
MUSIQUE_PRECEDENT = compiler(
    r"(?:{DETS})?(?:precedent|precedente)|(?:{DETS})?(?:chanson|morceau|titre|piste|musique) precedente?|"
    r"previous|(?:reviens|retourne|passe|revenir) (?:a la|au) (?:chanson|morceau|titre|piste) (?:precedente?|d avant)|"
    r"(?:{REMETTRE}|{JOUER}) (?:{DETS})?(?:chanson|morceau|titre) (?:d avant|precedente?)|"
    r"(?:{DETS})?(?:chanson|morceau|titre) d avant|(?:reviens|retourne) en arriere d (?:une|un) (?:chanson|morceau|"
    r"titre)|"
    r"(?:{REMETTRE}|{JOUER}|relance) (?:{DETS})?precedente?|(?:{REMETTRE}|{JOUER}|relance) (?:celle|celui) d avant|"
    r"relance (?:{DETS})?(?:chanson|morceau|titre) d avant",
)
MUSIQUE_TITRE = compiler(
    r"c est quoi (?:cette|la) (?:chanson|musique)|quelle est cette (?:chanson|musique)|c est quoi ce (?:morceau|son|"
    r"titre)|"
    r"qu est ce qui passe|qu est ce qu on ecoute|quel est (?:le|ce) (?:titre|morceau)|c est quoi le titre|qui chante|"
    r"c est qui qui chante|quelle chanson (?:c est|passe)",
)
MUSIQUE_PLAYLIST = compiler(
    r"(?:{LANCER}|{METTRE}|{JOUER}|ecoute|ecouter|{DEMARRER}) (?:{DETS})?(?:playlist|liste de lecture|play list) "
    r"(?P<objet>.+)",
    r"playlist (?P<objet>.+)",
)

# --- Système -----------------------------------------------------------------------------------------------------
VERROUILLER = compiler(
    r"{VERROUILLER}(?: (?:{DETS})?(?:ecran|session|{MACHINE}|tout))?|verrouillage(?: de l ecran)?|lock"
)
VEILLE = compiler(
    r"(?:{METTRE}|passe|passer) (?:{DETS})?(?:{MACHINE} )?en veille|mise en veille(?: (?:du|de l) {MACHINE})?|"
    r"veille|(?:{METTRE}|passe) le {MACHINE} en veille|(?:{METTRE}|passe) en veille (?:{DETS})?{MACHINE}|"
    r"(?:{DETS})?{MACHINE} en veille"
)
ECRAN_ETEINDRE = compiler(
    r"(?:{DESACTIVER}|{ETEINDRE}|{COUPER}) (?:{DETS})?(?:ecran|moniteur|affichage)|"
    r"(?:{METTRE}) (?:{DETS})?ecran en veille|ecran noir|mise en veille de l ecran"
)
MODE_SOMBRE = compiler(
    r"(?:(?:{ACTIVER}|{METTRE}|{REMETTRE}|passe|passer|repasse|repasser|bascule|basculer) (?:en |sur |le |la |l )?)?"
    r"(?:mode|theme|apparence) (?:sombre|nuit|noir|dark|fonce|foncee)",
    r"dark mode|(?:{DESACTIVER}|{ETEINDRE}|enleve) (?:le )?(?:mode|theme) (?:clair|jour)",
)
MODE_CLAIR = compiler(
    r"(?:(?:{ACTIVER}|{METTRE}|{REMETTRE}|passe|passer|repasse|repasser|bascule|basculer) (?:en |sur |le |la |l )?)?"
    r"(?:mode|theme|apparence) (?:clair|claire|jour|blanc|light|lumineux)",
    r"light mode|(?:{DESACTIVER}|{ETEINDRE}|enleve|enlever|{QUITTER}|sors du|sortir du) (?:le )?(?:mode|theme) "
    r"(?:sombre|nuit|noir|dark|fonce|foncee)",
)
WIFI = r"(?:wifi|wi fi|ouifi|wifie|connexion wifi|reseau wifi|le wifi|la wifi)"
WIFI_ACTIVER = compiler(
    rf"(?:{{ACTIVER}}|rallume|reactive|{{REMETTRE}}|{{METTRE}}|connecte|reconnecte|rebranche|relance|"
    rf"branche) (?:{{DETS}})?{WIFI}|"
    rf"{WIFI} on|"
    rf"(?:{{ACTIVER}}|rallume|reactive) internet"
)
WIFI_DESACTIVER = compiler(
    rf"(?:{{DESACTIVER}}|{{COUPER}}|{{ETEINDRE}}|{{ARRETER}}|enleve|deconnecte|debranche) (?:{{DETS}})?{WIFI}|"
    rf"{WIFI} off|"
    rf"(?:{{COUPER}}|{{DESACTIVER}}) internet"
)
BATTERIE = compiler(
    r"(?:l )?etat de (?:la )?batterie|(?:le )?niveau (?:de|de la) batterie|(?:il me reste |il reste )?combien de "
    r"batterie(?: (?:il )?(?:me )?reste)?|il me reste combien de batterie|(?:la )?batterie|"
    r"(?:quelle est l |combien d )autonomie(?: il me reste)?|il (?:me |nous )?reste combien d autonomie|"
    r"(?:le )?pourcentage de (?:la )?batterie|"
    r"ou en est la batterie|est ce que je suis en charge|est ce que (?:le mac|l ordi) charge"
)
HEURE = compiler(
    r"(?:quelle heure (?:est il|il est|est il maintenant)|il est quelle heure|(?:l )?heure|donne moi l heure|"
    r"c est quelle heure|(?:tu |t )?(?:as|aurais) l heure|quelle heure)"
)
DATE = compiler(
    r"quel jour (?:sommes nous|on est|est on|nous sommes|sommes nous aujourd hui)|on est quel jour(?: aujourd hui)?|"
    rf"quelle est la date(?: d aujourd hui)?|(?:la )?date(?: du jour| d aujourd hui)?|on est le combien{_QUAND}?|"
    r"c est quel jour(?: aujourd hui)?|quelle date sommes nous|(?:nous sommes|on est) quelle date"
)
METEO = compiler(
    rf"quel temps (?:fait il|il fait)(?: dehors)?{_QUAND}?(?: dehors)?|il fait quel temps(?: dehors)?{_QUAND}?|"
    rf"(?:(?:{{OUVRIR}}|{{AFFICHER}}|donne moi|donne|donner|dis moi) )?(?:{{DETS}})?meteo{_QUAND}?|"
    r"est ce qu il (?:va pleuvoir|pleut)|(?:est ce qu )?il va (?:faire beau|pleuvoir)(?: aujourd hui)?(?: ou pas)?"
)

# --- Concentration --------------------------------------------------------------------------------------------------
_FOCUS = r"(?:concentration|ne pas deranger|ne plus deranger|focus|do not disturb)"
CONCENTRATION_ACTIVER = compiler(
    rf"(?:(?:{{ACTIVER}}|{{METTRE}}|passe|passer|lance|{{DEMARRER}}) )?(?:{{DETS}})?(?:en )?(?:mode )?{_FOCUS}"
    rf"(?: (?:de |d )?(?:macos|mac|apple|systeme))?(?: (?:pendant|pour|durant) .+)?",
    r"(?:.+ )?(?:{ACTIVER}|{METTRE}|passe|lance) (?:{DETS})?(?:mode )?ne pas deranger(?: .+)?",
    r"(?:je (?:veux|voudrais|dois|vais|aimerais|ai besoin de)|il faut que je|faut que je|j ai besoin de) "
    r"(?:me concentrer|etre tranquille|ne pas etre derange|travailler au calme)",
    r"(?:me concentrer|etre tranquille|ne pas etre derange)",
    r"(?:(?:je travaille|je bosse|je suis occupe|je revise|je suis en reunion|je suis concentre) )?"
    r"ne me derange (?:plus|pas)(?: (?:je|j|on|il) .+)?|qu on ne me derange pas|je ne veux (?:plus|pas) etre derange",
    r"(?:j ai besoin de|je veux du|je voudrais du|un peu de) (?:calme|tranquillite|silence|concentration)",
    r"que je (?:me concentre|sois tranquille|bosse au calme)",
    r"(?:ne )?pas etre derange",
)
CONCENTRATION_DESACTIVER = compiler(
    r"(?:tu peux )?(?:me )?deranger(?: (?:maintenant|a nouveau|de nouveau))?",
    rf"(?:{{DESACTIVER}}|{{ARRETER}}|{{QUITTER}}|{{COUPER}}|enleve|enlever|{{ETEINDRE}}|sors du|sortir du|sors de|"
    rf"fin du|"
    rf"fin de) "
    rf"(?:{{DETS}})?(?:mode )?{_FOCUS}(?: (?:de |d )?(?:macos|mac|apple|systeme))?(?: (?:j|je|on|pendant|pour) .+)?",
)

# --- Fichiers ----------------------------------------------------------------------------------------------------
DERNIER_PDF = compiler(
    r"(?:(?:{OUVRIR}|{AFFICHER}) (?:moi )?)?(?:{DETS})?(?:dernier|plus recent) (?:fichier |document )?pdf",
    r"(?:(?:{OUVRIR}|{AFFICHER}) (?:moi )?)?(?:{DETS})?pdf le plus recent",
)
DERNIER_TELECHARGE = compiler(
    r"(?:(?:{OUVRIR}|{AFFICHER}) (?:moi )?)?(?:{DETS})?(?:dernier|plus recent) (?:fichier |document )?"
    r"(?:telecharge|telechargement)",
    r"(?:(?:{OUVRIR}|{AFFICHER}) (?:moi )?)?(?:{DETS})?(?:fichier|document|truc) (?:que|qu) je viens de telecharger",
    r"(?:(?:{OUVRIR}|{AFFICHER}) )?ce que je viens de telecharger",
    r"(?:(?:{OUVRIR}|{AFFICHER}) (?:moi )?)?(?:{DETS})?(?:dernier|derniere) (?:truc|chose|fichier|document) "
    r"(?:que|qu) j ai telecharge",
)
DERNIERE_CAPTURE = compiler(
    r"(?:(?:{OUVRIR}|{AFFICHER}) (?:moi )?)?(?:{DETS})?capture(?: d ecran)? (?:que je viens de (?:faire|prendre)|"
    r"la plus recente|que j ai (?:faite?|prise?))",
    r"(?:(?:{OUVRIR}|{AFFICHER}) (?:moi )?)?(?:{DETS})?(?:derniere|plus recente) (?:capture d ecran|capture|"
    r"screenshot|copie d ecran)",
)
RESULTAT = compiler(
    r"(?:(?:{OUVRIR}|{AFFICHER}|prends|choisis|{LANCER}) )?(?:{DETS})?(?:resultat|fichier|document|lien) "
    r"(?:numero |n )?(?P<rang>{RANG})",
    r"(?:(?:{OUVRIR}|{AFFICHER}|prends|choisis|{LANCER}) )?(?:{DETS})?(?:numero |n )?(?P<rang>{RANG})"
    r"(?: (?:resultat|fichier|document|lien|de la liste))?",
)
REVELER = compiler(
    r"(?:revele|reveler) (?:moi )?(?:{DETS})?(?:numero )?(?P<rang>{RANG})(?: (?:resultat|fichier|document))?",
    r"(?:(?:{AFFICHER}|revele|reveler|{OUVRIR}) (?:moi )?)?(?:{DETS})?(?:numero )?(?P<rang>{RANG})"
    r"(?: (?:resultat|fichier|document))? dans (?:le )?finder",
)
CHERCHER_FICHIER = compiler(
    r"{CHERCHER} (?:moi )?(?:{DETS})?(?:fichiers?|documents?|docs?|(?:dans|sur|parmi) (?:mes|les) "
    r"(?:fichiers|documents|dossiers|docs)|sur le mac|sur mon mac|dans le finder) (?:qui s appelle |qui se nomme |"
    r"nomme |intitule |appele )?(?P<requete>.+)",
    r"ou (?:j ai|ai je|est ce que j ai) (?:mis|range|enregistre|sauvegarde|laisse|classe) (?:{DETS})?"
    r"(?:fichiers? |documents? |docs? )?(?P<requete>.+)",
    r"{CHERCHER} (?:moi )?(?P<requete>.+?)(?: (?:dans mes fichiers|sur le mac|sur mon mac|avec spotlight))?",
    r"ou (?:est|sont|se trouve|se trouvent) (?:{DETS})?(?:fichiers?|documents?) (?P<requete>.+)",
)

# --- Web -----------------------------------------------------------------------------------------------------------
_GOOGLE = r"(?:google|internet|le web|le net|la toile)"
_VERBE_MOTEUR = r"(?:{CHERCHER}|regarde|regarder|tape|taper|demande|demander)"
# « YouTube c'est bien », « YouTube est en panne » : un avis, pas une recherche.
_PAS_UN_AVIS = r"(?!(?:est|c est|ca|a|ne|n|marche|marchent|fonctionne|plante|bug|bugue|rame|craint|et|ou)\b)"
GOOGLE = compiler(
    rf"{_VERBE_MOTEUR} (?:sur|dans|avec|a) {_GOOGLE} (?P<requete>.+)",
    rf"(?:va|vas|aller|{{OUVRIR}}) (?:sur )?google (?:et )?{_VERBE_MOTEUR} (?P<requete>.+)",
    r"(?:googlise|googlelise|googleise|googler|google moi) (?P<requete>.+)",
    rf"{{CHERCHER}} (?P<requete>.+?) (?:sur|dans|avec) {_GOOGLE}",
    rf"google {_PAS_UN_AVIS}(?P<requete>.+)",
    r"(?:fais|lance) une recherche(?: google| sur google| sur internet)? (?:sur |de |pour )?(?P<requete>.+)",
    r"recherche google (?:sur |de |pour )?(?P<requete>.+)",
)
YOUTUBE = compiler(
    rf"(?:{_VERBE_MOTEUR}|{{METTRE}}|{{LANCER}}|{{JOUER}}) (?:sur|dans) youtube (?P<requete>.+)",
    r"(?:{OUVRIR}|{LANCER}) youtube (?:sur|a propos de|pour|au sujet de) (?P<requete>.+)",
    r"(?:va|vas|aller|{OUVRIR}) (?:sur )?youtube (?:et )?(?:{CHERCHER}|regarde|{METTRE}|{LANCER}) (?P<requete>.+)",
    rf"youtube {_PAS_UN_AVIS}(?P<requete>.+)",
    r"{CHERCHER} (?P<requete>.+?) (?:sur|dans) youtube",
    r"(?:{METTRE}|{LANCER}|{JOUER}|regarde|regarder) (?P<requete>.+?) sur youtube",
)
WIKIPEDIA = compiler(
    rf"(?:{_VERBE_MOTEUR}|lis|lire) (?:sur|dans) (?:wikipedia|wiki) (?P<requete>.+)",
    rf"(?:va|vas|aller|{{OUVRIR}}) (?:sur )?(?:wikipedia|wiki) (?:et )?(?:{_VERBE_MOTEUR}|lis) (?P<requete>.+)",
    r"(?:{OUVRIR}|{LANCER}|lis|lire) (?:wikipedia|wiki) (?:sur|a propos de|pour|a la page|au sujet de) (?P<requete>.+)",
    rf"(?:wikipedia|wiki) {_PAS_UN_AVIS}(?P<requete>.+)",
    r"{CHERCHER} (?P<requete>.+?) (?:sur|dans) (?:wikipedia|wiki)",
    r"(?:qui est|qu est ce que|c est quoi) (?P<requete>.+?) (?:sur|selon) (?:wikipedia|wiki)",
)
PLANS = compiler(
    r"(?:{OUVRIR}|{LANCER}) (?:plans|maps|google maps|apple plans|la carte) (?:pour aller jusqu au|pour aller jusqu a|"
    r"pour aller au|pour aller aux|pour aller a|pour aller en|pour aller chez|pour aller|jusqu au|jusqu a|vers|pour) "
    r"(?P<requete>.+)",
    r"(?:{AFFICHER}|{CHERCHER}|{OUVRIR}) (?:moi )?(?P<requete>.+?) (?:sur|dans) (?:plans|la carte|une carte|maps|"
    r"google maps|apple plans)",
    r"(?:(?:{AFFICHER}|donne|{CHERCHER}) (?:moi )?)?(?:{DETS})?(?:itineraire|trajet|chemin|"
    r"route) (?:pour aller jusqu au|pour aller jusqu a|pour aller au|pour aller aux|"
    r"pour aller a|pour aller en|pour aller chez|jusqu au|jusqu a|vers|pour|au|aux|a) (?P<requete>.+)",
    r"(?:comment (?:aller|je vais|on va)|emmene(?: moi)?|guide(?: moi)?) (?:a|au|aux|en|chez|vers|jusqu a|"
    r"jusqu au) (?P<requete>.+)",
)
LANGUES = {
    "anglais": "en", "espagnol": "es", "allemand": "de", "italien": "it", "portugais": "pt", "chinois": "zh",
    "japonais": "ja", "arabe": "ar", "russe": "ru", "neerlandais": "nl", "francais": "fr", "polonais": "pl",
    "coreen": "ko", "grec": "el", "turc": "tr", "suedois": "sv",
}  # fmt: skip
_LANGUE = "(?P<langue>" + "|".join(LANGUES) + ")"
TRADUIRE = compiler(
    rf"{{TRADUIRE}} (?P<texte>.+?) en {_LANGUE}",
    rf"comment (?:on )?(?:dit on|dit|on dit|dire) (?P<texte>.+?) en {_LANGUE}",
    rf"(?:la )?traduction (?:de |d )?(?P<texte>.+?) en {_LANGUE}",
    rf"{{TRADUIRE}} en {_LANGUE} (?P<texte>.+)",
    rf"c est quoi (?P<texte>.+?) en {_LANGUE}",
    r"{TRADUIRE} (?P<texte>.+)",
)

# --- Apps ----------------------------------------------------------------------------------------------------------
_TOUT = r"(?:tout|toutes? (?:les|mes) (?:apps|applis|applications|fenetres|programmes)|tous (?:les|mes) programmes|"
_TOUT += r"tout le reste|"
_TOUT += r"tout ce qui est ouvert|toutes (?:les|mes) (?:apps|applis|applications|fenetres) ouvertes|"
_TOUT += r"tous (?:les|mes) programmes ouverts|(?:les|mes) (?:apps|applis|applications|programmes|fenetres) qui sont "
_TOUT += r"ouverte?s)"
FERMER_TOUT_SAUF = compiler(
    rf"(?:{{FERMER}}|{{QUITTER}}) {_TOUT} (?:sauf|a part|excepte|hormis|mais pas) (?P<objet>.+)",
)
FERMER_TOUT = compiler(rf"(?:{{FERMER}}|{{QUITTER}}) {_TOUT}")
CACHER_AUTRES = compiler(
    rf"{{CACHER}} (?:{_TOUT}|les autres|toutes les autres(?: apps| applications)?|les autres (?:apps|applications)) "
    rf"(?:sauf|a part|excepte|hormis|mais pas) (?P<objet>.+)",
    r"{CACHER} (?:toutes )?(?:les|mes) autres(?: (?:apps|applis|applications|fenetres|programmes))?",
    r"{CACHER} (?:tout|tout le reste|le reste|le reste des (?:fenetres|apps|applis|applications))",
)
FERMER = compiler(r"(?:{FERMER}|{QUITTER}|{ARRETER}) (?P<objet>.+)")
CACHER = compiler(r"(?:{CACHER}|fais disparaitre|fait disparaitre) (?P<objet>.+)")
AFFICHER = compiler(
    r"(?:va|vas|aller|allez|passe|passer|repasse|bascule|basculer|reviens|revenir|retourne|retourner|remets|remet|"
    r"emmene|emmener|amene) (?:sur|a|au|dans|vers) (?P<objet>.+)",
    r"(?:{AFFICHER}) (?:moi )?(?P<objet>.+)",
    r"(?:{METTRE}|{REMETTRE}|{AFFICHER}|amene|ramene|passe) (?:moi )?(?P<objet>.+?) (?:au premier plan|devant|"
    r"en avant)",
    r"(?:fais|fait) (?:moi )?voir (?P<objet>.+)",
    r"(?:va|vas|aller|allez) voir (?:sur |dans )?(?P<objet>.+)",
)
OUVRIR = compiler(
    r"(?:{OUVRIR}|{LANCER}|{DEMARRER}) (?:moi )?(?P<objet>.+)",
    r"(?:j ai besoin de|j ai besoin d|j aurais besoin de|j aurais besoin d|il (?:me|nous) faut|"
    r"il (?:me|nous) faudrait) (?P<objet>.+?)(?: (?:{OUVRIR}|{LANCER}) (?:le|la|les))?",
)
# Verbes faibles (« mets Netflix », « joue Jazz du soir ») : seulement un nom dit (presque) exactement ; sinon
# « joue aux cartes », « mets la table » deviendraient des ordres.
OUVRIR_FAIBLE = compiler(
    r"(?:{METTRE}|{JOUER}|ecoute|ecouter) (?:moi )?(?!(?:a|au|aux|avec|sur|dans|en|pour|chez)\b)(?P<objet>.+)"
)  # « joue aux cartes » : jouer à quelque chose n'est pas lancer une app

# Mots qui disent le genre d'objet (« l'app Notes », « le site YouTube », « le dossier Documents ») : retirés de
# l'objet, gardés comme indice.
INDICES_GENRE = [
    ("app", r"(?:l |une |mon |ma )?(?:app|appli|application|logiciel|programme)(?: de)?"),
    (
        None,
        r"(?:fenetres?|traitement de texte|tableur|navigateur|gestionnaire de mots de passe|lecteur video|messagerie|"
        r"lecteur de musique|liste|boite|boite mail|boite de reception|fichier|document)(?: de| des| du| d)?",
    ),
    ("site", r"(?:le |un |mon )?(?:site|site web|page|page web|site internet)(?: de| du| d)?"),
    ("dossier", r"(?:le |un |mon |mes |les )?(?:dossier|dossiers|repertoire)(?: des| de| du| d)?"),
]
SUFFIXES_OBJET = (
    r"(?: (?:pour moi|maintenant|tout de suite|vite|rapidement|sur le mac|sur l ordinateur|sur mon mac|"
    r"sur l ordi|en grand|en plein ecran|stp|s il te plait|merci|dans le navigateur|sur internet|dans safari|"
    r"dans chrome|dans firefox|sur safari|sur chrome|sur le navigateur|sur le web|dans le finder|en ligne|"
    r"sur spotify|dans spotify|sur apple music|devant|au premier plan|en avant))+$"
)
