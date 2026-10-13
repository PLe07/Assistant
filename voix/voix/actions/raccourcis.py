"""Les raccourcis Apple : lancer n'importe quel raccourci installé (son nom vient de `shortcuts list`, jamais de la
phrase seule), la liste, et la concentration par les raccourcis « Activer concentration » / « Désactiver
concentration » que Voix fournit (à ajouter une fois, voir le README).
"""

from __future__ import annotations

from voix.actions.base import Annulation, Etat, Outils, Reponse, erreur, fait, info
from voix.nlu.catalogue import Objet

ACTIVER = "Activer concentration"
DESACTIVER = "Désactiver concentration"


def _installe(o: Outils, nom: str) -> bool:
    return any(r.nom == nom for r in o.catalogue.du_genre("raccourci"))


def executer(o: Outils, nom: str, intention: str) -> Reponse:
    if not nom or len(nom) > 200 or nom.startswith("-") or not _installe(o, nom):
        return erreur(f"Le raccourci « {nom} » n'est pas installé.", intention)
    r = o.lancer("shortcuts", "run", nom, delai_s=60)
    if r.delai_depasse:
        return erreur(f"Le raccourci « {nom} » met trop de temps.", intention)
    if not r.ok:
        return erreur(f"Le raccourci « {nom} » a échoué.", intention)
    return fait(f"Raccourci « {nom} »", intention)


def lancer(o: Outils, objet: Objet) -> Reponse:
    return executer(o, objet.cible, "raccourci.lancer")


def lister(o: Outils) -> Reponse:
    noms = sorted(r.nom for r in o.catalogue.du_genre("raccourci"))
    if not noms:
        return info("Aucun raccourci Apple installé.", "raccourci.lister")
    return info(f"{len(noms)} raccourci{'s' if len(noms) > 1 else ''} : " + ", ".join(noms) + ".", "raccourci.lister",
                raccourcis=noms)  # fmt: skip


def concentration(o: Outils, etat: Etat, activer: bool) -> Reponse:
    intention = "concentration.activer" if activer else "concentration.desactiver"
    nom = ACTIVER if activer else DESACTIVER
    if not _installe(o, nom):
        return erreur(f"Ajoute d'abord le raccourci « {nom} » (voir le README).", intention)
    r = executer(o, nom, intention)
    if r.statut != "fait":
        return r
    etat.retenir(Annulation("concentration", {"active": not activer}, "concentration"))
    return fait("Concentration activée" if activer else "Concentration désactivée", intention)
