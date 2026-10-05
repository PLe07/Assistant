"""Réglages du détecteur : reglages.json → modules.corvees, complétés par les valeurs par défaut ci-dessous.

Une valeur invalide (mauvais type) n'arrête rien : elle est remplacée par la valeur par défaut et signalée.
Tous les seuils de détection sont ici, rien n'est codé en dur ailleurs.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

# fmt: off
APPLIS_EXCLUES = [
    # Mots de passe et secrets
    "1Password", "Bitwarden", "Dashlane", "LastPass", "KeePassXC", "Enpass", "Proton Pass", "Mots de passe",
    "Passwords", "Trousseau d'accès", "Trousseaux d'accès", "Keychain Access", "com.apple.Passwords",
    "com.apple.keychainaccess", "com.1password", "com.agilebits", "com.bitwarden", "com.dashlane", "com.lastpass",
    "org.keepassxc", "me.proton.pass",
    # Messageries et appels
    "Messages", "FaceTime", "WhatsApp", "Signal", "Telegram", "Messenger", "com.apple.MobileSMS",
    "com.apple.FaceTime", "net.whatsapp", "org.whispersystems", "ru.keepcoder.telegram", "com.facebook.archon",
    # Banques et paiement
    "Boursorama", "BoursoBank", "Crédit Agricole", "Ma Banque", "LCL", "Mes Comptes", "BNP Paribas",
    "Société Générale", "La Banque Postale", "Caisse d'Epargne", "Caisse d'Épargne", "Banque Populaire", "CIC",
    "Crédit Mutuel", "Fortuneo", "Hello bank", "Revolut", "N26", "Qonto", "Shine", "Lydia", "Sumeria",
    "Trade Republic", "PayPal",
]
DOMAINES_EXCLUS = [
    "credit-agricole.fr", "ca-paris.fr", "lcl.fr", "bnpparibas", "societegenerale.fr", "sg.fr", "boursorama.com",
    "boursobank.com", "labanquepostale.fr", "caisse-epargne.fr", "cic.fr", "creditmutuel.fr", "banquepopulaire.fr",
    "fortuneo.fr", "hellobank.fr", "revolut.com", "n26.com", "qonto.com", "paypal.com", "lydia-app.com",
    "impots.gouv.fr", "ameli.fr", "doctolib.fr", "caf.fr", "monespacesante.fr", "franceconnect.gouv.fr",
    "francetravail.fr", "pole-emploi.fr",
]
# fmt: on

DEFAUTS: dict[str, Any] = {
    "actif": False,
    "dossier": "",  # vide : donnees/corvees de l'Assistant (un autre chemin pour les essais)
    "capteurs": {
        "apps": True,
        "fenetres": True,
        "fichiers": True,
        "shell": True,
        "navigateur": True,
        "pressepapiers": True,
        "inactivite": True,
    },
    "fichiers": {"dossiers": ["~/Downloads", "~/Desktop", "~/Documents"], "profondeur": 4},
    "shell": {"historique": "~/.zsh_history"},
    "navigateurs": ["chrome", "brave", "arc", "edge", "safari"],
    "exclusions": {"applis": [], "domaines": [], "dossiers": []},  # en plus des listes de base ci-dessus
    "sessions": {"inactivite_min": 10},
    "detection": {
        "fenetre_jours": 30,
        "sequences": {
            "longueur_min": 3,
            "longueur_max": 8,
            "jours_min": 3,
            "parasites_max": 1,
            "lift_min": 8.0,
            "tolerance_maximale": 0.8,
        },
        "routines": {
            "tolerance_min": 45,
            "jours_min": 3,
            "sur_jours": 14,
            "semaines_min": 3,
            "concentration_min": 0.6,
            "concentration_semaine_min": 0.75,
            "jours_min_sequence": 4,  # pour donner un créneau à une suite d'actions
        },
        "fichiers": {"occurrences_min": 4, "jours_min": 2},
        "ponts": {
            "occurrences_min": 5,
            "jours_min": 3,
            "alpha": 0.05,
        },  # alpha : risque de prendre le hasard pour un pont
        "shell": {"longueur_min": 2, "occurrences_min": 4, "lift_min": 3.0},
    },
    "scoring": {
        # Facteur d'automatisabilité par type de corvée (1 = s'automatise sans peine).
        "automatisabilite": {
            "fichiers": 1.0,
            "shell": 1.0,
            "routine": 0.9,  # une corvée à heure fixe s'automatise facilement (Raccourcis, launchd)
            "sequence": 0.6,
            "pont": 0.5,
        },
        # Durée d'une étape faite à la main, quand rien ne permet de la mesurer (secondes).
        "secondes_par_etape": {
            "app": 3,
            "url": 6,
            "fen": 3,
            "fmove": 20,
            "fren": 20,
            "fcreate": 5,
            "fconv": 40,
            "fdel": 8,
            "clip": 12,
            "cmd": 8,  # par commande (une ligne « a && b » en compte deux)
        },
        "duree_max_s": 600,
        "facteur_action_instantanee": 0.1,  # ouvrir une seule appli ou un seul site
        "facteur_navigation_irreguliere": 0.1,  # suite d'applis/sites sans créneau ni jour fixe
        "score_min": 3.0,
        "top": 10,
    },
    "analyse": {"heure": "21:00", "batterie_min": 30},
    "notifications": {"silence_debut": "23:00", "silence_fin": "08:00"},
    "ia": {
        "actif": True,
        "modele": "rapide",  # « rapide » (économique, par défaut) ou « fort » (plus puissant)
        "max_candidats": 8,
        "budget_mensuel_usd": 2.0,
        # Dollars par million de jetons (Haiku 4.5 et Sonnet 5.5) : sert à estimer le coût de chaque appel.
        "tarifs": {"rapide": {"entree": 1.0, "sortie": 5.0}, "fort": {"entree": 2.0, "sortie": 10.0}},
        "delai_s": 180,
        "essais": 3,  # sur panne passagère (surcharge, quota, délai dépassé)
        "attente_s": 20,  # avant le 2e essai ; doublée avant le 3e
        "attente_max_s": 960,  # l'Assistant fait une pause de 15 min après un quota : on l'attend, sans plus
    },
    "installation": {
        "launchagents": "~/Library/LaunchAgents",
        "prefixe": "com.assistant.corvee",  # étiquette des tâches launchd installées par « accept --installer »
    },
    "retention_jours": 30,
    "ecriture_groupee_s": 30,
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
            if isinstance(defauts, dict) and chemin.endswith(("automatisabilite.", "secondes_par_etape.")):
                resultat[cle] = lu  # un type de plus, permis
            else:
                erreurs.append(f"modules.corvees.{ici} : réglage inconnu, ignoré")
            continue
        defaut = defauts[cle]
        if isinstance(defaut, dict) and isinstance(lu, dict):
            resultat[cle] = fusionner(defaut, lu, erreurs, f"{ici}.")
        elif _meme_type(defaut, lu):
            resultat[cle] = copy.deepcopy(lu)
        else:
            erreurs.append(f"modules.corvees.{ici} : valeur {lu!r} invalide, j'utilise {defaut!r}")
    return resultat


def charger(perso: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    """(réglages complets, erreurs). Sans « perso » : lus dans reglages.json."""
    if perso is None:
        from core import config

        perso = config.charger()["modules"].get("corvees", {})
    erreurs: list[str] = []
    return fusionner(DEFAUTS, perso if isinstance(perso, dict) else {}, erreurs), erreurs


def dossier_donnees(reglages: dict[str, Any]) -> Path:
    """Où tout est rangé : le réglage « dossier », sinon $CORVEES_DOSSIER, sinon donnees/corvees de l'Assistant."""
    choisi = reglages.get("dossier") or os.getenv("CORVEES_DOSSIER", "")
    if choisi:
        return Path(choisi).expanduser()
    from core import config

    return config.DONNEES / "corvees"


def applis_exclues(reglages: dict[str, Any]) -> list[str]:
    return APPLIS_EXCLUES + list(reglages["exclusions"]["applis"])


def domaines_exclus(reglages: dict[str, Any]) -> list[str]:
    return DOMAINES_EXCLUS + list(reglages["exclusions"]["domaines"])
