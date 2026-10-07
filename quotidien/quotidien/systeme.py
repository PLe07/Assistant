"""Ce que Quotidien demande au Mac, derrière une seule interface.

Tout passe par `executer` (une commande, sa sortie) : les tests le remplacent par une imitation qui enregistre chaque
appel, ce qui vérifie les commandes construites sans Mac. Ici, rien n'envoie de message à qui que ce soit : on
**ouvre** Messages avec un texte prérempli (l'envoi reste ton geste), on copie dans le presse-papiers, on notifie.

Les scripts AppleScript reçoivent toutes les valeurs en arguments (jamais collées dans le code du script) et leurs
variables commencent par « v » (leçon du Trieur, D-54 : « note », « an »… sont des mots réservés).
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass


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


_NOTIFIER = """on run argv
  set vTitre to item 1 of argv
  set vTexte to item 2 of argv
  set vSousTitre to item 3 of argv
  display notification vTexte with title vTitre subtitle vSousTitre
end run"""

_CHOISIR = (
    "on run argv\n"
    "  set vTitre to item 1 of argv\n"
    "  set vInvite to item 2 of argv\n"
    "  set vBouton to item 3 of argv\n"
    "  set vChoix to items 4 thru -1 of argv\n"
    "  set vReponse to choose from list vChoix with title vTitre with prompt vInvite"
    ' OK button name vBouton cancel button name "Plus tard"\n'
    '  if vReponse is false then return ""\n'
    "  return item 1 of vReponse\n"
    "end run"
)

PREFIXE_TROUSSEAU = "quotidien-"


def _osascript(script: str, *args: str) -> list[str]:
    return ["osascript", "-e", script, "--", *args]


class Systeme:
    def __init__(self, executeur: Executeur | None = None, mac: bool | None = None) -> None:
        self.executer: Executeur = executeur or executer_vraiment
        self.mac = platform.system() == "Darwin" if mac is None else mac

    # --- Notifications et fenêtres ------------------------------------------------------------------------------
    def notifier(self, titre: str, texte: str, sous_titre: str = "") -> bool:
        if not self.mac:
            return False
        return self.executer(_osascript(_NOTIFIER, titre, texte, sous_titre), None, 20).code == 0

    def choisir(self, titre: str, invite: str, bouton: str, choix: list[str], delai: float = 900) -> str | None:
        """Une liste où tu choisis (ex. une des 3 variantes d'un message). None : fermé ou « Plus tard »."""
        if not self.mac or not choix:
            return None
        r = self.executer(_osascript(_CHOISIR, titre, invite, bouton, *choix), None, delai)
        return r.sortie.strip() or None if r.code == 0 else None

    def ouvrir(self, cible: str) -> bool:
        commande = ["open", cible] if self.mac else ["xdg-open", cible]
        return self.executer(commande, None, 20).code == 0

    def copier(self, texte: str) -> bool:
        """Dans le presse-papiers (pbcopy lit l'entrée standard : aucun texte dans la ligne de commande)."""
        if not self.mac:
            return False
        return self.executer(["pbcopy"], texte, 10).code == 0

    def ouvrir_messages(self, texte: str, destinataire: str = "") -> bool:
        """Ouvre Messages avec le texte prérempli (URL `sms:` avec `body`) et le copie aussi dans le presse-papiers.
        Rien n'est envoyé : c'est toi qui appuies sur Envoyer."""
        self.copier(texte)
        return self.ouvrir(url_sms(texte, destinataire))

    # --- Trousseau (lecture seule, et seulement nos propres éléments) ------------------------------------------
    def trousseau_lire(self, service: str) -> str | None:
        """Seulement nos éléments (quotidien-…) : aucun autre secret du trousseau n'est jamais lu."""
        if not self.mac or not service.startswith(PREFIXE_TROUSSEAU):
            return None
        r = self.executer(["security", "find-generic-password", "-s", service, "-w"], None, 20)
        return r.sortie.rstrip("\n") if r.code == 0 and r.sortie.strip() else None

    # --- AppleScript générique (Rappels) ----------------------------------------------------------------------
    def applescript(self, script: str, *args: str, delai: float = 60) -> Resultat:
        if not self.mac:
            return Resultat(127, "", "AppleScript n'existe que sur Mac")
        return self.executer(_osascript(script, *args), None, delai)

    def commande_existe(self, nom: str) -> bool:
        return shutil.which(nom) is not None


def url_sms(texte: str, destinataire: str = "") -> str:
    """`sms:<numéro>&body=<texte>` : la forme comprise par Messages sur iPhone et sur Mac."""
    numero = "".join(c for c in destinataire if c.isdigit() or c == "+")
    return f"sms:{numero}&body={urllib.parse.quote(texte, safe='')}"
