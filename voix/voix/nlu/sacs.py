"""Les sacs de mots : la seconde lecture des commandes sans objet, quand la grammaire n'a rien reconnu.

« le son plus fort », « c'est trop bas », « passe en sombre », « j'ai encore de la batterie », « une autre chanson » :
l'ordre des mots varie, les mots restent. Une intention est reconnue si
- un de ses **noyaux** est présent (tous les mots d'un noyau ; « / » sépare des mots interchangeables) ;
- **chaque** mot de la phrase est expliqué : un mot du noyau, un mot permis pour cette intention, ou un mot-outil.
Un seul mot inexpliqué (« la batterie de mon **téléphone** est morte ») et rien n'est reconnu. Deux intentions
possibles à la fois : rien non plus (pas de pari). Jamais de nombre ici : les réglages chiffrés restent à la grammaire.
"""

from __future__ import annotations

from dataclasses import dataclass

# Les mots-outils : libres partout (articles, pronoms, prépositions, adverbes qui ne changent pas l'ordre).
OUTILS = {
    "sa", "son", "ses", "nos", "vos", "notre", "votre", "leur", "lui", "se", "ici", "la", "aussi", "deja", "vraiment",
    "carrement", "simplement", "direct", "directement", "svp", "pendant", "avec", "sur", "dans", "par", "pour",
    "exactement", "precisement", "toute",
    "le", "les", "l", "un", "une", "des", "du", "de", "d", "mon", "ma", "mes", "ton", "ta", "ce", "cet",
    "cette", "au", "aux", "a", "en", "et", "moi", "me", "m", "maintenant", "vite", "encore", "tout", "stp", "bon",
    "alors", "allez", "donc", "juste", "je", "j", "tu", "t", "on", "est", "c", "ca", "y", "s", "il", "te",
    "plait", "merci", "peu", "suite",
}  # fmt: skip


@dataclass(frozen=True)
class Sac:
    intention: str
    noyaux: tuple[tuple[frozenset[str], ...], ...]
    permis: frozenset[str]

    def explique(self, mots: set[str]) -> bool:
        if not any(all(mots & fente for fente in noyau) for noyau in self.noyaux):
            return False
        connus = self.permis | OUTILS | {m for noyau in self.noyaux for fente in noyau for m in fente}
        return mots <= connus


def sac(intention: str, noyaux: str, permis: str = "") -> Sac:
    """`noyaux` : « plus+fort|trop+bas » (| sépare les noyaux, + les mots requis, / les mots interchangeables)."""
    lus = tuple(tuple(frozenset(f.split("/")) for f in n.split("+")) for n in noyaux.split("|"))
    return Sac(intention, lus, frozenset(permis.split()))


_SON = "son volume musique mets met mettre"
_MUSIQUE = "musique chanson morceau titre piste zik"
_ECRAN = "mac ordi ordinateur macbook ecran"
_POSER = "mode theme apparence passe passer repasse mets met mettre active activer bascule basculer"
_RETIRER = (
    "enleve enlever retire retirer desactive desactiver sors sortir quitte quitter arrete arreter coupe couper fini "
    "finie termine"
)
_QUESTION = "quel quelle quels combien quoi dis donne donner dire savoir connaitre peux pourrais veux voudrais aimerais"

SACS = [
    sac("son.monter", "plus+fort|monte/remonte/pousse/augmente",
        f"{_SON} trop beaucoup plus fort bas rien entends entend n monte remonte pousse augmente"),
    sac("son.baisser", "moins+fort|plus+bas|baisse/descends/descend/diminue/redescends",
        f"{_SON} trop beaucoup moins fort plus bas baisse descends descend diminue redescends cran"),
    sac("son.couper", "sourdine|coupe/couper/mute+son/volume|muet+mac/ordi/passe/mets/met/mettre",
        f"{_SON} active activer mac ordi passe muet coupe couper mute"),
    sac("son.remettre", f"sourdine+{'/'.join(_RETIRER.split())}", f"{_SON} {_RETIRER}"),
    sac("musique.lecture", "musique/zik+mets/met/mettre/joue/jouer/lance/lancer/ecoute/ecouter/envie/besoin/continue/"
        "continuer/reprends/reprendre/relance/remets/allume/rallume",
        "mets met mettre joue jouer lance lancer ecoute ecouter envie ai besoin aimerais voudrais veux continue "
        "continuer reprends reprendre relance remets allume rallume"),
    sac("musique.pause", "pause|stop/arrete/stoppe/coupe+musique/chanson/morceau/zik",
        f"{_MUSIQUE} mets met mettre sur stop arrete stoppe coupe lecture"),
    sac("musique.suivant", "suivant/suivante/next/skip/zappe|apres+chanson/morceau/titre/piste|"
        "autre+chanson/morceau/titre/musique|change/changer+chanson/morceau/titre/musique",
        f"{_MUSIQUE} passe mets met autre change changer apres suivant suivante zappe celle celui ci"),
    sac("musique.precedent", "precedent/precedente|avant+chanson/morceau/titre/piste|"
        "arriere+chanson/morceau/titre/piste",
        f"{_MUSIQUE} reviens retourne revenir remets remet joue passe arriere avant precedent precedente"),
    sac("systeme.veille", "veille", f"{_ECRAN} mets met mettre passe passer mise"),
    sac("systeme.ecran_eteindre", "ecran/moniteur+eteins/eteindre/eteint/noir",
        "ecran moniteur eteins eteindre eteint noir"),
    sac("systeme.mode_sombre", f"{'/'.join(_POSER.split())}+sombre/nuit/noir/dark/fonce", f"{_POSER} {_ECRAN}"),
    sac("systeme.mode_clair",
        f"{'/'.join(_POSER.split())}+clair/claire/jour/blanc/light|{'/'.join(_RETIRER.split())}+sombre/nuit/noir/dark",
        f"{_POSER} {_RETIRER} {_ECRAN}"),
    sac("systeme.wifi_activer",
        "wifi/internet+active/activer/allume/allumer/branche/brancher/rallume/remets/reconnecte/connecte/relance",
        "wifi internet connexion reseau mets met"),
    sac("systeme.wifi_desactiver",
        "wifi/internet+coupe/couper/desactive/desactiver/eteins/eteindre/arrete/debranche/deconnecte/enleve",
        "wifi internet connexion reseau"),
    sac("systeme.batterie", "batterie/autonomie",
        f"{_QUESTION} ai reste niveau etat assez pourcentage ou mac ordi charge tient dure temps"),
    sac("systeme.meteo", "meteo|temps+quel/quelle+fait/fera|beau+qu+fait/fera/faire|pleut/pleuvoir/pluie/neige/neiger",
        f"{_QUESTION} il fait fera faire va temps beau dehors aujourd hui avoir est qu meteo pleut pleuvoir pluie "
        "neige neiger"),
    sac("minuteur.restant", "combien+temps+reste", "il reste combien temps minuteur chrono timer"),
    sac("controle.repeter", "dit+quoi|repete/repeter/redis/redire", "as dit quoi repete repeter redis redire pardon"),
    sac("controle.stop", "stop/suffit/chut/tais+stop/suffit/chut/tais/assez", "stop suffit chut tais toi assez"),
    sac("controle.pause", "pause+fais/fait|ecouter/ecoute+arrete/arreter",
        "petite fais fait pause ecouter ecoute arrete arreter moment"),
    sac("systeme.date", "date|jour+quel/quelle|combien+on/sommes", f"{_QUESTION} aujourd hui nous sommes jour"),
    sac("concentration.activer", "calme|tranquille|concentrer|concentration/focus+"
        "active/activer/mets/met/lance/passe/mode",
        "ai besoin veux voudrais etre mode active activer mets met lance passe focus concentration"),
    sac("concentration.desactiver", f"concentration/focus/deranger+{'/'.join(_RETIRER.split())}/fin/stop",
        f"{_RETIRER} fin stop mode focus concentration ne pas deranger"),
    sac("minuteur.annuler", "minuteur/timer/chrono/rappel/minuterie+annule/arrete/stop/supprime/enleve/coupe/besoin/"
        "stoppe/retire", "plus besoin annule arrete stop supprime enleve coupe stoppe retire"),
    sac("raccourci.lister", "raccourcis", f"{_QUESTION} ai liste affiche montre sont apple tous"),
    sac("module.tableau_etat", "modules", "etat affiche montre comment vont va bien fonctionnent marchent dis donne"),
    sac("module.ambiance_mood", "ambiance/mood+autre/nouvelle/nouveau/change/changer",
        "mets met lance autre nouvelle nouveau change changer"),
    sac("module.bouclier_presse_papiers", "copie/presse/arnaque/phishing/escroquerie",
        "analyse verifie regarde que ai message texte sms mail papiers papier ou pas si une"),
    sac("controle.annuler", "comme+avant/etait|annule/annuler/defais+action/commande/avant/fait/faire/dernier/truc",
        "remets remet reviens comme avant etait annule annuler defais action commande derniere precedente viens "
        "faire fait as que dernier truc"),
    sac("controle.aide", "sers|utilise/utiliser+comment|commandes|aide",
        "quoi sers comment utilise utiliser montre liste qu que peux sais faire pour dire quelles sont tes aide"),
    sac("controle.silencieux", "silencieux/discret|voix+plus/sans|sans+parler",
        "passe mode mets plus voix reponds sans parler coupe"),
    sac("fichier.dernier_pdf", "pdf+dernier/derniere/recent/recente/viens",
        "ouvre affiche montre que ai recu telecharge telecharger plus fichier document dernier derniere recent recente "
        "telechargements"),
    sac("fichier.dernier_telecharge",
        "telecharge/telechargement/recu/recevoir/telecharger+dernier/derniere/viens/recent/recente/heure",
        "ouvre affiche montre que ai viens plus fichier document truc chose dernier derniere recent recente heure"),
    sac("fichier.derniere_capture", "capture/screenshot+derniere/dernier/viens/recente/recent",
        "ouvre affiche montre ecran que viens faire fait faite ai plus copie derniere dernier recente recent"),
]  # fmt: skip

OUI = sac("controle.oui", "oui/ouais/ouai/ok/okay/exact/exactement/confirme/accord/go/parfait/vas",
          "fais fait le bon accord bien sur y carrement")  # fmt: skip
NON = sac("controle.non", "non/nan|pas+question/peine/besoin|surtout+pas|oublie|laisse+tomber",
          "pas peine question surtout ira laisse tomber besoin plus tard jamais oublie annule n certainement rien "
          "grave")  # fmt: skip


def lire(cles: list[str]) -> str | None:
    """L'intention dont le sac explique toute la phrase, s'il n'y en a qu'une."""
    mots = set(cles)
    if not mots or any(m.isdigit() for m in mots):
        return None
    trouves = [s.intention for s in SACS if s.explique(mots)]
    return trouves[0] if len(trouves) == 1 else None


def oui_non(cles: list[str]) -> str | None:
    """« ouais vas-y », « oui fais-le », « non c'est pas la peine », « pas question »."""
    mots = set(cles)
    oui, non = OUI.explique(mots), NON.explique(mots)
    if oui and not non and not mots & {"non", "nan", "pas"}:
        return "controle.oui"
    if non and not oui:
        return "controle.non"
    return None
