"""Un faux Mac pour les tests : chaque commande est notée, aucune n'est exécutée.

Il imite les notifications, la fenêtre de choix, `open`, `pbcopy`, `launchctl print` et l'app Rappels (des listes et
des rappels en mémoire, y compris celles d'autres projets, pour vérifier qu'on n'y touche jamais).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from typing import Any

from quotidien import rappels_apple
from quotidien.systeme import Resultat, Systeme


class FauxMac:
    def __init__(self, listes: dict[str, list[str]] | None = None, rappels_refuses: bool = False,
                 choix: str = "") -> None:  # fmt: skip
        self._n = itertools.count(1)
        self.listes: dict[str, list[dict[str, Any]]] = {
            nom: [{"id": self._id(), "titre": t, "note": "", "date": None} for t in titres]
            for nom, titres in (listes or {}).items()
        }
        self.rappels_refuses = rappels_refuses
        self.choix = choix
        self.appels: list[list[str]] = []
        self.entrees: list[str | None] = []
        self.notifications: list[tuple[str, str]] = []
        self.ouverts: list[str] = []
        self.launchctl: list[Resultat] = []

    def _id(self) -> str:
        return f"x-coredata://rappel/{next(self._n)}"

    def systeme(self) -> Systeme:
        return Systeme(self, mac=True)

    def etat_listes(self) -> dict[str, int]:
        return {nom: len(r) for nom, r in self.listes.items()}

    def __call__(self, args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        args = list(args)
        self.appels.append(args)
        self.entrees.append(entree)
        if args[:1] == ["osascript"]:
            script, argv = args[2], args[4:]
            if "display notification" in script:
                self.notifications.append((argv[0], argv[1]))
                return Resultat(0, "")
            if "choose from list" in script:
                return Resultat(0, self.choix)
            if 'tell application "Reminders"' in script:
                if self.rappels_refuses:
                    return Resultat(1, "", "execution error: Not authorized to send Apple events to Reminders. (-1743)")
                return self._rappels(script, argv)
            return Resultat(0, "")
        if args[:1] == ["open"]:
            self.ouverts.append(args[1])
            return Resultat(0, "")
        if args[:1] == ["launchctl"]:
            return self.launchctl.pop(0) if self.launchctl else Resultat(113, "", "Could not find service")
        return Resultat(0, "")

    def _rappels(self, script: str, argv: list[str]) -> Resultat:
        nom = argv[0]
        liste = self.listes.get(nom)
        if script == rappels_apple._EXISTE:
            return Resultat(0, "1" if liste is not None else "0")
        if script == rappels_apple._CREER_LISTE:
            self.listes.setdefault(nom, [])
            return Resultat(0, f"liste:{nom}")
        if script == rappels_apple._CREER:
            if liste is None:
                return Resultat(0, "")
            identifiant = self._id()
            date = tuple(int(x) for x in argv[4:9]) if argv[3] == "1" else None
            liste.append({"id": identifiant, "titre": argv[1], "note": argv[2], "date": date})
            return Resultat(0, identifiant)
        if script == rappels_apple._SUPPRIMER:
            if liste is None:
                return Resultat(0, "0")
            avant = len(liste)
            liste[:] = [r for r in liste if r["id"] not in argv[1:]]
            return Resultat(0, str(avant - len(liste)))
        if script == rappels_apple._COMPTER:
            return Resultat(0, str(len(liste)) if liste is not None else "-1")
        if script == rappels_apple._SUPPRIMER_LISTE:
            self.listes.pop(nom, None)
            return Resultat(0, "ok")
        return Resultat(1, "", "script inconnu du faux Mac")
