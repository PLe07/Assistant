"""Ce que Bouclier demande au Mac, derrière une seule interface.

Tout passe par `executer` (une commande, sa sortie) : les tests le remplacent par une imitation qui enregistre
chaque appel, ce qui vérifie les commandes construites sans Mac. Rien ici ne touche aux autres projets.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Resultat:
    code: int
    sortie: str
    erreur: str = ""


Executeur = Callable[[Sequence[str], str | None, float], Resultat]


def executer_vraiment(args: Sequence[str], entree: str | None = None, delai: float = 60) -> Resultat:
    try:
        r = subprocess.run(list(args), input=entree, capture_output=True, text=True, timeout=delai)
    except FileNotFoundError:
        return Resultat(127, "", f"{args[0]} introuvable")
    except (OSError, subprocess.TimeoutExpired) as e:
        return Resultat(124, "", f"{args[0]} : {e.__class__.__name__}")
    return Resultat(r.returncode, r.stdout, r.stderr)


_NOTIFIER = [
    "on run argv",
    "display notification (item 2 of argv) with title (item 1 of argv) subtitle (item 3 of argv)",
    "end run",
]
_CORBEILLE_FINDER = [
    "on run argv",
    'tell application "Finder" to delete (POSIX file (item 1 of argv) as alias)',
    "end run",
]
_DIALOGUE = [
    "on run argv",
    'display dialog (item 2 of argv) with title (item 1 of argv) buttons {"OK"} default button "OK"',
    "end run",
]


def _osascript(lignes: list[str], *args: str) -> list[str]:
    commande = ["osascript"]
    for ligne in lignes:
        commande += ["-e", ligne]
    return [*commande, "--", *args]


class Systeme:
    def __init__(self, executeur: Executeur | None = None, mac: bool | None = None) -> None:
        self.executer: Executeur = executeur or executer_vraiment
        self.mac = platform.system() == "Darwin" if mac is None else mac

    # --- Notifications et fenêtres -------------------------------------------------------------------------------
    def notifier(self, titre: str, texte: str, sous_titre: str = "") -> bool:
        if not self.mac:
            return False
        return self.executer(_osascript(_NOTIFIER, titre, texte, sous_titre), None, 20).code == 0

    def dialogue(self, titre: str, texte: str) -> bool:
        if not self.mac:
            return False
        return self.executer(_osascript(_DIALOGUE, titre, texte), None, 600).code == 0

    def ouvrir(self, chemin: Path) -> bool:
        commande = ["open", str(chemin)] if self.mac else ["xdg-open", str(chemin)]
        return self.executer(commande, None, 20).code == 0

    def ouvrir_editeur(self, chemin: Path) -> bool:
        commande = ["open", "-t", str(chemin)] if self.mac else ["xdg-open", str(chemin)]
        return self.executer(commande, None, 20).code == 0

    def presse_papiers(self) -> str:
        r = self.executer(["pbpaste"] if self.mac else ["xclip", "-o", "-selection", "clipboard"], None, 10)
        return r.sortie if r.code == 0 else ""

    # --- Trousseau (lecture ; écriture seulement de nos propres éléments) ----------------------------------------
    def trousseau_lire(self, service: str, compte: str | None = None) -> str | None:
        """Seulement nos propres éléments (bouclier-…) : aucun autre secret du trousseau n'est jamais lu."""
        if not self.mac or not service.startswith("bouclier-"):
            return None
        commande = ["security", "find-generic-password", "-s", service]
        if compte:
            commande += ["-a", compte]
        r = self.executer([*commande, "-w"], None, 20)
        return r.sortie.rstrip("\n") if r.code == 0 and r.sortie.strip() else None

    def trousseau_ecrire_interactif(self, service: str, compte: str) -> bool:
        """Seulement pour nos éléments (bouclier-…). `security` te demande lui-même le secret dans le Terminal :
        il ne passe jamais par Bouclier ni par la liste des processus. « -U » met à jour notre propre élément."""
        if not self.mac or not service.startswith("bouclier-"):
            return False
        return self.interactif(["security", "add-generic-password", "-U", "-s", service, "-a", compte, "-w"]) == 0

    def interactif(self, args: Sequence[str]) -> int:
        try:
            return subprocess.call(list(args))
        except OSError:
            return 127

    # --- iCloud ------------------------------------------------------------------------------------------------
    def telecharger_icloud(self, chemin: Path) -> bool:
        if not self.mac:
            return False
        return self.executer(["brctl", "download", str(chemin)], None, 60).code == 0

    def permettre_icloud(self) -> bool:
        """Le démon a le droit de faire venir les fichiers iCloud qu'il lit (leçon du Trieur, D-60)."""
        if not self.mac:
            return False
        try:
            import ctypes

            libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
            # sys/resource.h : IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES=3, IOPOL_SCOPE_PROCESS=0, ..._ON=2
            return bool(libc.setiopolicy_np(3, 0, 2) == 0)
        except (OSError, AttributeError):
            return False

    # --- Corbeille ----------------------------------------------------------------------------------------------
    def corbeille(self, chemin: Path) -> bool:
        """À la Corbeille par l'API du Mac (jamais `rm`) : NSFileManager, sinon le Finder."""
        if not self.mac:
            return False
        try:
            from Foundation import NSURL, NSFileManager

            ok, _, _ = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
                NSURL.fileURLWithPath_(str(chemin)), None, None
            )
            if ok:
                return True
        except ImportError:
            pass
        return self.executer(_osascript(_CORBEILLE_FINDER, str(chemin)), None, 60).code == 0

    # --- Outils ------------------------------------------------------------------------------------------------
    def commande_existe(self, nom: str) -> bool:
        return shutil.which(nom) is not None
