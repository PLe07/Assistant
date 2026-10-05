"""L'inactivité : seulement le temps écoulé depuis ta dernière action (jamais l'action elle-même).
Au-delà de 10 minutes, la session est coupée (un événement « inactif »)."""

from __future__ import annotations

from modules.corvees.capteurs.base import Capteur


class Inactivite(Capteur):
    nom = "inactivite"
    intervalle = 5.0

    def demarrer(self) -> None:
        self.absent = False
        self.seuil = float(self.reglages["sessions"]["inactivite_min"]) * 60
        if self.natif is None:
            self.desactiver("pas sur un Mac")

    def relever(self, maintenant: float) -> None:
        if self.natif is None:
            return
        secondes = self.natif.inactivite()
        if secondes is None:
            self.degrader("macOS ne dit pas depuis quand tu n'as rien fait")
            return
        self.statut, self.detail = "ok", ""
        if secondes >= self.seuil and not self.absent:
            self.absent = True
            self.emettre(maintenant - secondes, "inactif", "inactif")
        elif secondes < self.seuil:
            self.absent = False

    @property
    def inactif_depuis(self) -> float:
        return float(self.natif.inactivite() or 0) if self.natif else 0.0
