"""Ce que les adaptateurs partagent pendant un tour : les sondes, et ce qui ne doit être lu qu'une fois.

`launchctl list`, le journal de l'assistant (`logs/assistant.log`, commun à Corvées, Nettoyeur, Trieur et au tri
Gmail), la base `etat.db` du superviseur, ses fils et `docker ps` ne sont lus qu'**une fois par tour**, quel que soit
le nombre de modules qui en ont besoin.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau.config import Chemins, Reglages
from tableau.db import Base
from tableau.module import DefModule
from tableau.sondes import docker_n8n, logs, processus
from tableau.sondes.docker_n8n import EtatDocker, SondeDocker
from tableau.sondes.launchd import SondeLaunchd
from tableau.sondes.logs import LecteurJournaux, Ligne
from tableau.sondes.processus import SondeProcessus
from tableau.sondes.sqlite_copie import LecteurBases

LABEL_SUPERVISEUR = "com.assistant.superviseur"
_TOMBE = re.compile(r"Module « (?P<nom>[\w\-]+) » tombé")
LECTURE_REGLAGES_S = 600


@dataclass
class Contexte:
    chemins: Chemins
    reglages: Reglages
    base: Base
    launchd: SondeLaunchd
    processus: SondeProcessus
    journaux: LecteurJournaux
    bases: LecteurBases
    docker: SondeDocker
    horloge: Callable[[], float] = time.time
    healthz: Callable[[int], tuple[bool, str]] = docker_n8n.healthz
    modules: list[DefModule] = field(default_factory=list)
    mesurer_tailles: bool = False
    maintenant: float = 0.0
    _cache: dict[str, Any] = field(default_factory=dict)
    _fichiers: dict[str, tuple[float, Any]] = field(default_factory=dict)

    def nouveau_tour(self, mesurer_tailles: bool = False) -> None:
        self.maintenant = self.horloge()
        self.mesurer_tailles = mesurer_tailles
        self._cache = {}
        self.launchd.nouveau_tour()
        self.journaux.nouveau_tour()

    # --- chemins ---------------------------------------------------------------------------------------------------

    def chemin(self, defn: DefModule, brut: str | None) -> Path | None:
        return defn.chemin(brut, self.chemins.maison, self.chemins.icloud_drive)

    def module(self, ident: str) -> DefModule | None:
        return next((m for m in self.modules if m.id == ident), None)

    # --- fichiers de réglages des autres (petits, relus au plus toutes les 10 min) ---------------------------------

    def lire_reglages(self, chemin: Path | None, genre: str = "json") -> dict[str, Any]:
        """Un fichier de réglages d'un autre module (JSON ou TOML), lu en lecture seule ; {} si illisible."""
        if chemin is None:
            return {}
        memo = self._fichiers.get(str(chemin))
        if memo is not None and self.maintenant - memo[0] < LECTURE_REGLAGES_S:
            return dict(memo[1])
        valeur: dict[str, Any] = {}
        try:
            with open(chemin, "rb") as f:
                brut = f.read(1_000_000)
            if genre == "toml":
                import tomllib

                valeur = tomllib.loads(brut.decode("utf-8"))
            else:
                charge = json.loads(brut.decode("utf-8"))
                valeur = charge if isinstance(charge, dict) else {}
        except (OSError, ValueError):
            valeur = {}
        self._fichiers[str(chemin)] = (self.maintenant, valeur)
        return dict(valeur)

    # --- l'assistant et son superviseur ----------------------------------------------------------------------------

    def racine_assistant(self) -> Path | None:
        defn = self.module("assistant")
        return self.chemin(defn, defn.dossier_projet) if defn is not None else None

    def reglages_assistant(self) -> dict[str, Any]:
        racine = self.racine_assistant()
        return self.lire_reglages(racine / "reglages.json" if racine else None)

    def pid_superviseur(self) -> int | None:
        if "pid_superviseur" not in self._cache:
            etat = self.launchd.etat(LABEL_SUPERVISEUR)
            self._cache["pid_superviseur"] = etat.pid if etat is not None else None
        pid: int | None = self._cache["pid_superviseur"]
        return pid

    def fils_superviseur(self) -> dict[str, list[int]]:
        if "fils" not in self._cache:
            pid = self.pid_superviseur()
            self._cache["fils"] = processus.fils_du_superviseur(pid) if pid else {}
        fils: dict[str, list[int]] = self._cache["fils"]
        return fils

    def statuts_superviseur(self) -> dict[str, dict[str, Any]] | None:
        """La table `modules` de `etat.db` (copie), et le battement du superviseur. None : inconnu."""
        if "statuts" not in self._cache:
            racine = self.racine_assistant()
            self._cache["statuts"] = None
            if racine is not None:
                self._cache["statuts"] = self.bases.lire(racine / "donnees" / "etat.db", "statuts", _lire_statuts)
        statuts: dict[str, dict[str, Any]] | None = self._cache["statuts"]
        return statuts

    def lignes_assistant(self) -> list[Ligne]:
        """Les nouvelles lignes de `logs/assistant.log` (une lecture par tour), et les plantages qu'elles citent."""
        if "lignes" not in self._cache:
            racine = self.racine_assistant()
            lignes = self.journaux.nouvelles_lignes(racine / "logs" / "assistant.log") if racine else []
            self._cache["lignes"] = lignes
            relances: dict[str, list[float]] = {}
            for ligne in lignes:
                if ligne.composant == "superviseur":
                    m = _TOMBE.search(ligne.message)
                    if m:
                        relances.setdefault(m.group("nom"), []).append(ligne.ts or self.maintenant)
            self._cache["relances"] = relances
        resultat: list[Ligne] = self._cache["lignes"]
        return resultat

    def relances_superviseur(self, nom: str) -> list[float]:
        self.lignes_assistant()
        relances: dict[str, list[float]] = self._cache["relances"]
        return relances.get(nom, [])

    def composants_pris(self) -> set[str]:
        """Les composants du journal de l'assistant qui appartiennent à un autre module du registre."""
        return {m.superviseur for m in self.modules if m.superviseur and m.id != "assistant" and m.actif}

    # --- Docker -------------------------------------------------------------------------------------------------------

    def docker_etat(self, noms: list[str]) -> EtatDocker:
        cle = "docker:" + ",".join(sorted(noms))
        if cle not in self._cache:
            self._cache[cle] = self.docker.etat(noms)
        etat: EtatDocker = self._cache[cle]
        return etat


def _lire_statuts(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    statuts: dict[str, dict[str, Any]] = {}
    try:
        for r in db.execute("SELECT * FROM modules"):
            ligne = dict(r)
            if ligne.get("nom"):
                statuts[str(ligne["nom"])] = ligne
    except sqlite3.DatabaseError:
        pass
    try:
        r = db.execute("SELECT valeur FROM cles WHERE cle = 'superviseur_vivant'").fetchone()
        if r is not None:
            statuts["__superviseur__"] = {"vivant": float(r[0])}
    except (sqlite3.DatabaseError, TypeError, ValueError):
        pass
    return statuts


def lignes_du_composant(lignes: list[Ligne], composants: set[str]) -> list[Ligne]:
    return [lg for lg in lignes if lg.composant in composants]


__all__ = ["Contexte", "LABEL_SUPERVISEUR", "lignes_du_composant", "logs"]
