"""Les réglages du Trieur : reglages.json → modules.trieur, fusionnés avec ces valeurs par défaut.

Tous les chemins sont réglables : le mode test (et les tests) les font pointer vers un bac à sable.
Les seuils de classement sont ici ; les règles de reconnaissance sont dans regles.toml.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

ICLOUD = "~/Library/Mobile Documents/com~apple~CloudDocs"
# Le dossier iCloud de l'app Raccourcis (« iCloud Drive/Shortcuts ») : un raccourci qui enregistre un fichier
# sans dossier choisi l'y dépose. On surveille les deux BoiteMac (D-12).
ICLOUD_RACCOURCIS = "~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents"

DEFAUTS: dict[str, Any] = {
    "actif": False,  # la surveillance en fond (python assistant.py activer trieur) ; les commandes marchent sans
    "dossier": "",  # vide : donnees/trieur de l'Assistant (base, archive, journal des actions)
    "mode_test": False,  # true : notifications vers le journal, rien dans Rappels (liste Trieur-TEST)
    "chemins": {
        "classes": "~/Documents/Classés",
        "a_trier": "~/Desktop/À trier",
        "photos": "~/Pictures/Depuis l'iPhone",
        "icloud": ICLOUD,
        "boite": "BoiteMac",  # sous iCloud Drive : l'entrée de l'iPhone
        "boite_raccourcis": ICLOUD_RACCOURCIS + "/BoiteMac",
        "telechargements": "~/Downloads",
        "services": "~/Library/Services",
    },
    # Où va chaque type, sous « Classés » ({annee}, {banque} et {emetteur} sont remplacés). Alignable sur tes
    # dossiers existants : « trieur arborescence » propose, sans rien déplacer.
    "arborescence": {
        "facture_achat": "Factures/{annee}",
        "ticket_caisse": "Factures/{annee}",
        "facture_service": "Factures/{annee}",
        "releve_bancaire": "Banque/{banque}/{annee}",
        "avis_imposition": "Impôts/{annee}",
        "quittance_loyer": "Logement",
        "bail_contrat": "Logement",
        "attestation": "Administratif",
        "bulletin_paie": "Administratif/Salaire/{annee}",
        "assurance": "Assurances",
        "billet_transport": "Transport & voyages/{annee}",
        "reservation": "Transport & voyages/{annee}",
        "sante": "Santé",
        "identite": "Identité",
        "devis": "Devis/{annee}",
        "facture_emise": "Micro-entreprise/Factures émises/{annee}",
        "garantie_notice": "Garanties/Notices",
        "courrier_admin": "Administratif",
        "autre": "Administratif",
        "notes": "Notes reçues",
        "a_verifier": "À vérifier",
        "garanties": "Garanties",
        "originaux": "Originaux/{annee}",
        "fichiers": "Fichiers/{extension}",
    },
    "classement": {
        "seuil_ia": 0.75,  # en dessous : Claude (si permis), sinon « À vérifier »
        "pages_analysees_debut": 3,  # un long PDF : les 3 premières pages et la dernière
        "photo_mots_min": 12,  # une photo avec moins de mots lus, sans structure de document, est une photo
        "nom_max": 120,
    },
    # Ta micro-entreprise : une facture où tu es l'émetteur est « émise ». Vide : seul l'indice « 293 B » joue.
    "identite": {"nom": "", "siret": ""},
    "telechargements": {"actif": True, "confiance_min": 0.9, "stabilite_s": 120},
    "stabilite": {"mesures": 3, "pas_s": 1.0, "delai_max_s": 300},
    "paralleles": 2,
    "ia": {
        "actif": True,
        "modele": "rapide",  # l'alias de l'Assistant (Claude Code) : haiku, le plus économique
        "budget_mensuel_usd": 1.0,
        "caracteres_max": 3000,
        "tarifs_usd_par_million": {"entree": 1.0, "sortie": 5.0},
        "delai_s": 60,
        "essais": 3,
        "types_sensibles": ["sante", "identite", "avis_imposition", "bulletin_paie"],
    },
    "garanties": {
        "liste_rappels": "Garanties",
        "rappels_jours_avant": [30, 7],
        "heure_rappel": "09:00",
        "verification_quotidienne": "09:00",
        "legale_neuf_mois": 24,
        "legale_occasion_mois": 12,
        "prix_min_eur": 30.0,  # en dessous, pas de fiche (un câble, une coque…)
        "retractation": True,
        "retractation_rappel_jours": 11,
        "retractation_jours": 14,
    },
    "notifications": {"grouper_au_dela": 3, "fenetre_s": 60},
}


def _meme_type(defaut: Any, lu: Any) -> bool:
    if isinstance(defaut, bool) or isinstance(lu, bool):
        return isinstance(defaut, bool) and isinstance(lu, bool)
    if isinstance(defaut, (int, float)):
        return isinstance(lu, (int, float))
    if isinstance(defaut, list):
        return isinstance(lu, list)
    return isinstance(lu, type(defaut))


def fusionner(defauts: dict[str, Any], perso: dict[str, Any], erreurs: list[str], chemin: str = "") -> dict[str, Any]:
    """Les valeurs par défaut, remplacées par les tiennes quand elles ont le bon type."""
    resultat = copy.deepcopy(defauts)
    for cle, lu in perso.items():
        ici = f"{chemin}{cle}"
        if cle not in defauts:
            erreurs.append(f"modules.trieur.{ici} : réglage inconnu, ignoré")
            continue
        defaut = defauts[cle]
        if isinstance(defaut, dict) and isinstance(lu, dict):
            resultat[cle] = fusionner(defaut, lu, erreurs, f"{ici}.")
        elif _meme_type(defaut, lu):
            resultat[cle] = copy.deepcopy(lu)
        else:
            erreurs.append(f"modules.trieur.{ici} : valeur {lu!r} invalide, j'utilise {defaut!r}")
    return resultat


def charger(perso: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    """(réglages complets, erreurs). Sans « perso » : lus dans reglages.json."""
    if perso is None:
        from core import config

        perso = config.charger()["modules"].get("trieur", {})
    erreurs: list[str] = []
    return fusionner(DEFAUTS, perso if isinstance(perso, dict) else {}, erreurs), erreurs


def chemin(reglages: dict[str, Any], cle: str) -> Path:
    """Un des chemins réglables, ~ déplié. « boite » est sous iCloud Drive."""
    brut = reglages["chemins"][cle]
    if cle == "boite":
        return Path(reglages["chemins"]["icloud"]).expanduser() / brut
    return Path(brut).expanduser()


def dossier_donnees(reglages: dict[str, Any]) -> Path:
    """Base, archive, journal : le réglage « dossier », sinon $TRIEUR_DOSSIER, sinon donnees/trieur de l'Assistant."""
    choisi = reglages.get("dossier") or os.getenv("TRIEUR_DOSSIER", "")
    if choisi:
        return Path(choisi).expanduser()
    from core.config import DONNEES

    return DONNEES / "trieur"


def pour_le_bac_a_sable(racine: Path, perso: dict[str, Any] | None = None) -> dict[str, Any]:
    """Des réglages dont tous les chemins sont dans « racine » (tests, mode test du bout en bout)."""
    base = {
        "dossier": str(racine / "donnees"),
        "mode_test": True,
        "chemins": {
            "classes": str(racine / "Documents" / "Classés"),
            "a_trier": str(racine / "Bureau" / "À trier"),
            "photos": str(racine / "Images" / "Depuis l'iPhone"),
            "icloud": str(racine / "iCloud"),
            "boite": "BoiteMac",
            "boite_raccourcis": str(racine / "iCloud-Raccourcis" / "BoiteMac"),
            "telechargements": str(racine / "Téléchargements"),
            "services": str(racine / "Services"),
        },
    }
    erreurs: list[str] = []
    reglages = fusionner(DEFAUTS, base, erreurs)
    if perso:
        reglages = fusionner(reglages, perso, erreurs)
    if erreurs:
        raise ValueError("; ".join(erreurs))
    return reglages
