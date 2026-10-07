"""La seule porte vers les commandes du Mac : une liste blanche de commandes en lecture seule (§1.2).

Toute commande lancée par le tableau de bord passe par `executer`, qui refuse tout ce qui n'est pas explicitement
permis. Ainsi, même par erreur, le tableau de bord ne peut ni arrêter, ni relancer, ni modifier un autre projet :

- launchd : `launchctl list` et `launchctl print` seulement (jamais bootstrap, bootout, kickstart, kill, enable,
  disable, load, unload…) ;
- Docker : `docker ps`, `docker inspect` et `docker stats --no-stream` seulement ;
- git : `rev-parse`, `log` et `status`, toujours avec `--no-optional-locks` (git ne réécrit pas l'index) ;
- le reste : `ps`, `lsof`, `pmset -g`, `sysctl -n`, une notification (`osascript -e 'display notification …'`),
  l'ouverture de notre propre page (`open http://127.0.0.1:…`) et la lecture de notre propre clé dans le trousseau.

La commande de diagnostic d'un autre module (« Lancer le diagnostic ») ne passe pas par `executer` : elle a sa
propre porte, `executer_diagnostic`, qui exige une demande explicite (ton clic, ou ta commande dans le Terminal).
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

SERVICE_TROUSSEAU = "tableau-de-bord-admin-anthropic"


class CommandeInterdite(Exception):
    """Une commande hors de la liste blanche : jamais exécutée."""


@dataclass
class Resultat:
    code: int
    sortie: str
    erreur: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0


@dataclass(frozen=True)
class DemandeExplicite:
    """La preuve qu'une commande d'un autre module est lancée à ton initiative."""

    origine: str  # « page » (bouton, POST avec jeton) ou « terminal » (tableau diagnostic …)
    module: str


# Les dernières commandes lancées (pour `tableau doctor` et pour les tests, qui les espionnent).
JOURNAL: deque[tuple[float, tuple[str, ...]]] = deque(maxlen=200)
DIAGNOSTICS: deque[tuple[float, str, str, tuple[str, ...]]] = deque(maxlen=50)

_CIBLE_LAUNCHD = re.compile(r"^(gui|user)/\d+(/[A-Za-z0-9_.\-]+)?$")
_LABEL = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _verifier_launchctl(args: list[str]) -> None:
    if len(args) == 2 and args[1] == "list":
        return
    if len(args) == 3 and args[1] == "list" and _LABEL.match(args[2]):
        return
    if len(args) == 3 and args[1] == "print" and _CIBLE_LAUNCHD.match(args[2]):
        return
    raise CommandeInterdite(f"launchctl {' '.join(args[1:2])} : seuls « list » et « print » sont permis")


def _verifier_docker(args: list[str]) -> None:
    if len(args) < 2 or args[1] not in ("ps", "inspect", "stats"):
        raise CommandeInterdite("docker : seuls « ps », « inspect » et « stats --no-stream » sont permis")
    if args[1] == "stats" and "--no-stream" not in args:
        raise CommandeInterdite("docker stats sans --no-stream : interdit (il ne rendrait jamais la main)")


def _verifier_git(args: list[str]) -> None:
    if len(args) < 3 or args[1] != "--no-optional-locks":
        raise CommandeInterdite("git sans --no-optional-locks : interdit (git pourrait réécrire l'index)")
    reste = args[2:]
    if len(reste) >= 2 and reste[0] == "-C":
        reste = reste[2:]
    if not reste or reste[0] not in ("rev-parse", "log", "status"):
        raise CommandeInterdite("git : seuls « rev-parse », « log » et « status » sont permis")
    if any(a in ("--output", "-o") or a.startswith("--output=") for a in reste):
        raise CommandeInterdite("git : aucune écriture de fichier")


def _verifier_open(args: list[str]) -> None:
    if len(args) == 2 and re.match(r"^http://(127\.0\.0\.1|localhost):\d{2,5}/", args[1]):
        return
    if len(args) == 2 and args[1].endswith(".html") and Path(args[1]).is_absolute() and "TableauDeBord" in args[1]:
        return
    raise CommandeInterdite("open : seulement notre page locale ou nos rapports")


def verifier(args: list[str]) -> None:
    """Lève CommandeInterdite si la commande n'est pas dans la liste blanche."""
    if not args:
        raise CommandeInterdite("commande vide")
    nom = os.path.basename(args[0])
    if nom == "launchctl":
        _verifier_launchctl(args)
    elif nom == "docker":
        _verifier_docker(args)
    elif nom == "git":
        _verifier_git(args)
    elif nom in ("ps", "lsof"):
        if any(a in ("-k", "--kill") for a in args):
            raise CommandeInterdite(f"{nom} : option interdite")
    elif nom == "pmset":
        if len(args) < 2 or args[1] != "-g":
            raise CommandeInterdite("pmset : seulement « pmset -g » (lecture)")
    elif nom == "sysctl":
        if len(args) != 3 or args[1] != "-n" or "=" in args[2]:
            raise CommandeInterdite("sysctl : seulement « sysctl -n <nom> » (lecture)")
    elif nom == "osascript":
        if len(args) != 3 or args[1] != "-e" or not args[2].startswith("display notification "):
            raise CommandeInterdite("osascript : seulement l'affichage d'une notification")
    elif nom == "open":
        _verifier_open(args)
    elif nom == "security":
        if args[1:] != ["find-generic-password", "-s", SERVICE_TROUSSEAU, "-w"]:
            raise CommandeInterdite("security : seulement la lecture de notre propre clé (facultative)")
    else:
        raise CommandeInterdite(f"« {nom} » n'est pas dans la liste blanche du tableau de bord")


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def executer(args: list[str], delai: float = 15, cwd: Path | None = None) -> Resultat:
    """Lance une commande de la liste blanche. Ne lève jamais (sauf commande interdite) : échec = code ≠ 0."""
    verifier(args)
    JOURNAL.append((time.time(), tuple(args)))
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=delai, cwd=cwd, env=_env(), stdin=subprocess.DEVNULL
        )
    except FileNotFoundError:
        return Resultat(127, "", f"{args[0]} : introuvable sur cette machine")
    except subprocess.TimeoutExpired:
        return Resultat(124, "", f"{args[0]} : pas de réponse en {delai:g} s")
    except OSError as e:
        return Resultat(126, "", f"{args[0]} : {e.__class__.__name__}")
    return Resultat(proc.returncode, proc.stdout or "", proc.stderr or "")


def executer_diagnostic(commande: list[str], dossier: Path, demande: DemandeExplicite, delai: float = 120) -> Resultat:
    """La commande de diagnostic d'un autre module, lancée seulement à ta demande (bouton ou Terminal).

    C'est la commande du module qui s'exécute, dans son dossier, telle qu'écrite dans le registre."""
    if not isinstance(demande, DemandeExplicite) or demande.origine not in ("page", "terminal"):
        raise CommandeInterdite("un diagnostic ne se lance qu'à ta demande")
    if not commande:
        raise CommandeInterdite("pas de commande de diagnostic pour ce module")
    DIAGNOSTICS.append((time.time(), demande.origine, demande.module, tuple(commande)))
    try:
        proc = subprocess.run(
            commande, capture_output=True, text=True, timeout=delai, cwd=dossier, stdin=subprocess.DEVNULL
        )
    except FileNotFoundError:
        return Resultat(127, "", f"{commande[0]} : introuvable")
    except subprocess.TimeoutExpired:
        return Resultat(124, "", f"pas de réponse en {delai:g} s")
    except OSError as e:
        return Resultat(126, "", e.__class__.__name__)
    return Resultat(proc.returncode, proc.stdout or "", proc.stderr or "")


def est_un_mac() -> bool:
    return os.uname().sysname == "Darwin"
