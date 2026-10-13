"""La confirmation vocale des actions sensibles : « Tu confirmes ? », réponse « oui » ou « non » dans le délai
(5 s par défaut) ; sans réponse, ou si tu dis autre chose, l'action est **annulée**.

Sensibles : la mise en veille, « ferme tout » (et « ferme tout sauf »), le Wi-Fi coupé, et toute routine marquée
`sensible = true`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from voix.actions.base import Reponse, info
from voix.nlu.comprendre import Comprehension
from voix.nlu.intentions import INTENTIONS

QUESTIONS = {
    "systeme.veille": "Je mets le Mac en veille, tu confirmes ?",
    "app.fermer_tout": "Je ferme toutes les apps, tu confirmes ?",
    "app.fermer_tout_sauf": "Je ferme toutes les apps sauf {objet}, tu confirmes ?",
    "systeme.wifi_desactiver": "Je coupe le Wi-Fi, tu confirmes ?",
    "routine.lancer": "Je lance la routine « {objet} », tu confirmes ?",
}


@dataclass
class Attente:
    comprehension: Comprehension
    echeance: float


class Confirmations:
    def __init__(self, delai_s: float, horloge: Callable[[], float] = time.monotonic) -> None:
        self.delai_s = delai_s
        self.horloge = horloge
        self.attente: Attente | None = None

    def demander(self, c: Comprehension) -> Reponse:
        self.attente = Attente(c, self.horloge() + self.delai_s)
        objet = c.params.get("objet")
        modele = QUESTIONS.get(c.intention or "", "{libelle} : tu confirmes ?")
        libelle = INTENTIONS[c.intention].titre if c.intention in INTENTIONS else "Cette action"
        texte = modele.format(objet=getattr(objet, "nom", ""), libelle=libelle)
        return Reponse("question", texte, c.intention, {"delai_s": self.delai_s})

    def en_attente(self) -> bool:
        return self.attente is not None and self.horloge() <= self.attente.echeance

    def repondre(self, oui: bool) -> Comprehension | None:
        """L'action à faire si c'est « oui » dans le délai ; None sinon (et l'attente est oubliée)."""
        a, self.attente = self.attente, None
        if a is None or self.horloge() > a.echeance or not oui:
            return None
        return a.comprehension

    def abandonner(self) -> None:
        self.attente = None

    def expirer(self) -> Reponse | None:
        """Appelé régulièrement : le délai est passé sans réponse → l'action est annulée, et on le dit."""
        if self.attente is not None and self.horloge() > self.attente.echeance:
            intention = self.attente.comprehension.intention
            self.attente = None
            return info("Pas de réponse : je ne fais rien.", intention)
        return None
