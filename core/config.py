"""Réglages de l'assistant (reglages.json) et chemins partagés.

reglages.json est TON fichier : il reste sur ton Mac (jamais sur GitHub).
S'il n'existe pas, il est créé avec les valeurs par défaut ci-dessous.
Une valeur invalide n'arrête rien : elle est remplacée par sa valeur par défaut
et l'erreur est notée dans le journal.
"""

import copy
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"  # état, mémoire… : jamais sur GitHub
LOGS = RACINE / "logs"
FICHIER_REGLAGES = RACINE / "reglages.json"

load_dotenv(RACINE / ".env")

NIVEAUX_PROACTIVITE = {0: "muet", 1: "discret", 2: "normal", 3: "présent"}
CAPTEURS = {"oreilles": "micro", "yeux": "ecran"}  # modules coupés par « pause micro » / « pause écran »

DEFAUTS = {
    "pause_globale": False,
    "pause_micro": False,
    "pause_ecran": False,
    "niveau_proactivite": 2,
    "heures_silencieuses": {"debut": "22:30", "fin": "07:30"},
    "claude": {"modele_rapide": "haiku", "modele_fort": "sonnet", "appels_max_par_jour": 60},
    "modules": {
        "battement": {"actif": True, "toutes_les_secondes": 60},
        "mails": {
            "actif": False,
            "toutes_les_secondes": 180,
            "modele": "fort",
            "regle_r1_promotions": True,
            "regle_r2_reseaux_sociaux": True,
            "rattrapage_premier_passage_heures": 24,
        },
        "oreilles": {
            "actif": False,
            "mode": "passif",
            "mot_appel": "assistant",
            "modele_transcription": "small",
            "uniquement_sur_secteur": False,
            "micro": None,
        },
        "yeux": {"actif": False, "applis_exclues": ["Banque", "1Password", "Messages", "WhatsApp"]},
    },
}

_HEURE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_dernier_valide: dict | None = None


def _fusionner(base: dict, perso: dict) -> dict:
    """Les valeurs par défaut, complétées et remplacées par les tiennes."""
    resultat = copy.deepcopy(base)
    for cle, valeur in perso.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = _fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = copy.deepcopy(valeur)
    return resultat


def _nettoyer(r: dict, erreurs: list) -> dict:
    """Remplace chaque valeur invalide par sa valeur par défaut, en notant pourquoi."""

    def remettre(chemin: str, lu, defaut, attendu: str):
        erreurs.append(f"{chemin} : {attendu} (valeur lue : {lu!r}), j'utilise {defaut!r}")
        return copy.deepcopy(defaut)

    for cle in ("pause_globale", "pause_micro", "pause_ecran"):
        if not isinstance(r[cle], bool):
            r[cle] = remettre(cle, r[cle], False, "true ou false attendu")
    n = r["niveau_proactivite"]
    if isinstance(n, bool) or n not in NIVEAUX_PROACTIVITE:
        r["niveau_proactivite"] = remettre("niveau_proactivite", n, 2, "0, 1, 2 ou 3 attendu")

    hs = r["heures_silencieuses"]
    if not isinstance(hs, dict):
        r["heures_silencieuses"] = remettre("heures_silencieuses", hs, DEFAUTS["heures_silencieuses"], "objet attendu")
    else:
        for cle in ("debut", "fin"):
            if not isinstance(hs.get(cle), str) or not _HEURE.match(hs[cle]):
                hs[cle] = remettre(f"heures_silencieuses.{cle}", hs.get(cle),
                                   DEFAUTS["heures_silencieuses"][cle], "heure HH:MM attendue")

    cl = r["claude"]
    if not isinstance(cl, dict):
        r["claude"] = remettre("claude", cl, DEFAUTS["claude"], "objet attendu")
    else:
        for cle in ("modele_rapide", "modele_fort"):
            if not isinstance(cl.get(cle), str) or not cl[cle].strip():
                cl[cle] = remettre(f"claude.{cle}", cl.get(cle), DEFAUTS["claude"][cle], "nom de modèle attendu")
        m = cl.get("appels_max_par_jour")
        if isinstance(m, bool) or not isinstance(m, int) or m < 0:
            cl["appels_max_par_jour"] = remettre("claude.appels_max_par_jour", m, 60, "nombre entier ≥ 0 attendu")

    if not isinstance(r["modules"], dict):
        r["modules"] = remettre("modules", r["modules"], DEFAUTS["modules"], "objet attendu")
    for nom, reglage in list(r["modules"].items()):
        if not isinstance(reglage, dict):
            r["modules"][nom] = {"actif": False}
            erreurs.append(f"modules.{nom} : objet attendu, module désactivé")
        elif not isinstance(reglage.get("actif"), bool):
            erreurs.append(f"modules.{nom}.actif : true ou false attendu, module désactivé")
            reglage["actif"] = False
    return r


def charger_avec_erreurs() -> tuple[dict, list[str]]:
    """Lit reglages.json. Renvoie (réglages utilisables, liste des problèmes trouvés)."""
    global _dernier_valide
    if not FICHIER_REGLAGES.exists():
        ecrire(DEFAUTS)
    erreurs: list[str] = []
    try:
        perso = json.loads(FICHIER_REGLAGES.read_text(encoding="utf-8"))
        if not isinstance(perso, dict):
            raise ValueError("le fichier doit contenir un objet { … }")
    except (json.JSONDecodeError, ValueError, OSError) as e:
        erreurs.append(f"reglages.json illisible ({e}) : je garde les derniers réglages valides")
        return copy.deepcopy(_dernier_valide or DEFAUTS), erreurs
    reglages = _nettoyer(_fusionner(DEFAUTS, perso), erreurs)
    _dernier_valide = reglages
    return copy.deepcopy(reglages), erreurs


def charger() -> dict:
    return charger_avec_erreurs()[0]


def ecrire(reglages: dict) -> None:
    """Écriture atomique : le fichier n'est jamais à moitié écrit, même en cas de coupure."""
    temporaire = FICHIER_REGLAGES.with_name(f".reglages.{os.getpid()}.tmp")
    temporaire.write_text(json.dumps(reglages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporaire, FICHIER_REGLAGES)


def _modifier(changement) -> None:
    """Change une valeur de reglages.json sans toucher au reste. Fonctionne même si tu as
    cassé le fichier en l'éditant : ta version est mise de côté (reglages.json.casse-…), jamais effacée."""
    try:
        perso = json.loads(FICHIER_REGLAGES.read_text(encoding="utf-8")) if FICHIER_REGLAGES.exists() else {}
        if not isinstance(perso, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        copie = FICHIER_REGLAGES.with_name(f"reglages.json.casse-{time.strftime('%Y%m%d-%H%M%S')}")
        FICHIER_REGLAGES.rename(copie)
        perso = copy.deepcopy(_dernier_valide or DEFAUTS)
    changement(perso)
    ecrire(perso)


def mettre_en_pause(pause: bool) -> None:
    """L'interrupteur maître : fonctionne toujours, même avec un fichier cassé."""
    _modifier(lambda perso: perso.__setitem__("pause_globale", pause))


def mettre_capteur_en_pause(capteur: str, pause: bool) -> None:
    """« micro » ou « ecran » : coupe (ou rallume) les modules qui l'utilisent."""
    _modifier(lambda perso: perso.__setitem__(f"pause_{capteur}", pause))


def activer_module(nom: str, actif: bool) -> None:
    def changement(perso: dict) -> None:
        if not isinstance(perso.get("modules"), dict):
            perso["modules"] = {}
        if not isinstance(perso["modules"].get(nom), dict):
            perso["modules"][nom] = {}
        perso["modules"][nom]["actif"] = actif

    _modifier(changement)
