"""Les notifications du Nettoyeur : au plus une par jour, jamais entre 23 h et 8 h (réglable). Une notification
retenue n'est pas perdue : elle attend le prochain moment permis (les nouveaux éléments passent avant le récap)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from modules.demarrage.db import Base, DisquePlein

log = logging.getLogger("demarrage")
TITRE = "Nettoyeur de démarrage"
PRIORITE = {"nouveau": 0, "recap": 1}


def par_l_assistant(titre: str, message: str) -> bool:
    from core.notifications import notifier

    return bool(notifier(titre, message, module="demarrage")[0])


def _minutes(hhmm: str) -> int:
    h, _, m = hhmm.partition(":")
    return int(h) * 60 + int(m or 0)


class Notifieur:
    def __init__(self, base: Base, reglages: dict[str, Any], envoyer: Callable[[str, str], bool] | None = None):
        self.base = base
        self.reglages = reglages["notifications"]
        self.envoyer = envoyer or par_l_assistant

    def en_silence(self, maintenant: float) -> bool:
        lt = time.localtime(maintenant)
        actuelle = lt.tm_hour * 60 + lt.tm_min
        debut, fin = _minutes(self.reglages["silence_debut"]), _minutes(self.reglages["silence_fin"])
        if debut == fin:
            return False
        return debut <= actuelle < fin if debut < fin else actuelle >= debut or actuelle < fin

    def deja_aujourdhui(self, maintenant: float) -> bool:
        derniere = self.base.lire("derniere_notification")
        return bool(derniere) and time.localtime(float(derniere))[:3] == time.localtime(maintenant)[:3]

    def proposer(self, genre: str, message: str, maintenant: float, elements: list[str] | None = None) -> bool:
        """Envoie maintenant si c'est permis ; sinon, garde-la pour plus tard. Renvoie True si elle est partie."""
        attente = self.base.lire("en_attente")
        if attente and attente["genre"] == genre == "nouveau":
            elements = list(dict.fromkeys([*attente.get("elements", []), *(elements or [])]))
            message = nouveaux_message(elements)
        elif attente and PRIORITE[attente["genre"]] < PRIORITE[genre]:
            return self.relancer(maintenant)  # un nouvel élément en attente passe avant le récap
        if self.en_silence(maintenant) or self.deja_aujourdhui(maintenant):
            self._garder({"genre": genre, "message": message, "elements": elements or [], "depuis": maintenant})
            return False
        return self._envoyer(genre, message, maintenant)

    def relancer(self, maintenant: float) -> bool:
        attente = self.base.lire("en_attente")
        if not attente or self.en_silence(maintenant) or self.deja_aujourdhui(maintenant):
            return False
        return self._envoyer(attente["genre"], attente["message"], maintenant)

    def _garder(self, attente: dict[str, Any]) -> None:
        try:
            self.base.ecrire("en_attente", attente)
        except DisquePlein:
            log.error("[demarrage] disque plein : notification perdue")

    def _envoyer(self, genre: str, message: str, maintenant: float) -> bool:
        if self.reglages["vers_journal"]:
            log.info("[demarrage] notification (journal seulement) : %s", message)
            envoye = True
        else:
            envoye = self.envoyer(TITRE, message)
        if envoye:
            try:
                self.base.ecrire("derniere_notification", maintenant)
                self.base.effacer("en_attente")
                with self.base.transaction() as db:
                    db.execute("INSERT INTO notifications (ts, genre, titre, texte) VALUES (?, ?, ?, ?)",
                               (maintenant, genre, TITRE, message))  # fmt: skip
            except DisquePlein:
                log.error("[demarrage] disque plein : notification envoyée mais pas notée")
        return envoye


def nouveaux_message(elements: list[str]) -> str:
    """elements : « Nom (Éditeur) »."""
    if len(elements) == 1:
        return f"⚠️ Nouveau programme au démarrage : {elements[0]}"
    liste = ", ".join(elements[:3]) + (f" et {len(elements) - 3} autre(s)" if len(elements) > 3 else "")
    return f"⚠️ {len(elements)} nouveaux programmes au démarrage : {liste}"
