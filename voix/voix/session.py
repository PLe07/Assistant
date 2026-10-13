"""La conversation : une phrase entendue → comprise → (confirmée, ou choisie) → faite → journalisée.

- « Notes ou Notion ? » : la phrase suivante est d'abord lue comme un choix (« Notion », « la deuxième », « aucun ») ;
  sinon, c'est une nouvelle commande.
- Action sensible : « Tu confirmes ? » ; « oui » dans le délai → faite ; « non », silence ou autre chose → annulée.
- Le journal garde le texte compris, l'intention et le résultat (jamais d'audio).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from voix.actions import minuteur
from voix.actions.base import Etat, Outils, Reponse, info
from voix.actions.confirmation import Confirmations
from voix.actions.minuteur import Minuteurs
from voix.actions.registre import Execution, executer
from voix.journal import Journal
from voix.nlu import ambiguite
from voix.nlu.comprendre import MODES_AMBIANCE, Choix, Comprehension, Contexte, comprendre
from voix.nlu.intentions import INTENTIONS


def contexte(o: Outils) -> Contexte:
    """Ce que la compréhension doit savoir : le catalogue, tes commandes, tes modules et les réglages."""
    return Contexte(
        o.catalogue,
        o.commandes,
        modules=frozenset(o.modules),
        modes_ambiance=dict(o.modes_ambiance or MODES_AMBIANCE),
        seuil=float(o.reglages["comprehension"]["seuil"]),
        marge=float(o.reglages["comprehension"]["marge_ambiguite"]),
        maintenant=o.maintenant,
    )


class Session:
    def __init__(self, o: Outils, journal: Journal | None = None, horloge: Callable[[], float] = time.monotonic):
        self.o = o
        self.etat = Etat(parler=bool(o.reglages["retour"]["parler"]))
        self.minuteurs = Minuteurs(o.chemins.minuteurs)
        self.journal = journal
        self.confirmations = Confirmations(float(o.reglages["confirmation"]["delai_s"]), horloge)
        self.choix: list[Choix] = []
        self.contexte = contexte(o)

    @property
    def execution(self) -> Execution:
        return Execution(self.o, self.etat, self.minuteurs)

    def _sensible(self, c: Comprehension) -> bool:
        if c.intention == "routine.lancer":
            routine = self.o.commandes.routine(getattr(c.params.get("objet"), "ident", ""))
            return routine is not None and routine.sensible
        return c.intention in INTENTIONS and INTENTIONS[c.intention].sensible

    def _faire(self, c: Comprehension) -> Reponse:
        if self._sensible(c):
            return self.confirmations.demander(c)
        return executer(c, self.execution)

    def _choisir(self, texte: str) -> Reponse | None:
        """La réponse à « Notes ou Notion ? », ou None si la phrase n'en est pas une."""
        choix, self.choix = self.choix, []
        verdict, index = ambiguite.choisir(texte, [c.libelle for c in choix])
        if verdict == "abandon":
            return info("D'accord, je ne fais rien.")
        if verdict == "choisi" and index is not None:
            return self._faire(choix[index].comprehension)
        return None

    def entendre(self, texte: str) -> Reponse:
        r = self._entendre(texte)
        if r.intention != "controle.repeter" and r.statut not in ("rien", "stop"):
            self.etat.derniere = r
        if self.journal is not None and r.statut != "rien":
            self.journal.ajouter(texte, r.intention, r.statut, r.texte, self.o.maintenant())
        return r

    def _entendre(self, texte: str) -> Reponse:
        if self.choix:
            r = self._choisir(texte)
            if r is not None:
                return r
        c = comprendre(texte, self.contexte)
        if self.confirmations.attente is not None:
            if c.statut == "compris" and c.intention in ("controle.oui", "controle.non"):
                a_faire = self.confirmations.repondre(c.intention == "controle.oui")
                if a_faire is None:
                    return info("D'accord, je ne fais rien." if c.intention == "controle.non" else
                                "Trop tard : je n'ai rien fait.", c.intention)  # fmt: skip
                return executer(a_faire, self.execution)
            self.confirmations.abandonner()  # autre chose qu'un oui : l'action sensible est annulée
        if c.statut == "vide":
            return Reponse("rien", c.raison)
        if c.statut == "pas_compris":
            return Reponse("incompris", "Je n'ai pas compris.", None, {"suggestions": c.suggestions,
                                                                       "raison": c.raison})  # fmt: skip
        if c.statut in ("refus", "negation"):
            return Reponse("refus" if c.statut == "refus" else "info", c.raison, c.intention)
        if c.statut == "ambigu":
            self.choix = list(c.choix)
            return Reponse("choix", c.raison, c.intention, {"choix": [x.libelle for x in c.choix]})
        return self._faire(c)

    def tic(self) -> list[Reponse]:
        """Appelé chaque seconde par le moteur : confirmation expirée, minuteurs échus (notification)."""
        sorties: list[Reponse] = []
        expiree = self.confirmations.expirer()
        if expiree is not None:
            sorties.append(expiree)
        for m in self.minuteurs.echus(self.o.maintenant()):
            minuteur.notifier(self.o, m)
            texte = f"⏰ {m.message}" if m.message else "⏰ Minuteur terminé"
            sorties.append(Reponse("alerte", texte, "rappel.creer" if m.message else "minuteur.lancer"))
        return sorties
