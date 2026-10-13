"""Lancer un programme de la liste blanche, et rien d'autre.

- La parole ne construit jamais une commande : chaque action choisit un **programme de la liste** et lui passe des
  **arguments validés**, un par un (jamais de shell, jamais de chaîne interprétée).
- Les programmes sont cherchés dans des dossiers fixes : ceux du système pour `open`, `osascript`… ; ceux de tes
  modules (`~/.local/bin`, Homebrew) pour `tableau`, `ambiance`… Un programme hors liste est refusé.
- Délai maximum pour chaque lancement ; la sortie est bornée.
Dans les tests, les dossiers pointent vers de faux exécutables qui notent ce qu'ils reçoivent.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Programmes du système, et ce qu'ils servent à faire.
SYSTEME: dict[str, str] = {
    "open": "ouvrir une app, un dossier, un fichier, un site",
    "osascript": "le volume (sans autorisation), une notification de secours",
    "networksetup": "le Wi-Fi",
    "pmset": "la veille, l'écran, la batterie",
    "shortcuts": "les raccourcis Apple (dont la concentration)",
    "mdfind": "la recherche Spotlight",
    "defaults": "lire l'apparence (clair ou sombre), en lecture seule",
    "say": "la réponse parlée (facultative)",
}
# Les commandes publiques de tes modules (§4.6), lancées seulement si `which` les trouve.
MODULES: dict[str, str] = {
    "tableau": "Tableau de bord",
    "ambiance": "Ambiance",
    "quotidien": "Quotidien",
    "bouclier": "Bouclier",
}
DOSSIERS_SYSTEME = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
SORTIE_MAX = 64_000


class ProgrammeRefuse(Exception):
    """Un programme hors liste, introuvable, ou un argument invalide : rien n'est lancé."""


@dataclass(frozen=True)
class Resultat:
    code: int
    sortie: str = ""
    erreur: str = ""
    delai_depasse: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.delai_depasse


def dossiers_modules(maison: Path, path: str | None = None) -> list[str]:
    """Où chercher les commandes de tes modules : ~/.local/bin, Homebrew, /usr/local/bin, puis ton PATH."""
    base = [str(maison / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    for d in (path if path is not None else os.environ.get("PATH", "")).split(os.pathsep):
        if d and d not in base:
            base.append(d)
    return base


@dataclass
class Executeur:
    dossiers_systeme: Sequence[str] = DOSSIERS_SYSTEME
    dossiers_modules: Sequence[str] = field(default_factory=list)
    delai_s: float = 10.0
    env: dict[str, str] | None = None

    def trouver(self, programme: str) -> str | None:
        """Le chemin du programme s'il est dans la liste et présent ; sinon None."""
        if programme in SYSTEME:
            dossiers: Sequence[str] = self.dossiers_systeme
        elif programme in MODULES:
            dossiers = self.dossiers_modules
        else:
            return None
        for d in dossiers:
            chemin = Path(d) / programme
            if chemin.is_file() and os.access(chemin, os.X_OK):
                return str(chemin)
        return None

    def present(self, programme: str) -> bool:
        return self.trouver(programme) is not None

    def lancer(self, programme: str, arguments: Sequence[str], delai_s: float | None = None) -> Resultat:
        if programme not in SYSTEME and programme not in MODULES:
            raise ProgrammeRefuse(f"programme hors liste : {programme!r}")
        for a in arguments:
            if not isinstance(a, str) or "\x00" in a or len(a) > 4000:
                raise ProgrammeRefuse("argument invalide")
        chemin = self.trouver(programme)
        if chemin is None:
            raise ProgrammeRefuse(f"{programme} introuvable")
        env = dict(self.env) if self.env is not None else _env_minimal()
        if programme in MODULES:  # leurs scripts cherchent leur Python (Homebrew) dans le PATH
            env["PATH"] = ":".join([*self.dossiers_modules, *DOSSIERS_SYSTEME])
        try:
            proc = subprocess.run(  # noqa: S603 - une liste d'arguments, jamais de shell
                [chemin, *arguments],
                capture_output=True,
                timeout=delai_s if delai_s is not None else self.delai_s,
                check=False,
                env=env,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return Resultat(124, delai_depasse=True)
        except OSError as e:
            return Resultat(127, erreur=str(e))
        sortie = proc.stdout.decode("utf-8", "replace")[:SORTIE_MAX]
        erreur = proc.stderr.decode("utf-8", "replace")[:SORTIE_MAX]
        return Resultat(proc.returncode, sortie, erreur)


def _env_minimal() -> dict[str, str]:
    """Un environnement réduit : pas de variables héritées qui changeraient le comportement d'un programme."""
    garder = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR")
    env = {k: os.environ[k] for k in garder if k in os.environ}
    env["PATH"] = ":".join(DOSSIERS_SYSTEME)
    return env
