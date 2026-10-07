"""L'état launchd des modules : `launchctl list` et `launchctl print`, rien d'autre (§1.2).

- `launchctl list` (un seul appel par tour, pour tous les modules) : chargé ou non, numéro de processus, dernier code
  de sortie ;
- `launchctl print gui/<uid>/<label>` : état, nombre de lancements (`runs`), dernier code de sortie, programme et
  journaux. Il n'est appelé que lorsqu'un label a changé dans `list` (nouveau processus, nouveau code) ou toutes les
  10 minutes : chaque appel est un programme lancé, et le tableau de bord doit rester léger.

Les lectures sont tolérantes : une ligne inattendue est ignorée, un champ absent vaut None (« inconnu »).
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from tableau import systeme
from tableau.module import EtatLaunchd

Executer = Callable[[list[str]], systeme.Resultat]


@dataclass
class LigneListe:
    pid: int | None
    statut: int | None


def lire_liste(sortie: str) -> dict[str, LigneListe]:
    """`launchctl list` : « PID\\tStatus\\tLabel », un « - » quand il n'y a rien."""
    resultat: dict[str, LigneListe] = {}
    for ligne in sortie.splitlines():
        morceaux = ligne.split("\t")
        if len(morceaux) != 3 or morceaux[0] == "PID":
            continue
        pid_brut, statut_brut, label = (m.strip() for m in morceaux)
        if not label:
            continue
        pid = int(pid_brut) if pid_brut.isdigit() else None
        try:
            statut = int(statut_brut)
        except ValueError:
            statut = None
        resultat[label] = LigneListe(pid, statut)
    return resultat


_CHAMP = re.compile(r"^\t(?P<cle>[a-z][a-z ]+?) = (?P<valeur>.*)$")


def lire_print(label: str, sortie: str) -> EtatLaunchd:
    """`launchctl print gui/<uid>/<label>` : seuls les champs du premier niveau sont lus."""
    champs: dict[str, str] = {}
    for ligne in sortie.splitlines():
        m = _CHAMP.match(ligne)
        if m:
            champs.setdefault(m.group("cle"), m.group("valeur").strip())

    def entier(cle: str) -> int | None:
        brut = champs.get(cle, "")
        m = re.match(r"^-?\d+", brut)
        return int(m.group(0)) if m else None

    return EtatLaunchd(
        label=label,
        charge=True,
        pid=entier("pid"),
        dernier_code=entier("last exit code"),
        lancements=entier("runs"),
        etat=champs.get("state"),
        programme=champs.get("program"),
    )


class SondeLaunchd:
    """Une instance pour toute la vie du démon : elle se souvient de ce qu'elle a vu au tour précédent."""

    def __init__(self, executer: Executer | None = None, uid: int | None = None,
                 horloge: Callable[[], float] = time.time, rafraichir_s: float = 600) -> None:  # fmt: skip
        self.executer: Executer = executer or (lambda args: systeme.executer(args, delai=10))
        self.uid = os.getuid() if uid is None else uid
        self.horloge = horloge
        self.rafraichir_s = rafraichir_s
        self._liste: dict[str, LigneListe] | None = None
        self._liste_precedente: dict[str, LigneListe] = {}
        self._prints: dict[str, tuple[float, EtatLaunchd]] = {}
        self.erreur: str | None = None

    def nouveau_tour(self) -> None:
        """Au début de chaque tour : `launchctl list` sera relu (une fois) au premier besoin."""
        if self._liste is not None:
            self._liste_precedente = self._liste
        self._liste = None

    def liste(self) -> dict[str, LigneListe] | None:
        if self._liste is None:
            r = self.executer(["launchctl", "list"])
            if not r.ok:
                self.erreur = (r.erreur or r.sortie or f"code {r.code}").strip()[:200]
                return None
            self.erreur = None
            self._liste = lire_liste(r.sortie)
        return self._liste

    def etat(self, label: str) -> EtatLaunchd | None:
        """L'état d'un label, ou None si launchd ne répond pas (inconnu). Non chargé : `charge=False`."""
        liste = self.liste()
        if liste is None:
            return None
        ligne = liste.get(label)
        if ligne is None:
            self._prints.pop(label, None)
            return EtatLaunchd(label=label, charge=False)
        avant = self._liste_precedente.get(label)
        memo = self._prints.get(label)
        a_change = avant is None or avant.pid != ligne.pid or avant.statut != ligne.statut
        if memo is None or a_change or self.horloge() - memo[0] >= self.rafraichir_s:
            r = self.executer(["launchctl", "print", f"gui/{self.uid}/{label}"])
            if r.ok:
                memo = (self.horloge(), lire_print(label, r.sortie))
                self._prints[label] = memo
        if memo is None:
            return EtatLaunchd(label=label, charge=True, pid=ligne.pid, dernier_code=ligne.statut)
        detail = memo[1]
        # `list` est relu à chaque tour : il fait foi pour le processus et le dernier code de sortie.
        return EtatLaunchd(
            label=label,
            charge=True,
            pid=ligne.pid,
            dernier_code=ligne.statut if ligne.statut is not None else detail.dernier_code,
            lancements=detail.lancements,
            etat=("running" if ligne.pid else detail.etat if detail.etat != "running" else "not running"),
            programme=detail.programme,
        )
