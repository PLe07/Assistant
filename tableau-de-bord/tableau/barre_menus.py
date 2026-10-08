"""L'icône de la barre des menus (§5.2) : un point vert, orange ou rouge, et un menu court.

Le menu liste les modules avec leur pastille, puis « Ouvrir le tableau de bord », « Mettre les alertes en sourdine
1 h » (ou « Lever la sourdine ») et « Rapport de la semaine ». Ce fichier construit le **modèle** du menu et fait les
actions (testés partout) ; `barre_menus_natif.py` l'affiche avec rumps, sur le Mac seulement.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tableau import systeme, textes
from tableau.analyse import rapport_semaine
from tableau.module import EMOJI, EtatModule, Pastille
from tableau.vues import Source
from tableau.web import rendu

LONGUEUR_PHRASE = 48


@dataclass(frozen=True)
class Element:
    titre: str
    action: str | None = None  # ouvrir, sourdine, lever, rapport, module:<id> ; None : séparateur ou texte


def point(etats: list[EtatModule]) -> str:
    """Le point de l'icône : 🔴 si un module ne fait plus son travail, 🟠 si quelque chose est à regarder."""
    if any(e.pastille == Pastille.ROUGE for e in etats):
        return "🔴"
    if any(e.pastille == Pastille.JAUNE for e in etats):
        return "🟠"
    return "🟢"


def _court(texte: str) -> str:
    return texte if len(texte) <= LONGUEUR_PHRASE else texte[: LONGUEUR_PHRASE - 1].rstrip() + "…"


def modele(etats: list[EtatModule], sourdine_jusqua: float | None) -> tuple[str, list[Element]]:
    elements = [Element(f"{EMOJI[e.pastille]} {e.nom} — {_court(e.phrase)}", f"module:{e.id}") for e in etats]
    if not elements:
        elements.append(Element("Aucun module observé pour l'instant"))
    elements.append(Element("-"))
    elements.append(Element("Ouvrir le tableau de bord", "ouvrir"))
    if sourdine_jusqua is None:
        elements.append(Element("Mettre les alertes en sourdine 1 h", "sourdine"))
    else:
        elements.append(Element(f"Lever la sourdine (jusqu'à {textes.heure(sourdine_jusqua)})", "lever"))
    elements.append(Element("Rapport de la semaine", "rapport"))
    return point(etats), elements


def rapport_maintenant(source: Source, maintenant: float | None = None) -> Path:
    """Le rapport des 7 derniers jours, fait à la demande (le rapport du dimanche reste celui du dimanche)."""
    maintenant = source.horloge() if maintenant is None else maintenant
    r = rapport_semaine.construire(source.base, source.etats(), maintenant, maintenant)
    return rapport_semaine.ecrire(r, source.chemins.rapports / "a-la-demande")


class Actions:
    """Ce que fait chaque ligne du menu (aussi utilisé par la CLI)."""

    def __init__(
        self, source: Source, adresse: str, ouvrir: Callable[[list[str]], systeme.Resultat] | None = None
    ) -> None:
        self.source = source
        self.adresse = adresse
        self.ouvrir_commande = ouvrir or (lambda args: systeme.executer(args, delai=10))
        self._verrou = threading.Lock()

    def faire(self, action: str) -> str:
        with self._verrou:
            if action == "ouvrir":
                self.ouvrir_commande(["open", self.adresse])
                return "Tableau de bord ouvert."
            if action.startswith("module:"):
                ident = action.split(":", 1)[1]
                self.ouvrir_commande(["open", self.adresse.replace("/?", f"/module/{ident}?", 1)])
                return f"Page de {ident} ouverte."
            if action == "sourdine":
                return self.source.sourdine("1h")
            if action == "lever":
                return self.source.sourdine("fin")
            if action == "rapport":
                chemin = rapport_maintenant(self.source)
                self.ouvrir_commande(["open", str(chemin)])
                return f"Rapport ouvert ({chemin.name})."
        raise ValueError(f"action inconnue : {action}")


def adresse_page(port: int, jeton: str) -> str:
    return rendu.lien(f"http://127.0.0.1:{port}/", jeton)


def lancer(source: Source, adresse: str, arret: threading.Event) -> None:  # pragma: no cover - Mac seulement
    """Affiche l'icône (rumps, dans le fil principal) ; rend la main quand l'application se ferme."""
    from tableau import barre_menus_natif

    barre_menus_natif.Application(source, Actions(source, adresse), arret).run()
