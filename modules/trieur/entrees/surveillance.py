"""Les entrées surveillées (§2) : la boîte iCloud (E1), « À trier » dans Documents (E2, D-57),
Téléchargements (E5).

Un fichier n'est pris que lorsqu'il ne bouge plus : même taille et même date sur 3 mesures à 1 s d'intervalle
(2 minutes dans Téléchargements : un navigateur écrit par morceaux).

E1 · BoiteMac (les deux dossiers, D-12) :
- un fichier « fantôme » d'iCloud (« .facture.pdf.icloud ») est demandé à iCloud (brctl download), puis pris quand
  le vrai fichier arrive ; de même un fichier présent mais encore sans contenu sur le Mac (macOS récents, D-59) ;
- la note de l'iPhone arrive dans « <nom>.meta.json » ({"note": "garantie 3 ans"}) : elle accompagne le document ;
  une note restée seule plus de 10 minutes est traitée comme un document (elle ira dans Notes reçues) ;
- les pages du Trieur (« Mon coffre.html »…) et les fichiers cachés sont ignorés.
E2 · « À trier » est un dossier du Trieur : créé par lui, ou vide quand il l'a pris (D-58). Un dossier du même nom
qui contient déjà tes fichiers n'est jamais surveillé.
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
from modules.trieur.base import Base, Element
from modules.trieur.systeme import Systeme

EN_COURS = (".crdownload", ".part", ".download", ".tmp", ".partial", ".opdownload")
META = ".meta.json"
META_ORPHELINE_S = 600
RELANCE_ICLOUD_S = 120
A_TRIER = "a_trier"  # la clé de la base qui retient le dossier « À trier » du Trieur (D-58)
JAMAIS_RANGES = ("en_attente", "en_cours", "erreur", "ignore")
SF_DATALESS = 0x40000000  # sys/stat.h : un fichier iCloud dont le contenu n'est pas encore sur le Mac


def sans_contenu(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_flags", 0) & SF_DATALESS)


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


def a_trier_du_trieur(reglages: dict[str, Any], base: Base) -> Path | None:
    """Le dossier « À trier » s'il est bien celui du Trieur, sinon None."""
    dossier = config.chemin(reglages, "a_trier")
    return dossier if base.lire_meta(A_TRIER) == str(dossier) else None


def contient_des_fichiers(dossier: Path) -> bool:
    try:
        return any(e.name != ".DS_Store" for e in os.scandir(dossier))
    except OSError:
        return True  # illisible : prudence


def prendre_a_trier(reglages: dict[str, Any], base: Base) -> tuple[str, str]:
    """Crée « À trier », ou le prend s'il est vide. S'il contient déjà quoi que ce soit, il est à toi : le Trieur ne le
    surveille pas et n'y touche jamais (D-58)."""
    dossier = config.chemin(reglages, "a_trier")
    if a_trier_du_trieur(reglages, base) is None:
        if dossier.is_symlink() or (dossier.exists() and (not dossier.is_dir() or contient_des_fichiers(dossier))):
            return "❌", (f"{dossier} existe déjà et contient tes fichiers : le Trieur ne le surveille pas et n'y "
                          "touche pas (pour choisir un autre dossier : ACTIONS_HUMAINES.md)")  # fmt: skip
        base.ecrire_meta(A_TRIER, str(dossier))
    dossier.mkdir(parents=True, exist_ok=True)
    return "✅", f"dossier {dossier}"


def anciens_du_trieur(reglages: dict[str, Any], base: Base) -> list[Path]:
    """Les anciens « À trier » (D-57, D-59) que le Trieur a créés : nés après son installation. Un dossier plus
    ancien, même vide, est à toi : il n'en fait jamais partie."""
    installe = base.lire_meta("installe_le")
    actuel = config.chemin(reglages, "a_trier")
    sortie = []
    for brut in reglages["chemins"]["anciens_a_trier"]:
        ancien = Path(brut).expanduser()
        if installe is None or ancien == actuel or ancien.is_symlink() or not ancien.is_dir():
            continue
        if ne_le(ancien) >= float(installe):
            sortie.append(ancien)
    return sortie


def ne_le(chemin: Path) -> float:
    """La date de création (macOS) ; ailleurs, le dernier changement d'inode."""
    st = chemin.stat()
    return float(getattr(st, "st_birthtime", st.st_ctime))


def vus_hors_de_chez_nous(reglages: dict[str, Any], base: Base) -> tuple[list[Element], list[Element]]:
    """Les fichiers repérés dans un « À trier » qui n'est pas (ou plus) celui du Trieur et jamais rangés :
    (sans aucune action au journal, donc jamais déplacés ni modifiés ; avec une action)."""
    garde = a_trier_du_trieur(reglages, base)
    vus = [el for el in base.venus_de("a_trier", JAMAIS_RANGES) if Path(el.chemin).parent != garde]
    avec = [el for el in vus if base.actions(el.id, toutes=True)]
    return [el for el in vus if el not in avec], avec


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
        sortie = [(config.chemin(r, "boite"), "boite"), (Path(r["chemins"]["boite_raccourcis"]).expanduser(), "boite")]
        a_trier = a_trier_du_trieur(r, self.base)
        if a_trier is not None:
            sortie.append((a_trier, "a_trier"))
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
        if source in ("boite", "a_trier") and nom.startswith(".") and nom.endswith(".icloud"):  # Documents dans iCloud
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
        if sans_contenu(st):  # le lire maintenant échouerait : on le demande à iCloud, et on attend
            self._relancer_icloud(chemin, maintenant)
            return None
        if self.base.deja_laisse(chemin, st.st_size, maintenant):
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
        if not vrai.exists():
            self._relancer_icloud(vrai, maintenant)

    def _relancer_icloud(self, chemin: Path, maintenant: float) -> None:
        if maintenant - self.demandes_icloud.get(chemin, 0.0) >= RELANCE_ICLOUD_S:
            self.demandes_icloud[chemin] = maintenant
            self.systeme.telecharger_icloud(chemin)

    def creer_les_dossiers(self) -> tuple[str, str]:
        for dossier, source in self.dossiers():
            if source == "boite":
                dossier.mkdir(parents=True, exist_ok=True)
        return prendre_a_trier(self.reglages, self.base)
