"""Ce que tous les capteurs partagent : un relevé régulier, un état de santé, et l'échec propre.

Un capteur qui plante ne fait rien tomber : il passe « dégradé », le démon le relance avec un délai croissant.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

from modules.corvees.db import Evenement

Sortie = Callable[[Evenement], None]


class Memoire(Protocol):
    """Où un capteur garde ses curseurs (la base du détecteur)."""

    def lire(self, cle: str, defaut: Any = None) -> Any: ...

    def ecrire(self, cle: str, valeur: Any) -> None: ...


class MemoireVive:
    """Une mémoire sans disque, pour les essais."""

    def __init__(self) -> None:
        self.valeurs: dict[str, Any] = {}

    def lire(self, cle: str, defaut: Any = None) -> Any:
        return self.valeurs.get(cle, defaut)

    def ecrire(self, cle: str, valeur: Any) -> None:
        self.valeurs[cle] = valeur


class Capteur:
    nom = "capteur"
    intervalle = 5.0  # secondes entre deux relevés

    def __init__(self, reglages: dict[str, Any], sortie: Sortie, memoire: Memoire | None = None, natif: Any = None):
        self.reglages = reglages
        self.sortie = sortie
        self.memoire = memoire or MemoireVive()
        self.natif = natif
        self.statut = "ok"  # ok, dégradé, désactivé
        self.detail = ""
        self.dernier_releve = 0.0
        self.erreurs = 0

    # À redéfinir
    def demarrer(self) -> None:
        """Prépare le capteur (ouvre une surveillance, vérifie une autorisation…)."""

    def arreter(self) -> None:
        """Libère ce qui a été ouvert. Doit pouvoir être appelé plusieurs fois."""

    def relever(self, maintenant: float) -> None:
        """Un relevé : regarde ce qui a changé et l'envoie à la sortie."""

    # Commun
    def emettre(self, ts: float, kind: str, token: str, **attrs: Any) -> None:
        self.sortie(Evenement(ts, self.nom, kind, token, attrs))

    def degrader(self, detail: str) -> None:
        self.statut, self.detail = "dégradé", detail

    def desactiver(self, detail: str) -> None:
        self.statut, self.detail = "désactivé", detail

    def sante(self) -> dict[str, Any]:
        return {
            "capteur": self.nom,
            "statut": self.statut,
            "detail": self.detail,
            "dernier_releve": self.dernier_releve,
        }


def maintenant() -> float:
    return time.time()
