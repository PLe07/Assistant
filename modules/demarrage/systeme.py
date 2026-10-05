"""Tout ce qui parle au vrai Mac, isolé ici : lancer une commande (sans shell, avec un délai), situer un fichier,
connaître l'heure, attendre. Les tests le remplacent par un faux Mac (tests/demarrage/faux_mac).

Garde-fous : jamais de shell, jamais de droits d'administrateur (une commande qui commence par « sudo » est
refusée avant même d'être lancée), toujours un délai maximum.
"""

from __future__ import annotations

import getpass
import os
import resource
import shutil
import subprocess
import sys
import threading
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


def _processeur_des_enfants() -> float:
    u = resource.getrusage(resource.RUSAGE_CHILDREN)
    return u.ru_utime + u.ru_stime


class Mac:
    """Le vrai Mac. Il tient aussi le compte de ce que chaque commande a coûté (couts()), pour la mesure du démon."""

    def __init__(self) -> None:
        self.racine = Path("/")
        self.maison = str(Path.home())
        self.uid = os.getuid()
        self.utilisateur = getpass.getuser()
        self._couts: dict[str, list[float]] = {}  # commande → [appels, secondes de processeur, secondes réelles]
        self._verrou = threading.Lock()

    def couts(self) -> dict[str, dict[str, float]]:
        """Par commande : appels, processeur (s), temps réel (s). Le processeur vient de getrusage(RUSAGE_CHILDREN) :
        exact quand les commandes passent une à une (le démon), approché quand elles tournent en parallèle (scan)."""
        with self._verrou:
            par_commande = {
                nom: {"appels": int(n), "processeur_s": round(cpu, 3), "reel_s": round(reel, 2)}
                for nom, (n, cpu, reel) in sorted(self._couts.items(), key=lambda c: -c[1][1])
            }
        rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        par_commande["(plus grosse commande)"] = {
            "memoire_mo": round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
        }
        return par_commande

    def _compter(self, commande: list[str], cpu_avant: float, debut: float) -> None:
        nom = (
            " ".join([Path(commande[0]).name, *commande[1:2]])
            if Path(commande[0]).name == "launchctl"
            else Path(commande[0]).name
        )
        with self._verrou:
            n, cpu, reel = self._couts.get(nom, [0, 0.0, 0.0])
            self._couts[nom] = [
                n + 1,
                cpu + max(0.0, _processeur_des_enfants() - cpu_avant),
                reel + time.perf_counter() - debut,
            ]

    def chemin(self, absolu: str | Path) -> Path:
        return Path(absolu)

    def executer(self, commande: list[str], delai: float = 10.0, env: dict[str, str] | None = None) -> Resultat:
        verifier_commande(commande)
        environnement = {**os.environ, **env} if env else None
        debut, cpu_avant = time.perf_counter(), _processeur_des_enfants()
        try:
            proc = subprocess.run(
                commande, capture_output=True, text=True, errors="replace", timeout=delai, env=environnement
            )
        except FileNotFoundError:
            return Resultat(127, "", f"{commande[0]} : commande introuvable")
        except subprocess.TimeoutExpired:
            self._compter(commande, cpu_avant, debut)
            return Resultat(124, "", f"{commande[0]} : pas de réponse en {delai:.0f} s", delai)
        except OSError as e:
            return Resultat(126, "", f"{commande[0]} : {e}")
        self._compter(commande, cpu_avant, debut)
        return Resultat(proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - debut)

    def maintenant(self) -> float:
        return time.time()

    def attendre(self, secondes: float) -> None:
        time.sleep(max(0.0, secondes))

    def a_la_commande(self, nom: str) -> bool:
        return shutil.which(nom) is not None
