"""Ce que le Trieur demande au Mac, derrière une seule interface (D-04) : les tags du Finder, les alias, les coins
d'un document photographié, les rappels de l'app Rappels, le téléchargement d'un fichier iCloud.

- `Mac` : le vrai, par PyObjC (natif.py), osascript et brctl.
- `Simple` : ailleurs (ou si une autorisation manque) : un lien symbolique tient lieu d'alias, le reste est noté.
Les tests utilisent une imitation qui enregistre chaque appel.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Protocol

from core.journal import journal

log = journal("trieur")


class Systeme(Protocol):
    nom: str

    def poser_tags(self, chemin: Path, tags: list[str]) -> bool: ...

    def creer_alias(self, cible: Path, alias: Path) -> bool: ...

    def coins(self, image: Path) -> list[tuple[float, float]] | None: ...

    def rappel_creer(self, liste: str, titre: str, quand: datetime, note: str = "") -> str | None: ...

    def rappel_supprimer(self, liste: str, identifiant: str) -> bool: ...

    def telecharger_icloud(self, chemin: Path) -> bool: ...

    def quarantaine(self, chemin: Path) -> str: ...


def _lien(cible: Path, alias: Path) -> bool:
    try:
        alias.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(cible, alias)
        return True
    except OSError as e:
        log.warning("alias impossible (%s) : %s", alias.name, e)
        return False


class Simple:
    """Hors du Mac : rien de natif, mais rien ne plante."""

    nom = "simple"

    def poser_tags(self, chemin: Path, tags: list[str]) -> bool:
        return False

    def creer_alias(self, cible: Path, alias: Path) -> bool:
        return _lien(cible, alias)

    def coins(self, image: Path) -> list[tuple[float, float]] | None:
        return None

    def rappel_creer(self, liste: str, titre: str, quand: datetime, note: str = "") -> str | None:
        log.info("rappel non créé (pas sur un Mac) : %s le %s", titre, quand.date())
        return None

    def rappel_supprimer(self, liste: str, identifiant: str) -> bool:
        return False

    def telecharger_icloud(self, chemin: Path) -> bool:
        return False

    def quarantaine(self, chemin: Path) -> str:
        return ""


# Le script AppleScript des Rappels : les valeurs passent en arguments (jamais collées dans le code du script).
# Toutes les variables commencent par « v » : des mots comme « note » (une icône de Standard Additions) ou « an »
# (un article) sont réservés en AppleScript, et « set note to … » échoue (« Accès non autorisé », -10003).
_RAPPEL_CREER = """on run argv
  set vListe to item 1 of argv
  set vTitre to item 2 of argv
  set vCorps to item 3 of argv
  set vAnnee to (item 4 of argv) as integer
  set vMois to (item 5 of argv) as integer
  set vJour to (item 6 of argv) as integer
  set vHeure to (item 7 of argv) as integer
  set vMinute to (item 8 of argv) as integer
  set vDate to current date
  set day of vDate to 1
  set year of vDate to vAnnee
  set month of vDate to vMois
  set day of vDate to vJour
  set hours of vDate to vHeure
  set minutes of vDate to vMinute
  set seconds of vDate to 0
  tell application "Reminders"
    if not (exists list vListe) then make new list with properties {name:vListe}
    set vProprietes to {name:vTitre, body:vCorps, remind me date:vDate}
    set vRappel to make new reminder at end of list vListe with properties vProprietes
    return id of vRappel
  end tell
end run"""
_RAPPEL_SUPPRIMER = """on run argv
  set vListe to item 1 of argv
  set vIdentifiant to item 2 of argv
  tell application "Reminders"
    if not (exists list vListe) then return "0"
    set vTrouves to (every reminder of list vListe whose id is vIdentifiant)
    repeat with vRappel in vTrouves
      delete vRappel
    end repeat
    return (count of vTrouves) as text
  end tell
end run"""


class Mac(Simple):
    nom = "mac"

    def poser_tags(self, chemin: Path, tags: list[str]) -> bool:
        try:
            from modules.trieur import natif

            return natif.poser_tags(chemin, tags)
        except Exception as e:
            log.warning("tags impossibles : %s", e)
            return False

    def creer_alias(self, cible: Path, alias: Path) -> bool:
        try:
            from modules.trieur import natif

            alias.parent.mkdir(parents=True, exist_ok=True)
            if natif.creer_alias(cible, alias):
                return True
        except Exception as e:
            log.warning("alias du Finder impossible, lien symbolique à la place : %s", e)
        return _lien(cible, alias)

    def coins(self, image: Path) -> list[tuple[float, float]] | None:
        try:
            from modules.trieur import natif

            return natif.coins_du_document(image)
        except Exception:
            return None

    def _osascript(self, script: str, *arguments: str) -> str | None:
        try:
            r = subprocess.run(["osascript", "-e", script, *arguments], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("Rappels injoignable : %s", e)
            return None
        if r.returncode != 0:
            log.warning("Rappels a refusé : %s", r.stderr.strip()[:200])
            return None
        return r.stdout.strip()

    def rappel_creer(self, liste: str, titre: str, quand: datetime, note: str = "") -> str | None:
        valeurs = [str(v) for v in (quand.year, quand.month, quand.day, quand.hour, quand.minute)]
        return self._osascript(_RAPPEL_CREER, liste, titre, note, *valeurs) or None

    def rappel_supprimer(self, liste: str, identifiant: str) -> bool:
        return (self._osascript(_RAPPEL_SUPPRIMER, liste, identifiant) or "0") != "0"

    def telecharger_icloud(self, chemin: Path) -> bool:
        """« brctl download » : iCloud remplace le fichier fantôme (.nom.icloud) par le vrai."""
        if not shutil.which("brctl"):
            return False
        try:
            r = subprocess.run(["brctl", "download", str(chemin)], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0

    def quarantaine(self, chemin: Path) -> str:
        """L'attribut de quarantaine (qui a apporté le fichier : « sharingd » pour AirDrop, un navigateur…)."""
        try:
            r = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(chemin)], capture_output=True, text=True,
                               timeout=5)  # fmt: skip
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return r.stdout.strip() if r.returncode == 0 else ""


def choisir() -> Systeme:
    return Mac() if sys.platform == "darwin" else Simple()
