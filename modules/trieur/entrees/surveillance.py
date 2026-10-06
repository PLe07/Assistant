"""Les entrées surveillées (§2) : la boîte iCloud (E1), « À trier » sur le Bureau (E2), Téléchargements (E5).

Un fichier n'est pris que lorsqu'il ne bouge plus : même taille et même date sur 3 mesures à 1 s d'intervalle
(2 minutes dans Téléchargements : un navigateur écrit par morceaux).

E1 · BoiteMac (les deux dossiers, D-12) :
- un fichier « fantôme » d'iCloud (« .facture.pdf.icloud ») est demandé à iCloud (brctl download), puis pris quand
  le vrai fichier arrive ;
- la note de l'iPhone arrive dans « <nom>.meta.json » ({"note": "garantie 3 ans"}) : elle accompagne le document ;
  une note restée seule plus de 10 minutes est traitée comme un document (elle ira dans Notes reçues) ;
- les pages du Trieur (« Mon coffre.html »…) et les fichiers cachés sont ignorés.
E5 · Téléchargements : seulement les PDF arrivés après l'installation (jamais les fichiers déjà là), jamais un
téléchargement en cours (.crdownload, .part, .download) ; un fichier reçu par AirDrop (quarantaine « sharingd »)
est traité comme un envoi de l'iPhone, quel que soit son format.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.trieur import config, pages
from modules.trieur.base import Base
from modules.trieur.systeme import Systeme

EN_COURS = (".crdownload", ".part", ".download", ".tmp", ".partial", ".opdownload")
META = ".meta.json"
META_ORPHELINE_S = 600
RELANCE_ICLOUD_S = 120


@dataclass
class Vu:
    taille: int
    date: float
    mesures: int
    premier: float


@dataclass
class Pret:
    chemin: Path
    source: str
    note: str | None
    meta: Path | None


def lire_note(meta: Path) -> str | None:
    try:
        donnees = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    note = donnees.get("note") if isinstance(donnees, dict) else None
    return str(note).strip()[:500] or None if note else None


class Entrees:
    def __init__(self, reglages: dict[str, Any], base: Base, systeme: Systeme,
                 horloge: Callable[[], float] = time.time):  # fmt: skip
        self.reglages, self.base, self.systeme, self.horloge = reglages, base, systeme, horloge
        self.vus: dict[Path, Vu] = {}
        self.demandes_icloud: dict[Path, float] = {}
        installe = base.lire_meta("installe_le")
        if installe is None:  # le premier démarrage : ce qui est déjà dans Téléchargements n'est jamais touché
            installe = str(horloge())
            base.ecrire_meta("installe_le", installe)
        self.installe_le = float(installe)

    def dossiers(self) -> list[tuple[Path, str]]:
        r = self.reglages
        sortie = [(config.chemin(r, "boite"), "boite"), (Path(r["chemins"]["boite_raccourcis"]).expanduser(), "boite"),
                  (config.chemin(r, "a_trier"), "a_trier")]  # fmt: skip
        if r["telechargements"]["actif"]:
            sortie.append((config.chemin(r, "telechargements"), "telechargements"))
        return sortie

    def _attente(self, source: str) -> tuple[int, float]:
        """(mesures identiques, durée minimale) avant de prendre un fichier."""
        if source == "telechargements":
            return 2, float(self.reglages["telechargements"]["stabilite_s"])
        return int(self.reglages["stabilite"]["mesures"]), 0.0

    def regarder(self) -> list[Pret]:
        """Un passage sur les dossiers : les fichiers prêts à traiter."""
        prets: list[Pret] = []
        maintenant = self.horloge()
        presents: set[Path] = set()
        for dossier, source in self.dossiers():
            try:
                entrees = list(os.scandir(dossier))
            except OSError:
                continue
            noms = {e.name for e in entrees}
            for e in entrees:
                chemin = Path(e.path)
                pret = self._examiner(e, chemin, source, noms, maintenant)
                if pret is not None:
                    prets.append(pret)
                presents.add(chemin)
        for disparu in set(self.vus) - presents:
            del self.vus[disparu]
        return prets

    def _examiner(self, e: os.DirEntry[str], chemin: Path, source: str, noms: set[str],
                  maintenant: float) -> Pret | None:  # fmt: skip
        nom = e.name
        if source == "boite" and nom.startswith(".") and nom.endswith(".icloud"):
            self._demander_a_icloud(chemin.parent / nom[1:-7], maintenant)
            return None
        if nom.startswith((".", "~$")) or nom.endswith(EN_COURS) or nom in (pages.COFFRE, pages.DERNIERS):
            return None
        if nom.endswith(" (Trieur).html"):
            return None
        try:
            if not e.is_file(follow_symlinks=False):
                return None
            st = e.stat(follow_symlinks=False)
        except OSError:
            return None
        if nom.endswith(META) and source != "telechargements":
            if self._a_son_document(nom, noms) or maintenant - st.st_mtime < META_ORPHELINE_S:
                return None  # elle partira avec son document
        if source == "telechargements" and max(st.st_mtime, getattr(st, "st_birthtime", 0.0)) < self.installe_le:
            return None  # déjà là avant l'installation : jamais touché
        if self.base.deja_laisse(chemin, st.st_size):
            return None  # déjà examiné et laissé (pas sûr, doublon, erreur) : repris seulement s'il change
        vu = self.vus.get(chemin)
        if vu is None or (vu.taille, vu.date) != (st.st_size, st.st_mtime):
            self.vus[chemin] = Vu(st.st_size, st.st_mtime, 1, maintenant)
            return None
        vu.mesures += 1
        mesures, duree = self._attente(source)
        if vu.mesures < mesures or maintenant - vu.premier < duree:
            return None
        del self.vus[chemin]
        if source == "telechargements":
            if "sharingd" in self.systeme.quarantaine(chemin).lower():
                source = "airdrop"
            elif chemin.suffix.lower() != ".pdf":
                return None
        meta = self._meta(chemin, noms) if source in ("boite", "a_trier") else None
        return Pret(chemin, source, lire_note(meta) if meta else None, meta)

    @staticmethod
    def _a_son_document(nom_meta: str, noms: set[str]) -> bool:
        racine = nom_meta[: -len(META)]
        return any(n != nom_meta and (n == racine or Path(n).stem == racine) for n in noms)

    @staticmethod
    def _meta(chemin: Path, noms: set[str]) -> Path | None:
        for candidat in (chemin.name + META, chemin.stem + META):
            if candidat in noms:
                return chemin.parent / candidat
        return None

    def _demander_a_icloud(self, vrai: Path, maintenant: float) -> None:
        if vrai.exists():
            return
        if maintenant - self.demandes_icloud.get(vrai, 0.0) >= RELANCE_ICLOUD_S:
            self.demandes_icloud[vrai] = maintenant
            self.systeme.telecharger_icloud(vrai)

    def creer_les_dossiers(self) -> None:
        for dossier, source in self.dossiers():
            if source != "telechargements":
                dossier.mkdir(parents=True, exist_ok=True)
