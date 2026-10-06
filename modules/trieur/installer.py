"""« trieur installer » (D-08) : tout ce qu'il faut pour que le Trieur marche seul, sans rien écraser.

1. les dossiers (Classés, À trier dans Documents, Photos de l'iPhone, la boîte iCloud BoiteMac), et l'ancien
   « À trier » du Bureau retiré s'il est vide (D-57) ;
2. l'action rapide du Finder (~/Library/Services) ;
3. les deux raccourcis de l'iPhone, signés, dans BoiteMac/Raccourcis (à ouvrir depuis l'app Fichiers) ;
4. la date d'installation (Téléchargements : seuls les PDF arrivés après seront regardés) ;
5. le module allumé : le superviseur de l'Assistant le lance (pas de LaunchAgent à part, D-01).
Chaque étape peut échouer seule : le message dit quoi faire, les autres continuent.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from modules.trieur import config, pages
from modules.trieur.base import Base
from modules.trieur.entrees import finder, surveillance
from modules.trieur.garanties.coffre import Coffre
from modules.trieur.systeme import Systeme

PROJET = Path(__file__).resolve().parents[2]


def installer(reglages: dict[str, Any], base: Base, systeme: Systeme, allumer: bool = True,
              projet: Path = PROJET, python: Path | None = None) -> list[tuple[str, str]]:  # fmt: skip
    faits: list[tuple[str, str]] = []
    python = python or Path(sys.executable)

    for cle in ("classes", "photos"):
        dossier = config.chemin(reglages, cle)
        dossier.mkdir(parents=True, exist_ok=True)
        faits.append(("✅", f"dossier {dossier}"))
    faits.append(surveillance.prendre_a_trier(reglages, base))
    faits += _anciens_a_trier(reglages, base)
    faits += _vus_hors_de_chez_nous(reglages, base)
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


def _anciens_a_trier(reglages: dict[str, Any], base: Base) -> list[tuple[str, str]]:
    """Les anciens « À trier » créés par le Trieur (D-57, D-59) : retirés s'ils sont vides (le « .DS_Store » du
    Finder mis à part) ; s'ils contiennent quoi que ce soit, rien n'est touché. Un dossier né avant l'arrivée du
    Trieur est à toi : jamais regardé."""
    nouveau = config.chemin(reglages, "a_trier")
    faits = []
    for ancien in surveillance.anciens_du_trieur(reglages, base):
        reste = [e.name for e in ancien.iterdir() if e.name != ".DS_Store"]
        if not reste:
            try:
                (ancien / ".DS_Store").unlink(missing_ok=True)
                ancien.rmdir()  # refuse d'elle-même un dossier qui n'est pas vide
                faits.append(("✅", f"ancien dossier {ancien} retiré (il était vide)"))
                continue
            except OSError:
                reste = [e.name for e in ancien.iterdir()]
        faits.append(("⚠️", f"l'ancien dossier {ancien} contient encore {len(reste)} élément(s) : glisse-les dans "
                            f"{nouveau}, puis supprime-le"))  # fmt: skip
    return faits


def _vus_hors_de_chez_nous(reglages: dict[str, Any], base: Base) -> list[tuple[str, str]]:
    """D-58 : la preuve, lue dans le journal des actions, que les fichiers d'un dossier à toi n'ont pas bougé.
    La base ne les oublie qu'au redémarrage du Trieur (l'ancien, encore en marche, les reprendrait sinon)."""
    sans_action, avec_action = surveillance.vus_hors_de_chez_nous(reglages, base)
    faits = []
    if sans_action:
        dossiers = ", ".join(sorted({str(Path(el.chemin).parent) for el in sans_action}))
        erreurs = Counter(el.erreur for el in sans_action if el.erreur).most_common(1)
        faits.append(("✅", f"{len(sans_action)} fichier(s) de ton dossier {dossiers} vus par erreur : aucun déplacé "
                            "ni modifié (aucune action au journal) ; le Trieur les oublie à son redémarrage"
                            + (f" · erreur vue : {erreurs[0][0]}" if erreurs else "")))  # fmt: skip
    if avec_action:
        faits.append(("⚠️", f"{len(avec_action)} fichier(s) d'un dossier à toi ont une action au journal : "
                            "python trieur.py journal"))  # fmt: skip
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
