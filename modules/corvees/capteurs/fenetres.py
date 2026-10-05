"""C2 — Le titre de la fenêtre au premier plan, seulement avec l'autorisation « Accessibilité ».

Le titre est normalisé (les nombres deviennent *) puis caviardé et filtré (banque, santé, mot de passe…) avant
toute écriture. Sans l'autorisation, ce capteur est désactivé et `corvees doctor` le dit.
"""

from __future__ import annotations

from modules.corvees.capteurs.base import Capteur
from modules.corvees.normalize import tok_fenetre


class Fenetres(Capteur):
    nom = "fenetres"
    intervalle = 5.0

    def __init__(self, *args, apps=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.apps = apps  # le capteur C1, pour savoir dans quelle appli est la fenêtre

    def demarrer(self) -> None:
        self.dernier: str | None = None
        if self.natif is None:
            self.desactiver("pas sur un Mac")
        elif not self.natif.accessibilite():
            self.desactiver("autorisation « Accessibilité » non accordée (voir ACTIONS_HUMAINES.md)")

    def relever(self, maintenant: float) -> None:
        if self.natif is None:
            return
        if not self.natif.accessibilite():  # retirée en cours de route : on s'arrête
            self.desactiver("autorisation « Accessibilité » non accordée (voir ACTIONS_HUMAINES.md)")
            return
        self.statut, self.detail = "ok", ""
        titre = self.natif.titre_fenetre()
        appli = getattr(self.apps, "courante", None) or ""
        if not titre or not appli:
            return
        token = tok_fenetre(appli, titre)
        if token != self.dernier:
            self.emettre(maintenant, "fen", token, appli=appli)
            self.dernier = token
