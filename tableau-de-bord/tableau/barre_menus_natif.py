"""L'icône de la barre des menus, dessinée par rumps (Mac seulement, dans la session graphique).

Le modèle et les actions sont dans `barre_menus.py` (testés partout) ; ici, seulement le lien avec rumps : un minuteur
relit l'état toutes les 10 s et reconstruit le menu s'il a changé. Pas de bouton « Quitter » : le démon est gardé en
vie par launchd (`tableau` dans le Terminal pour tout le reste).
"""

from __future__ import annotations

import threading
from typing import Any

import rumps

from tableau import barre_menus
from tableau.vues import Source


class Application(rumps.App):
    def __init__(self, source: Source, actions: barre_menus.Actions, arret: threading.Event) -> None:
        super().__init__("Tableau de bord", title="🟢", quit_button=None)
        self.source = source
        self.actions = actions
        self.arret = arret
        self._modele: Any = None
        self.minuteur = rumps.Timer(self.rafraichir, 10)
        self.minuteur.start()
        self.rafraichir(None)

    def rafraichir(self, _minuteur: Any) -> None:
        if self.arret.is_set():
            rumps.quit_application()
            return
        titre, elements = barre_menus.modele(self.source.etats(), self.source.alertes.sourdine_jusqua())
        if (titre, elements) == self._modele:
            return
        self._modele = (titre, elements)
        self.title = titre
        self.menu.clear()
        for e in elements:
            if e.titre == "-":
                self.menu.add(rumps.separator)
            elif e.action is None:
                self.menu.add(rumps.MenuItem(e.titre))
            else:
                self.menu.add(rumps.MenuItem(e.titre, callback=self._rappel(e.action)))

    def _rappel(self, action: str) -> Any:
        def faire(_element: Any) -> None:
            try:
                self.actions.faire(action)
            except Exception as e:  # noqa: BLE001 - un clic ne fait jamais tomber l'icône
                rumps.notification("Tableau de bord", "Action impossible", str(e)[:120])
            self._modele = None
            self.rafraichir(None)

        return faire
