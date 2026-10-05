"""C3 — Les fichiers : ce qui arrive, est rangé, renommé, converti ou jeté dans Téléchargements, Bureau, Documents.

FSEvents (via watchdog) signale les changements ; on reconstitue l'action (déplacement source → destination,
renommage, conversion, téléchargement terminé). Jamais le contenu des fichiers. Les chemins ne sont gardés que sous
forme d'empreinte (pour relier les étapes d'un même fichier) et de lieu généralisé (« Documents/Factures »).
Sans watchdog : on compare des instantanés des dossiers (mode dégradé).
"""

from __future__ import annotations

import os
import queue
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.corvees.capteurs.base import Capteur
from modules.corvees.normalize import tok_conversion, tok_creation, tok_deplacement, tok_renommage, tok_suppression

TEMPORAIRES = (".crdownload", ".part", ".download", ".tmp", ".swp", ".partial", ".icloud", ".opdownload")
APPARIEMENT_S = 2.0  # une suppression puis une création du même nom : un déplacement


@dataclass
class Brut:
    ts: float
    sorte: str  # created, deleted, moved
    chemin: str
    destination: str = ""


def temporaire(chemin: str) -> bool:
    nom = os.path.basename(chemin)
    return nom.startswith(("~$", ".~")) or nom == ".DS_Store" or nom.lower().endswith(TEMPORAIRES)


def cache(chemin: str) -> bool:
    """Un fichier ou dossier caché (sauf la corbeille, destination légitime)."""
    return any(p.startswith(".") and p != ".Trash" for p in Path(chemin).parts[1:])


class Reconstructeur:
    """Des signalements bruts aux actions : fcreate, fmove, fren, fconv, fdel."""

    def __init__(
        self,
        racines: list[str],
        profondeur: int,
        empreinte: Callable[[str], str],
        exclu: Callable[[str], bool],
        maison: str | None = None,
    ):
        self.racines = [str(Path(r).expanduser()) for r in racines]
        self.profondeur = profondeur
        self.empreinte = empreinte
        self.exclu = exclu
        self.maison = maison or str(Path.home())
        self.suppressions: list[Brut] = []
        self.creations: list[Brut] = []

    def surveille(self, chemin: str) -> bool:
        for racine in self.racines:
            if chemin.startswith(racine.rstrip("/") + "/"):
                return len(Path(chemin).relative_to(racine).parts) <= self.profondeur + 1
        return False

    def _ignore(self, chemin: str) -> bool:
        return temporaire(chemin) or cache(chemin) or self.exclu(chemin)

    def traiter(self, bruts: list[Brut], maintenant: float) -> list[tuple[float, str, str, dict[str, Any]]]:
        """[(instant, sorte, token, attributs)]. Créations et suppressions attendent 2 s : « supprimé ici, recréé
        là-bas sous le même nom » est un déplacement, quel que soit l'ordre dans lequel le système les signale."""
        sortie: list[tuple[float, str, str, dict[str, Any]]] = []
        for b in bruts:
            if b.sorte == "moved":
                sortie += self._deplace(b)
            elif b.sorte == "created" and self.surveille(b.chemin) and not self._ignore(b.chemin):
                self.creations.append(b)
            elif b.sorte == "deleted" and self.surveille(b.chemin) and not self._ignore(b.chemin):
                self.suppressions.append(b)
        for c in list(self.creations):
            paire = next(
                (
                    s
                    for s in self.suppressions
                    if os.path.basename(s.chemin) == os.path.basename(c.chemin)
                    and abs(c.ts - s.ts) <= APPARIEMENT_S
                    and os.path.dirname(s.chemin) != os.path.dirname(c.chemin)
                ),
                None,
            )
            if paire:
                self.creations.remove(c)
                self.suppressions.remove(paire)
                sortie += self._deplace(Brut(max(c.ts, paire.ts), "moved", paire.chemin, c.chemin))
        for c in [c for c in self.creations if maintenant - c.ts > APPARIEMENT_S]:
            self.creations.remove(c)
            sortie.append(self._cree(c.ts, c.chemin))
        for s in [s for s in self.suppressions if maintenant - s.ts > APPARIEMENT_S]:
            self.suppressions.remove(s)
            sortie.append(self._supprime(s))
        return sorted(sortie, key=lambda x: x[0])

    def _attrs(self, **chemins: str) -> dict[str, Any]:
        return {cle: self.empreinte(valeur) for cle, valeur in chemins.items()}

    def _cree(self, ts: float, chemin: str) -> tuple[float, str, str, dict[str, Any]]:
        dossier, nom = os.path.dirname(chemin), os.path.basename(chemin)
        tige, ext = os.path.splitext(nom)
        try:
            voisins = [
                v
                for v in os.listdir(dossier)
                if os.path.splitext(v)[0] == tige
                and os.path.splitext(v)[1]
                and v != nom
                and os.path.isfile(os.path.join(dossier, v))
            ]
        except OSError:
            voisins = []
        if ext and voisins:  # le même nom avec une autre extension, juste à côté : une conversion
            source = os.path.join(dossier, voisins[0])
            token = tok_conversion(dossier, voisins[0], nom, self.maison)
            return ts, "fconv", token, self._attrs(source=source, fichier=chemin)
        return ts, "fcreate", tok_creation(dossier, nom, self.maison), self._attrs(fichier=chemin)

    def _deplace(self, b: Brut) -> list[tuple[float, str, str, dict[str, Any]]]:
        source, cible = b.chemin, b.destination
        if not cible or self._ignore(cible) or self.exclu(source):
            return []
        if temporaire(source):  # un téléchargement qui se termine (« x.pdf.crdownload » → « x.pdf »)
            return [self._cree(b.ts, cible)] if self.surveille(cible) else []
        if not (self.surveille(source) or self.surveille(cible)):
            return []
        de, vers = os.path.dirname(source), os.path.dirname(cible)
        nom_avant, nom_apres = os.path.basename(source), os.path.basename(cible)
        attrs = self._attrs(avant=source, fichier=cible)
        if de == vers:
            return [(b.ts, "fren", tok_renommage(de, nom_avant, nom_apres, self.maison), attrs)]
        return [(b.ts, "fmove", tok_deplacement(de, vers, nom_apres, self.maison), attrs)]

    def _supprime(self, b: Brut) -> tuple[float, str, str, dict[str, Any]]:
        dossier, nom = os.path.dirname(b.chemin), os.path.basename(b.chemin)
        return b.ts, "fdel", tok_suppression(dossier, nom, self.maison), self._attrs(avant=b.chemin)


class Fichiers(Capteur):
    nom = "fichiers"
    intervalle = 2.0

    def __init__(self, *args, empreinte=None, exclu=None, maison: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        r = self.reglages["fichiers"]
        self.reconstructeur = Reconstructeur(
            r["dossiers"], r["profondeur"], empreinte or (lambda c: c), exclu or (lambda c: False), maison
        )
        self.file: queue.Queue[Brut] = queue.Queue()
        self.observateur: Any = None
        self.instantane: dict[int, str] | None = None
        self.dernier_instantane = 0.0

    def demarrer(self) -> None:
        racines = [r for r in self.reconstructeur.racines if os.path.isdir(r)]
        if not racines:
            self.desactiver("aucun des dossiers surveillés n'existe")
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            self.degrader("watchdog absent : comparaison des dossiers toutes les minutes")
            self.instantane = self._photographier()
            return
        file = self.file

        class Signalement(FileSystemEventHandler):
            def on_any_event(self, event):  # noqa: N802
                if event.is_directory or event.event_type not in ("created", "deleted", "moved"):
                    return
                file.put(Brut(time.time(), event.event_type, str(event.src_path), str(getattr(event, "dest_path", ""))))

        self.observateur = Observer()
        for racine in racines:
            self.observateur.schedule(Signalement(), racine, recursive=True)
        self.observateur.daemon = True
        self.observateur.start()

    def arreter(self) -> None:
        if self.observateur is not None:
            self.observateur.stop()
            self.observateur.join(timeout=5)
            self.observateur = None

    def _photographier(self) -> dict[int, str]:
        """{inode: chemin} des fichiers surveillés (mode dégradé sans watchdog)."""
        vus: dict[int, str] = {}
        for racine in self.reconstructeur.racines:
            for dossier, sous, noms in os.walk(racine):
                if len(Path(dossier).relative_to(racine).parts) >= self.reconstructeur.profondeur:
                    sous[:] = []
                for nom in noms:
                    chemin = os.path.join(dossier, nom)
                    try:
                        vus[os.stat(chemin).st_ino] = chemin
                    except OSError:
                        continue
        return vus

    def relever(self, maintenant: float) -> None:
        bruts: list[Brut] = []
        if self.instantane is not None and maintenant - self.dernier_instantane >= 60:
            nouveau = self._photographier()
            for inode, chemin in nouveau.items():
                ancien = self.instantane.get(inode)
                if ancien is None:
                    bruts.append(Brut(maintenant, "created", chemin))
                elif ancien != chemin:
                    bruts.append(Brut(maintenant, "moved", ancien, chemin))
            bruts += [Brut(maintenant, "deleted", c) for i, c in self.instantane.items() if i not in nouveau]
            self.instantane, self.dernier_instantane = nouveau, maintenant
        while True:
            try:
                bruts.append(self.file.get_nowait())
            except queue.Empty:
                break
        for ts, sorte, token, attrs in self.reconstructeur.traiter(bruts, maintenant):
            self.emettre(ts, sorte, token, **attrs)
