"""L'entrée iCloud du raccourci « Arnaque ? » : le Mac lit ce que l'iPhone a déposé dans `Bouclier/entree/` et écrit
sa réponse dans `Bouclier/reponses/<même nom>.txt`, dans le même dossier iCloud (celui de Bouclier ou celui de l'app
Raccourcis, D-12 du Trieur).

- Un fichier « fantôme » d'iCloud (`.nom.icloud`, pas encore téléchargé) est demandé avec `brctl download`, puis
  attendu ; un fichier n'est lu que lorsque sa taille n'a pas bougé entre deux passages (il est complet).
- Chaque fichier n'est traité qu'une fois (table `entrees_vues`) ; la réponse est écrite d'un coup (fichier
  temporaire puis renommage) pour que l'iPhone ne lise jamais une réponse à moitié écrite.
- Les fichiers `bouclier-verif-*` (déposés par `install.sh`) sont analysés pour de vrai, sans notification ni trace
  dans l'historique.
- Ces fichiers sont des copies faites pour Bouclier (l'original reste dans Messages ou Photos) : ceux de plus de
  30 jours sont retirés de l'entrée et des réponses.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bouclier.arnaque import analyse, extraction
from bouclier.config import Chemins
from bouclier.db import Base
from bouclier.journal import log
from bouclier.notifier import Notifieur
from bouclier.systeme import Systeme

GARDE_S = 30 * 86400
PREFIXE_VERIF = "bouclier-verif-"  # déposé par `install.sh` : analysé pour de vrai, puis rien n'en reste
RELANCE_ICLOUD_S = 120
TAILLE_MAX = 25_000_000


def identifiant(chemin: Path) -> str:
    return chemin.name.split(".", 1)[0] if not chemin.name.startswith(".") else chemin.name[1:].split(".", 1)[0]


def dossier_reponses(chemin_entree: Path) -> Path:
    return chemin_entree.parent.parent / "reponses"


@dataclass
class Traite:
    entree: Path
    reponse: Path
    titre: str


class BoiteEntree:
    def __init__(
        self, chemins: Chemins, base: Base, systeme: Systeme, horloge: Callable[[], float] = time.time
    ) -> None:
        self.chemins, self.base, self.systeme, self.horloge = chemins, base, systeme, horloge
        self._tailles: dict[Path, int] = {}
        self._demandes: dict[Path, float] = {}

    def _deja_vu(self, chemin: Path) -> bool:
        return (
            self.base.cx.execute("SELECT 1 FROM entrees_vues WHERE chemin = ?", (str(chemin),)).fetchone() is not None
        )

    def _noter(self, chemin: Path, taille: int, etat: str) -> None:
        with self.base.transaction() as cx:
            cx.execute("INSERT OR REPLACE INTO entrees_vues(chemin, taille, traitee_le, etat) VALUES (?, ?, ?, ?)",
                       (str(chemin), taille, self.horloge(), etat))  # fmt: skip

    def prets(self) -> list[Path]:
        """Les fichiers complets et pas encore traités ; demande à iCloud ceux qui ne sont pas encore là."""
        prets: list[Path] = []
        for dossier in self.chemins.entrees():
            if not dossier.is_dir():
                continue
            for chemin in sorted(dossier.iterdir()):
                if not chemin.is_file() or chemin.name in (".DS_Store",) or chemin.name.endswith(".tmp"):
                    continue
                if chemin.name.startswith(".") and chemin.name.endswith(".icloud"):
                    reel = chemin.with_name(chemin.name[1 : -len(".icloud")])
                    if self.horloge() - self._demandes.get(reel, 0) >= RELANCE_ICLOUD_S:
                        self._demandes[reel] = self.horloge()
                        self.systeme.telecharger_icloud(reel)
                        log().info("entrée iCloud pas encore téléchargée : demandée (%s)", reel.name)
                    continue
                if chemin.name.startswith(".") or self._deja_vu(chemin):
                    continue
                taille = chemin.stat().st_size
                if taille > 0 and self._tailles.get(chemin) == taille:
                    prets.append(chemin)
                self._tailles[chemin] = taille
        return prets

    def repondre(self, entree: Path, texte: str) -> Path:
        dossier = dossier_reponses(entree)
        dossier.mkdir(parents=True, exist_ok=True)
        cible = dossier / f"{identifiant(entree)}.txt"
        temporaire = dossier / f".{cible.name}.tmp"
        temporaire.write_text(texte + "\n", encoding="utf-8")
        os.replace(temporaire, cible)
        return cible

    def traiter(self, entree: Path, outils: analyse.Outils, notifieur: Notifieur) -> Traite:
        taille = entree.stat().st_size
        try:
            if taille > TAILLE_MAX:
                raise ValueError("fichier trop gros (plus de 25 Mo)")
            message = extraction.depuis_fichier(entree, outils.lire_image)
            if not message.texte.strip() and not message.pieces_jointes:
                raise ValueError("je n'ai trouvé aucun texte à analyser")
        except (OSError, ValueError) as e:
            texte = (f"⚠️ Je n'ai pas pu lire ce que tu as envoyé ({e}).\nEnvoie plutôt le texte du message, ou une"
                     " capture d'écran nette.")  # fmt: skip
            reponse = self.repondre(entree, texte)
            self._noter(entree, taille, "illisible")
            return Traite(entree, reponse, "illisible")
        r = analyse.verifier(message, outils, "iphone")
        reponse = self.repondre(entree, r.reponse.texte())
        self._noter(entree, taille, r.verdict.niveau.code)
        if identifiant(entree).startswith(PREFIXE_VERIF):  # la vérification de l'installation : ni notification
            with self.base.transaction() as cx:  # ni trace dans l'historique
                cx.execute("DELETE FROM analyses WHERE id = ?", (r.id_historique,))
            return Traite(entree, reponse, "vérification de l'installation")
        titre, corps = r.reponse.notification()
        notifieur.envoyer("reponse", titre, corps, reponse_a_demande=True)
        return Traite(entree, reponse, r.reponse.titre)

    def purger(self) -> int:
        """Les copies de plus de 30 jours (entrées et réponses) : seulement dans les dossiers de Bouclier."""
        retires = 0
        limite = self.horloge() - GARDE_S
        for dossier in [*self.chemins.entrees(), *self.chemins.dossiers_reponses()]:
            if not dossier.is_dir():
                continue
            for chemin in dossier.iterdir():
                try:
                    if chemin.is_file() and chemin.stat().st_mtime < limite:
                        chemin.unlink()
                        retires += 1
                except OSError:
                    continue
        with self.base.transaction() as cx:
            cx.execute("DELETE FROM entrees_vues WHERE traitee_le < ?", (limite,))
        return retires
