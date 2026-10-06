"""« trieur installer » (D-08) : tout ce qu'il faut pour que le Trieur marche seul, sans rien écraser.

1. les dossiers (Classés, À trier, Photos de l'iPhone, la boîte iCloud BoiteMac) ;
2. l'action rapide du Finder (~/Library/Services) ;
3. les deux raccourcis de l'iPhone, signés, dans BoiteMac/Raccourcis (à ouvrir depuis l'app Fichiers) ;
4. la date d'installation (Téléchargements : seuls les PDF arrivés après seront regardés) ;
5. le module allumé : le superviseur de l'Assistant le lance (pas de LaunchAgent à part, D-01).
Chaque étape peut échouer seule : le message dit quoi faire, les autres continuent.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from modules.trieur import config, pages
from modules.trieur.base import Base
from modules.trieur.entrees import finder
from modules.trieur.garanties.coffre import Coffre
from modules.trieur.systeme import Systeme

PROJET = Path(__file__).resolve().parents[2]


def installer(reglages: dict[str, Any], base: Base, systeme: Systeme, allumer: bool = True,
              projet: Path = PROJET, python: Path | None = None) -> list[tuple[str, str]]:  # fmt: skip
    faits: list[tuple[str, str]] = []
    python = python or Path(sys.executable)

    for cle in ("classes", "a_trier", "photos"):
        dossier = config.chemin(reglages, cle)
        dossier.mkdir(parents=True, exist_ok=True)
        faits.append(("✅", f"dossier {dossier}"))
    icloud = Path(reglages["chemins"]["icloud"]).expanduser()
    boite = config.chemin(reglages, "boite")
    if icloud.is_dir():
        boite.mkdir(exist_ok=True)
        faits.append(("✅", f"boîte iCloud {boite}"))
    else:
        faits.append(("❌", "iCloud Drive introuvable : active-le (Réglages Système → identifiant Apple → iCloud)"))

    try:
        paquet = finder.installer(config.chemin(reglages, "services"), projet, python)
        faits.append(("✅", f"action rapide du Finder : {paquet.name}"))
    except (OSError, FileExistsError) as e:
        faits.append(("⚠️", f"action rapide du Finder non installée : {e}"))

    faits += _raccourcis(reglages, boite if icloud.is_dir() else None)

    if base.lire_meta("installe_le") is None:
        base.ecrire_meta("installe_le", str(time.time()))
    faits.append(("✅", "Téléchargements : seuls les PDF arrivés à partir de maintenant seront regardés"))

    try:
        pages.mettre_a_jour(reglages, base, Coffre(reglages, base, systeme))
        faits.append(("✅", "pages « Mon coffre » et « Derniers classements » dans la boîte"))
    except OSError as e:
        faits.append(("⚠️", f"pages HTML non écrites : {e}"))

    if allumer:
        from core import config as config_assistant

        config_assistant.activer_module("trieur", True)
        faits.append(("✅", "surveillance allumée (le superviseur la lance dans la minute)"))
    return faits


def _raccourcis(reglages: dict[str, Any], boite: Path | None) -> list[tuple[str, str]]:
    from modules.trieur import raccourcis

    brouillons = config.dossier_donnees(reglages) / "raccourcis"
    non_signes = raccourcis.ecrire(brouillons)
    if boite is None:
        return [("⚠️", "raccourcis non signés (pas d'iCloud) : la recette manuelle est dans ACTIONS_HUMAINES.md")]
    dossier = boite / "Raccourcis"
    dossier.mkdir(exist_ok=True)
    faits = []
    for brouillon in non_signes:
        nom = brouillon.name.replace(".non-signé", "")
        cible = dossier / nom
        if cible.exists():
            faits.append(("✅", f"raccourci « {cible.stem} » déjà prêt dans BoiteMac/Raccourcis"))
            continue
        ok, erreur = raccourcis.signer(brouillon, cible)
        faits.append(("✅", f"raccourci « {cible.stem} » signé dans BoiteMac/Raccourcis") if ok else
                     ("⚠️", f"raccourci « {cible.stem} » non signé ({erreur}) : recette manuelle dans "
                            "ACTIONS_HUMAINES.md"))  # fmt: skip
    return faits
