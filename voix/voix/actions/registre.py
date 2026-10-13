"""Chaque intention de la liste blanche → son action. Une intention sans action ici n'existe pas (vérifié par les
tests) ; une action ne reçoit que des paramètres déjà validés par la compréhension (ou par `routines.preparer`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from voix.actions import annuler, apps, fichiers, minuteur, modules, raccourcis, routines, son, systeme, web
from voix.actions.base import Etat, Outils, Reponse, erreur, fait, info
from voix.actions.minuteur import Minuteurs
from voix.nlu.comprendre import Comprehension


@dataclass
class Execution:
    o: Outils
    etat: Etat
    minuteurs: Minuteurs


Action = Callable[[Execution, dict[str, Any], str], Reponse]


def _routine(x: Execution, p: dict[str, Any], i: str) -> Reponse:
    routine = x.o.commandes.routine(p["objet"].ident)
    if routine is None:
        return erreur("Cette routine n'existe plus.", i)
    return routines.lancer(routine, x.o.catalogue, lambda c: executer(c, x))


def _aide(x: Execution, p: dict[str, Any], i: str) -> Reponse:
    page = x.o.chemins.aide_memoire
    if page.is_file() and x.o.lancer("open", str(page)).ok:
        return fait("Aide-mémoire ouvert", i)
    return info("Dis par exemple : « ouvre Notion », « volume à 30 % », « minuteur 10 minutes », « annule ».", i)


def _parler(x: Execution, oui: bool, i: str) -> Reponse:
    x.etat.parler = oui
    return fait("Je te réponds à voix haute" if oui else "Je ne parle plus", i)


def _pause(x: Execution, p: dict[str, Any], i: str) -> Reponse:
    r = x.o.demander("ecoute.pause")
    return fait("Écoute en pause", i) if r.ok else erreur(f"Je n'ai pas pu me mettre en pause : {r.erreur}.", i)


def _repeter(x: Execution, p: dict[str, Any], i: str) -> Reponse:
    if x.etat.derniere is None:
        return info("Je n'ai encore rien dit.", i)
    return info(x.etat.derniere.texte, i)


ACTIONS: dict[str, Action] = {
    "app.ouvrir": lambda x, p, i: apps.ouvrir(x.o, p["objet"]),
    "app.afficher": lambda x, p, i: apps.ouvrir(x.o, p["objet"], i),
    "app.fermer": lambda x, p, i: apps.fermer(x.o, p["objet"]),
    "app.cacher": lambda x, p, i: apps.cacher(x.o, p["objet"]),
    "app.cacher_autres": lambda x, p, i: apps.cacher_autres(x.o, p.get("objet")),
    "app.fermer_tout": lambda x, p, i: apps.fermer_tout(x.o, None),
    "app.fermer_tout_sauf": lambda x, p, i: apps.fermer_tout(x.o, p["objet"]),
    "dossier.ouvrir": lambda x, p, i: fichiers.ouvrir_dossier(x.o, p["objet"]),
    "alias.ouvrir": lambda x, p, i: fichiers.ouvrir_alias(x.o, p["objet"]),
    "fichier.dernier_pdf": lambda x, p, i: fichiers.dernier(x.o, i),
    "fichier.dernier_telecharge": lambda x, p, i: fichiers.dernier(x.o, i),
    "fichier.derniere_capture": lambda x, p, i: fichiers.dernier(x.o, i),
    "fichier.chercher": lambda x, p, i: fichiers.chercher(x.o, x.etat, p["requete"]),
    "fichier.ouvrir_resultat": lambda x, p, i: fichiers.resultat(x.o, x.etat, p["rang"], reveler=False),
    "fichier.reveler_resultat": lambda x, p, i: fichiers.resultat(x.o, x.etat, p["rang"], reveler=True),
    "web.ouvrir_site": lambda x, p, i: web.ouvrir_site(x.o, p["objet"]),
    "web.chercher_google": lambda x, p, i: web.chercher(x.o, i, p["requete"]),
    "web.chercher_youtube": lambda x, p, i: web.chercher(x.o, i, p["requete"]),
    "web.chercher_wikipedia": lambda x, p, i: web.chercher(x.o, i, p["requete"]),
    "web.chercher_plans": lambda x, p, i: web.chercher(x.o, i, p["requete"]),
    "web.traduire": lambda x, p, i: web.traduire(x.o, p["texte"], p.get("langue", "en")),
    "son.monter": lambda x, p, i: son.varier(x.o, x.etat, i, int(p.get("pas", 10))),
    "son.baisser": lambda x, p, i: son.varier(x.o, x.etat, i, int(p.get("pas", 10))),
    "son.couper": lambda x, p, i: son.sourdine(x.o, x.etat, True),
    "son.remettre": lambda x, p, i: son.sourdine(x.o, x.etat, False),
    "son.regler": lambda x, p, i: son.regler(x.o, x.etat, int(p["niveau"])),
    "son.niveau": lambda x, p, i: son.niveau(x.o),
    "musique.lecture": lambda x, p, i: son.musique(x.o, i, p.get("lecteur")),
    "musique.pause": lambda x, p, i: son.musique(x.o, i),
    "musique.suivant": lambda x, p, i: son.musique(x.o, i),
    "musique.precedent": lambda x, p, i: son.musique(x.o, i),
    "musique.titre": lambda x, p, i: son.musique(x.o, i),
    "musique.playlist": lambda x, p, i: son.playlist(x.o, p["objet"]),
    "systeme.verrouiller": lambda x, p, i: systeme.verrouiller(x.o),
    "systeme.veille": lambda x, p, i: systeme.veille(x.o),
    "systeme.ecran_eteindre": lambda x, p, i: systeme.ecran(x.o),
    "systeme.mode_sombre": lambda x, p, i: systeme.apparence(x.o, x.etat, True),
    "systeme.mode_clair": lambda x, p, i: systeme.apparence(x.o, x.etat, False),
    "systeme.wifi_activer": lambda x, p, i: systeme.wifi(x.o, x.etat, True),
    "systeme.wifi_desactiver": lambda x, p, i: systeme.wifi(x.o, x.etat, False),
    "systeme.batterie": lambda x, p, i: systeme.batterie(x.o),
    "systeme.heure": lambda x, p, i: systeme.heure(x.o.maintenant()),
    "systeme.date": lambda x, p, i: systeme.date(x.o.maintenant()),
    "systeme.meteo": lambda x, p, i: systeme.meteo(x.o),
    "concentration.activer": lambda x, p, i: raccourcis.concentration(x.o, x.etat, True),
    "concentration.desactiver": lambda x, p, i: raccourcis.concentration(x.o, x.etat, False),
    "minuteur.lancer": lambda x, p, i: minuteur.lancer(x.o, x.minuteurs, int(p["duree_s"])),
    "rappel.creer": lambda x, p, i: minuteur.rappel(
        x.o, x.minuteurs, int(p["duree_s"]), str(p["message"]), p.get("heure")
    ),  # fmt: skip
    "minuteur.annuler": lambda x, p, i: minuteur.annuler(x.minuteurs),
    "minuteur.restant": lambda x, p, i: minuteur.restant(x.o, x.minuteurs),
    "raccourci.lancer": lambda x, p, i: raccourcis.lancer(x.o, p["objet"]),
    "raccourci.lister": lambda x, p, i: raccourcis.lister(x.o),
    "routine.lancer": _routine,
    "module.tableau_ouvrir": lambda x, p, i: modules.executer(x.o, i),
    "module.tableau_etat": lambda x, p, i: modules.executer(x.o, i),
    "module.ambiance_mode": lambda x, p, i: modules.executer(x.o, i, p.get("mode")),
    "module.ambiance_mood": lambda x, p, i: modules.executer(x.o, i),
    "module.quotidien_menu": lambda x, p, i: modules.executer(x.o, i),
    "module.bouclier_presse_papiers": lambda x, p, i: modules.executer(x.o, i),
    "controle.annuler": lambda x, p, i: annuler.defaire(x.o, x.etat),
    "controle.repeter": _repeter,
    "controle.stop": lambda x, p, i: Reponse("stop", "", i),
    "controle.aide": _aide,
    "controle.silencieux": lambda x, p, i: _parler(x, False, i),
    "controle.parler": lambda x, p, i: _parler(x, True, i),
    "controle.pause": _pause,
    "controle.oui": lambda x, p, i: info("Il n'y a rien à confirmer.", i),
    "controle.non": lambda x, p, i: info("D'accord.", i),
    "refus": lambda x, p, i: Reponse("refus", "Je ne fais pas ça, par sécurité.", i),
}


def executer(c: Comprehension, x: Execution) -> Reponse:
    if c.intention is None or c.intention not in ACTIONS:
        return erreur("Je ne sais pas faire ça.", c.intention)
    try:
        return ACTIONS[c.intention](x, c.params, c.intention)
    except (KeyError, TypeError, ValueError) as e:  # un paramètre manquant ou invalide : rien n'a été lancé
        return erreur(f"Paramètre invalide ({e.__class__.__name__}).", c.intention)
