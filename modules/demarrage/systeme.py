"""Tout ce qui parle au vrai Mac, isolé ici : lancer une commande (sans shell, avec un délai), situer un fichier,
connaître l'heure, attendre. Les tests le remplacent par un faux Mac (tests/demarrage/faux_mac).

Garde-fous : jamais de shell, jamais de droits d'administrateur (une commande qui commence par « sudo » est
refusée avant même d'être lancée), toujours un délai maximum.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Resultat:
    code: int
    sortie: str
    erreur: str = ""
    duree_s: float = 0.0  # temps réel écoulé (sert à chronométrer zsh)

    @property
    def ok(self) -> bool:
        return self.code == 0


class RefusAdministrateur(Exception):
    """Une commande a voulu des droits d'administrateur : refusée, jamais lancée."""


class Systeme(Protocol):
    """Ce dont les collecteurs, la mesure et les actions ont besoin du Mac."""

    racine: Path  # « / » sur le vrai Mac, un dossier temporaire pour le faux Mac
    maison: str  # le dossier personnel, tel que le Mac l'écrit (/Users/…)
    uid: int
    utilisateur: str

    def chemin(self, absolu: str | Path) -> Path: ...

    def executer(self, commande: list[str], delai: float = 10.0, env: dict[str, str] | None = None) -> Resultat: ...

    def maintenant(self) -> float: ...

    def attendre(self, secondes: float) -> None: ...

    def a_la_commande(self, nom: str) -> bool: ...


def verifier_commande(commande: list[str]) -> None:
    if not commande:
        raise ValueError("commande vide")
    if Path(commande[0]).name in ("sudo", "su", "doas"):
        raise RefusAdministrateur(f"refusé : {commande[0]} (le Nettoyeur n'agit jamais en administrateur)")


class Mac:
    """Le vrai Mac."""

    def __init__(self) -> None:
        self.racine = Path("/")
        self.maison = str(Path.home())
        self.uid = os.getuid()
        self.utilisateur = getpass.getuser()

    def chemin(self, absolu: str | Path) -> Path:
        return Path(absolu)

    def executer(self, commande: list[str], delai: float = 10.0, env: dict[str, str] | None = None) -> Resultat:
        verifier_commande(commande)
        environnement = {**os.environ, **env} if env else None
        debut = time.perf_counter()
        try:
            proc = subprocess.run(
                commande, capture_output=True, text=True, errors="replace", timeout=delai, env=environnement
            )
        except FileNotFoundError:
            return Resultat(127, "", f"{commande[0]} : commande introuvable")
        except subprocess.TimeoutExpired:
            return Resultat(124, "", f"{commande[0]} : pas de réponse en {delai:.0f} s", delai)
        except OSError as e:
            return Resultat(126, "", f"{commande[0]} : {e}")
        return Resultat(proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - debut)

    def maintenant(self) -> float:
        return time.time()

    def attendre(self, secondes: float) -> None:
        time.sleep(max(0.0, secondes))

    def a_la_commande(self, nom: str) -> bool:
        return shutil.which(nom) is not None
