"""`demarrage restaurer ID` : défait exactement la dernière action notée au journal pour cet élément (simulation
sans `--confirmer`, comme `desactiver`). L'état actuel est relu d'abord : ce qui est déjà revenu n'est pas refait.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from modules.demarrage.actions import quarantaine
from modules.demarrage.actions.desactiver import applescript, etat_launchd
from modules.demarrage.actions.journal import Action, Journal
from modules.demarrage.systeme import Systeme


@dataclass
class Retour:
    fait: bool
    message: str
    commandes: list[list[str]] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


def _commandes(a: Action, systeme: Systeme) -> tuple[list[list[str]], bool]:
    """(commandes à lancer, fichier à sortir de quarantaine ?) d'après le journal et l'état actuel."""
    if a.genre == "system_events":
        app = a.details.get("app")
        proprietes = f"{{path:{applescript(str(app))}, hidden:false}}"
        script = f'tell application "System Events" to make login item at end with properties {proprietes}'
        return [["osascript", "-e", script]], False
    domaine = str(a.details.get("domaine") or f"gui/{systeme.uid}")
    chemin = a.details.get("chemin_plist")
    etat = etat_launchd(systeme, a.label)
    commandes: list[list[str]] = []
    if not a.avant.get("desactive") and etat["desactive"]:
        commandes.append(["launchctl", "enable", f"{domaine}/{a.label}"])
    sortir = a.genre == "quarantaine" and bool(a.details.get("quarantaine"))
    if sortir and not (Path(str(a.details["quarantaine"])) / quarantaine.MANIFESTE).exists():
        sortir = False  # déjà ressorti
    if a.avant.get("charge") and not etat["charge"] and chemin:
        commandes.append(["launchctl", "bootstrap", domaine, str(chemin)])
    return commandes, sortir


def restaurer(fiche_id: str, systeme: Systeme, journal: Journal, confirmer: bool = False) -> Retour:
    a = journal.a_annuler(fiche_id)
    if a is None:
        return Retour(
            False, "Rien à restaurer : aucune action en cours sur cet élément (voir « demarrage historique »)."
        )
    commandes, sortir = _commandes(a, systeme)
    if not commandes and not sortir:
        if confirmer:
            journal.annuler(a.id, systeme.maintenant())
        return Retour(
            False, "Rien à faire : il est déjà revenu comme avant." + (" Noté au journal." if confirmer else "")
        )
    resume = ([f"remettre {a.details.get('chemin_plist')} (depuis la quarantaine)"] if sortir else []) + [
        shlex.join(c) for c in commandes
    ]
    if not confirmer:
        return Retour(False, "Simulation : rien n'a été modifié. Je ferais :\n   " + "\n   ".join(resume), commandes)
    erreurs: list[str] = []
    if sortir:
        try:
            quarantaine.remettre(systeme, Path(str(a.details["quarantaine"])))
        except (OSError, ValueError) as e:
            return Retour(False, f"Je ne peux pas remettre le fichier : {e}", erreurs=[str(e)])
    for c in commandes:
        r = systeme.executer(c, delai=15)
        if not r.ok:
            erreurs.append(f"{shlex.join(c)} : {r.erreur.strip()[:200] or f'code {r.code}'}")
            break
    if erreurs:
        return Retour(False, "Restauration incomplète.", commandes, erreurs)
    journal.annuler(a.id, systeme.maintenant())
    return Retour(True, "C'est restauré : " + " ; ".join(resume), commandes)
