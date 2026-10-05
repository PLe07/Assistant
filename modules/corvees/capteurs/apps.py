"""C1 — L'appli au premier plan (sans autorisation). Un événement à chaque changement d'appli.

Méthode : la liste des applis de macOS (NSWorkspace), relevée toutes les 2 secondes ; en secours, le propriétaire
de la fenêtre la plus en avant (mode dégradé).
"""

from __future__ import annotations

from modules.corvees.capteurs.base import PROCESSUS_SYSTEME, Capteur
from modules.corvees.normalize import tok_app


class Apps(Capteur):
    nom = "apps"
    intervalle = 2.0

    def demarrer(self) -> None:
        self.courante: str | None = None
        self.depuis = 0.0
        if self.natif is None:
            self.desactiver("pas sur un Mac")

    def relever(self, maintenant: float) -> None:
        if self.natif is None:
            return
        devant = self.natif.appli_devant()
        if devant is None:
            devant = self.natif.appli_devant_secours()
            if devant is None:
                self.degrader("macOS ne dit pas quelle appli est devant")
                return
            self.degrader("méthode de secours (fenêtre la plus en avant)")
        else:
            self.statut, self.detail = "ok", ""
        nom, bundle = devant
        if nom in PROCESSUS_SYSTEME:
            return  # Stage Manager, Dock… : pas une appli, on garde la précédente
        if nom and nom != self.courante:
            duree = round(maintenant - self.depuis, 1) if self.courante else None
            self.emettre(maintenant, "app", tok_app(nom), appli=nom, bundle=bundle, duree_precedente=duree)
            self.courante, self.depuis = nom, maintenant
