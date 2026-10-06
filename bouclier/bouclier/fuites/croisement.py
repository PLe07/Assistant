"""Le croisement des fuites publiques avec ton inventaire (n°18) et les notifications (une seule fois par fuite).

Une fuite te concerne si son domaine correspond à un service où tu as un compte (domaine, sous-domaine ou alias de
marque) et si elle n'est pas antérieure à la création du compte quand celle-ci est connue (mail de bienvenue).
Au tout premier passage, les fuites anciennes sont notées et résumées en une seule notification ; ensuite, chaque
nouvelle fuite qui touche un de tes services déclenche une notification, une seule fois.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from bouclier.arnaque.liens import domaine_enregistrable
from bouclier.comptes import regroupement
from bouclier.db import Base
from bouclier.fuites import traductions
from bouclier.fuites.hibp import Fuite
from bouclier.notifier import Notifieur


@dataclass(frozen=True)
class CompteSurveille:
    service: str
    nom: str
    domaines: tuple[str, ...]
    cree_le: dt.date | None  # connu seulement grâce au mail de bienvenue


@dataclass(frozen=True)
class Correspondance:
    fuite: Fuite
    compte: CompteSurveille
    confirmee: bool = False  # ton adresse figure dans la fuite (option payante)

    @property
    def que_faire(self) -> str:
        debut = "Change ce mot de passe tout de suite, et partout où tu l'as réutilisé"
        if not traductions.mots_de_passe_concernes(list(self.fuite.donnees)):
            debut = "Change ce mot de passe par précaution, et partout où tu l'as réutilisé"
        return (f"{debut} ; active la double authentification ; méfie-toi des messages qui citent ces informations"
                " (les escrocs s'en servent pour paraître crédibles).")  # fmt: skip


def comptes_surveilles(base: Base) -> list[CompteSurveille]:
    sortie = []
    for r in base.lignes("SELECT * FROM comptes WHERE nature = 'compte' AND statut != 'supprime'"):
        signaux = json.loads(r["signaux"])
        cree = dt.date.fromisoformat(r["premiere_vue"]) if "creation" in signaux and r["premiere_vue"] else None
        sortie.append(CompteSurveille(str(r["service"]), str(r["nom"]), tuple(json.loads(r["domaines"])), cree))
    return sortie


def croiser(
    fuites: list[Fuite], comptes: list[CompteSurveille], confirmees: set[str] | None = None
) -> list[Correspondance]:
    par_service = {c.service: c for c in comptes}
    par_domaine: dict[str, CompteSurveille] = {}
    for c in comptes:
        for d in c.domaines:
            par_domaine.setdefault(domaine_enregistrable(d), c)
    sortie = []
    for f in fuites:
        connu = regroupement.trouver(f.domaine)
        compte = par_service.get(connu.id) if connu else None
        compte = compte or par_domaine.get(domaine_enregistrable(f.domaine))
        if compte is None:
            continue
        if compte.cree_le and f.date and f.date < compte.cree_le:
            continue  # la fuite date d'avant ton compte : tes données n'y étaient pas
        sortie.append(Correspondance(f, compte, bool(confirmees and f.nom in confirmees)))
    sortie.sort(key=lambda c: c.fuite.date or dt.date.min, reverse=True)
    return sortie


@dataclass
class Bilan:
    toutes: list[Correspondance]
    nouvelles: list[Correspondance]
    premier_passage: bool


def signaler(base: Base, correspondances: list[Correspondance], notifieur: Notifieur,
             horloge: Callable[[], float] = time.time) -> Bilan:  # fmt: skip
    deja = {str(r["nom"]) for r in base.lignes("SELECT nom FROM fuites_signalees")}
    premier = base.lire_meta("fuites_initialisees") is None
    nouvelles = [c for c in correspondances if c.fuite.nom not in deja]
    if premier:
        if nouvelles:
            notifieur.envoyer("fuite", f"🛡️ {len(nouvelles)} fuite(s) ancienne(s) touchent tes comptes",
                              "Le détail et quoi faire : bouclier fuites, ou le tableau de bord.")  # fmt: skip
    else:
        for c in nouvelles:
            donnees = ", ".join(traductions.traduire(list(c.fuite.donnees))[:4])
            notifieur.envoyer("fuite", f"⚠️ Fuite de données chez {c.compte.nom}",
                              f"Données : {donnees}. {c.que_faire}")  # fmt: skip
    with base.transaction() as cx:
        for c in nouvelles:
            cx.execute("INSERT OR IGNORE INTO fuites_signalees(nom, service, signalee_le) VALUES (?, ?, ?)",
                       (c.fuite.nom, c.compte.service, horloge()))  # fmt: skip
    if premier:
        base.ecrire_meta("fuites_initialisees", str(horloge()))
    return Bilan(correspondances, nouvelles, premier)
