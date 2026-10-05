"""La base de connaissances embarquée (connaissances.json, écrite à la main, en français) : par motif, ce qu'est un
élément courant, son impact typique, la recommandation par défaut et l'effet si on le désactive.

Un élément absent de la base reçoit une description générique honnête : ce qu'on sait (éditeur, programme,
déclencheurs), sans rien inventer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from modules.demarrage.modele import Fiche

FICHIER = Path(__file__).with_name("connaissances.json")
IMPACTS = ("faible", "moyen", "fort")
RECOMMANDATIONS = ("garder", "desactiver", "au_choix")


@dataclass(frozen=True)
class Connaissance:
    motifs: tuple[re.Pattern[str], ...]
    nom: str
    role: str
    impact: str
    recommandation: str
    effet: str
    categorie: str
    editeur: str | None = None

    @property
    def mise_a_jour(self) -> bool:
        return self.categorie == "mise_a_jour"


def lire(chemin: Path = FICHIER) -> list[Connaissance]:
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    entrees = []
    for e in donnees["elements"]:
        entrees.append(
            Connaissance(
                motifs=tuple(re.compile(m, re.IGNORECASE) for m in e["motifs"]),
                nom=e["nom"],
                role=e["role"],
                impact=e["impact"],
                recommandation=e["recommandation"],
                effet=e["effet"],
                categorie=e["categorie"],
                editeur=e.get("editeur"),
            )
        )
    return entrees


@lru_cache(maxsize=1)
def base() -> tuple[Connaissance, ...]:
    return tuple(lire())


def indices(f: Fiche) -> list[str]:
    """Ce sur quoi on cherche : le label, le programme, l'app, le plist, les bundles associés."""
    morceaux = [f.label, f.programme, f.app_parente, f.chemin_plist, f.details.get("app_aide"), *f.bundles_associes]
    return [m for m in morceaux if m]


def trouver(f: Fiche, entrees: tuple[Connaissance, ...] | None = None) -> Connaissance | None:
    """La première entrée dont un motif correspond (la base est rangée du plus précis au plus général)."""
    textes = indices(f)
    for c in entrees if entrees is not None else base():
        if any(m.search(t) for m in c.motifs for t in textes):
            return c
    return None


def description_generique(f: Fiche) -> str:
    """Pour un élément inconnu de la base : ce qu'on sait, sans rien inventer."""
    if f.programme:
        quoi = f"lance « {PurePosixPath(f.programme).name} »"
    elif f.erreurs:
        quoi = f"a un fichier de lancement illisible ({f.erreurs[0]})"
    else:
        quoi = "ne dit pas quel programme il lance"
    qui = f"Un élément de {f.editeur}" if f.editeur else "Un élément d'un éditeur inconnu"
    quand = f.declencheurs.resume() if f.source not in ("ouverture", "ouverture_app") else "à l'ouverture de session"
    return f"{qui} qui {quoi} ({quand}). Il n'est pas dans la base de connaissances : on ne devine pas son rôle."
