"""Réglages du Nettoyeur : reglages.json → modules.demarrage, complétés par les valeurs par défaut ci-dessous.

Une valeur invalide (mauvais type) n'arrête rien : elle est remplacée par la valeur par défaut et signalée.
Tous les seuils (mesure, scores, verdicts) sont ici, rien n'est codé en dur ailleurs.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

DEFAUTS: dict[str, Any] = {
    "actif": False,  # la surveillance en fond (« demarrage surveiller on ») ; scan, mesure et rapport marchent sans
    "dossier": "",  # vide : donnees/demarrage de l'Assistant
    "echantillonnage": {
        "session_minutes": 5,  # mode « ouverture de session » : juste après la connexion
        "session_pas_s": 5,
        "croisiere_pas_s": 120,
        "energie_pas_s": 600,  # « top » (impact énergétique), en croisière seulement
    },
    "calme": {"seuil_cpu_pct": 15.0, "duree_s": 30},  # le Mac est « calme » sous 15 % pendant 30 s de suite
    "retention_jours": 60,
    "zsh": {"essais": 5, "seuil_ms": 300},
    "scores": {
        # Score d'impact (0 à 100) = 100 × Σ poids × min(1, mesure / référence), plus des bonus.
        "poids": {"cpu_session": 0.45, "cpu_croisiere": 0.2, "memoire": 0.2, "energie": 0.15},
        "references": {
            "cpu_session_s": 30.0,  # secondes de processeur pendant les 5 premières minutes de session
            "cpu_croisiere_pct": 5.0,  # processeur moyen ensuite
            "memoire_mo": 500.0,  # mémoire médiane
            "energie": 10.0,  # impact énergétique moyen (colonne POWER de top)
        },
        "bonus_veille": 30.0,  # empêche le Mac de se mettre en veille
        "bonus_boucle": 15.0,  # relancé en boucle par KeepAlive, avec des sorties en erreur
        "relances_boucle": 5,  # à partir de combien de lancements on parle de boucle
        # Pas encore mesuré : l'impact typique de la base de connaissances, affiché « estimé ».
        "impact_estime": {"faible": 3.0, "moyen": 12.0, "fort": 30.0},
    },
    "verdicts": {
        "impact_significatif": 20.0,  # au-delà : il coûte vraiment
        "impact_negligeable": 5.0,  # en dessous : on peut le garder sans y penser
        "utilite_jours": 30,  # app pas ouverte depuis plus longtemps : utilité faible
        # Un simple outil de mise à jour peut tourner quand on ouvre l'app plutôt qu'au démarrage.
        # (« helper » seul est trop large : l'assistant réseau de Docker ou d'un VPN n'est pas une mise à jour.)
        "motifs_mise_a_jour": ["updat", "keystone", "autoupdate", "shipit", "softwareupdate"],
        "veille_part_min": 0.05,  # « empêche la veille » s'il la bloque dans au moins 5 % des relevés
        "fenetre_jours": 7,  # les mesures de croisière des 7 derniers jours
        "sessions_retenues": 5,  # la médiane des 5 dernières ouvertures de session
        # L'ordre des règles de verdict (la première qui s'applique l'emporte), voir analyse/verdicts.py.
        "ordre": ["apple", "moi", "orphelin", "inconnu", "inactif", "mise_a_jour", "lourd_inutile", "utile"],
    },
    "notifications": {"silence_debut": "23:00", "silence_fin": "08:00", "vers_journal": False},
    "delais": {"commande_s": 10.0, "osascript_s": 10.0, "journal_systeme_s": 15.0, "codesign_s": 5.0},
}


def _meme_type(defaut: Any, lu: Any) -> bool:
    if isinstance(defaut, bool) or isinstance(lu, bool):
        return isinstance(defaut, bool) and isinstance(lu, bool)
    if isinstance(defaut, (int, float)):
        return isinstance(lu, (int, float))
    if isinstance(defaut, list):
        return isinstance(lu, list) and all(isinstance(x, str) for x in lu)
    return isinstance(lu, type(defaut))


def fusionner(defauts: dict[str, Any], perso: dict[str, Any], erreurs: list[str], chemin: str = "") -> dict[str, Any]:
    """Les valeurs par défaut, remplacées par les tiennes quand elles ont le bon type."""
    resultat = copy.deepcopy(defauts)
    for cle, lu in perso.items():
        ici = f"{chemin}{cle}"
        if cle not in defauts:
            erreurs.append(f"modules.demarrage.{ici} : réglage inconnu, ignoré")
            continue
        defaut = defauts[cle]
        if isinstance(defaut, dict) and isinstance(lu, dict):
            resultat[cle] = fusionner(defaut, lu, erreurs, f"{ici}.")
        elif _meme_type(defaut, lu):
            resultat[cle] = copy.deepcopy(lu)
        else:
            erreurs.append(f"modules.demarrage.{ici} : valeur {lu!r} invalide, j'utilise {defaut!r}")
    return resultat


def charger(perso: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    """(réglages complets, erreurs). Sans « perso » : lus dans reglages.json."""
    if perso is None:
        from core import config

        perso = config.charger()["modules"].get("demarrage", {})
    erreurs: list[str] = []
    return fusionner(DEFAUTS, perso if isinstance(perso, dict) else {}, erreurs), erreurs


def dossier_donnees(reglages: dict[str, Any]) -> Path:
    """Où tout est rangé : le réglage « dossier », sinon $DEMARRAGE_DOSSIER, sinon donnees/demarrage de l'Assistant."""
    choisi = reglages.get("dossier") or os.getenv("DEMARRAGE_DOSSIER", "")
    if choisi:
        return Path(choisi).expanduser()
    from core import config

    return config.DONNEES / "demarrage"
