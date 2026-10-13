"""Chemins et réglages de Voix.

- Données : `~/Library/Application Support/Voix/` (réglages, alias et routines, journal, modèles, socket).
- Journaux (sans audio, caviardés) : `~/Library/Logs/Voix/`.
- `reglages.toml` est **à toi** : écrit une fois (commenté) à l'installation, jamais réécrit. Les choix automatiques
  (raccourci libre retenu, moteur choisi par le banc d'essai) vont dans `choix.json` ; une valeur que tu écris dans
  `reglages.toml` passe toujours devant.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NOM_APP = "Commandes Vocales"
SOCKET = "voix.sock"  # propre au projet, dans notre dossier (0700), droits 0600

DEFAUTS: dict[str, dict[str, Any]] = {
    "installation": {"prefixe_label": ""},
    "raccourci": {"combinaison": "auto"},
    "ecoute": {"silence_fin_ms": 500, "duree_max_s": 8.0, "seuil_maintien_ms": 350},
    "moteur": {"choix": "auto", "whisper_modele": "auto", "whisper_backend": "auto"},
    "eveil": {"actif": False, "seuil": 0.5, "refractaire_s": 2.0},
    "comprehension": {"seuil": 0.80, "marge_ambiguite": 0.06},
    "retour": {"sons": True, "parler": False, "voix": "auto", "duree_bulle_s": 2.0},
    "journal": {"actif": True, "taille": 100},
    "confirmation": {"delai_s": 5.0},
    "modules": {"delai_s": 10.0},
    "modeles": {"garder_au_chaud_min": 5},
    "ia": {"actif": False, "plafond_usd_mois": 0.50, "modele": "claude-haiku-5-5"},
}

# Bornes des réglages numériques : une valeur hors bornes est refusée (et la valeur par défaut gardée).
BORNES: dict[tuple[str, str], tuple[float, float]] = {
    ("ecoute", "silence_fin_ms"): (200, 2000),
    ("ecoute", "duree_max_s"): (2, 15),
    ("ecoute", "seuil_maintien_ms"): (150, 1000),
    ("eveil", "seuil"): (0.05, 0.99),
    ("eveil", "refractaire_s"): (0.5, 10),
    ("comprehension", "seuil"): (0.5, 0.99),
    ("comprehension", "marge_ambiguite"): (0.0, 0.3),
    ("retour", "duree_bulle_s"): (0.5, 10),
    ("journal", "taille"): (0, 1000),
    ("confirmation", "delai_s"): (2, 30),
    ("modules", "delai_s"): (1, 60),
    ("modeles", "garder_au_chaud_min"): (0, 240),
    ("ia", "plafond_usd_mois"): (0, 0.50),
}
CHOIX_PERMIS: dict[tuple[str, str], tuple[str, ...]] = {
    ("moteur", "choix"): ("auto", "whisper", "apple"),
    ("moteur", "whisper_modele"): ("auto", "base", "small"),
    ("moteur", "whisper_backend"): ("auto", "mlx", "onnx"),
}


@dataclass(frozen=True)
class Chemins:
    maison: Path

    @property
    def support(self) -> Path:
        return self.maison / "Library" / "Application Support" / "Voix"

    @property
    def logs(self) -> Path:
        return self.maison / "Library" / "Logs" / "Voix"

    @property
    def socket(self) -> Path:
        return self.support / SOCKET

    @property
    def reglages(self) -> Path:
        return self.support / "reglages.toml"

    @property
    def choix(self) -> Path:
        return self.support / "choix.json"

    @property
    def commandes(self) -> Path:
        return self.support / "commandes.toml"

    @property
    def journal(self) -> Path:
        return self.support / "journal.jsonl"

    @property
    def etat(self) -> Path:
        return self.support / "etat.json"

    @property
    def minuteurs(self) -> Path:
        return self.support / "minuteurs.json"

    @property
    def modeles(self) -> Path:
        return self.support / "modeles"

    @property
    def verrou(self) -> Path:
        return self.support / ".verrou"

    @property
    def aide_memoire(self) -> Path:
        return self.support / "aide-memoire.html"

    @property
    def launch_agents(self) -> Path:
        return self.maison / "Library" / "LaunchAgents"

    @property
    def app(self) -> Path:
        return self.maison / "Applications" / f"{NOM_APP}.app"

    @property
    def bin(self) -> Path:
        return self.maison / ".local" / "bin"

    def preparer(self) -> None:
        """Nos dossiers, privés (0700). Rien n'est créé ailleurs."""
        for d in (self.support, self.logs, self.modeles):
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o700)


def chemins_par_defaut() -> Chemins:
    return Chemins(Path(os.environ.get("VOIX_MAISON") or Path.home()))


@dataclass
class Reglages:
    valeurs: dict[str, dict[str, Any]]
    erreurs: list[str] = field(default_factory=list)
    choix: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, section: str) -> dict[str, Any]:
        return self.valeurs[section]

    def prefixe(self) -> str:
        brut = str(self.valeurs["installation"].get("prefixe_label") or "") or getpass.getuser()
        return re.sub(r"[^A-Za-z0-9_-]", "", brut) or "utilisateur"

    def label_moteur(self) -> str:
        return f"com.{self.prefixe()}.voix"

    def label_app(self) -> str:
        return f"com.{self.prefixe()}.voix.app"

    def raccourci(self) -> str:
        """La combinaison retenue : la tienne si tu l'as écrite, sinon celle choisie à l'installation."""
        brut = str(self.valeurs["raccourci"].get("combinaison") or "auto")
        if brut != "auto":
            return brut
        return str(self.choix.get("raccourci") or "ctrl+option+espace")

    def moteur(self) -> str:
        brut = str(self.valeurs["moteur"]["choix"])
        if brut != "auto":
            return brut
        return str(self.choix.get("moteur") or "whisper")

    def whisper(self) -> tuple[str, str]:
        """(modèle, backend) : les tiens, sinon ceux du banc d'essai, sinon small sur mlx (Apple Silicon)."""
        modele = str(self.valeurs["moteur"]["whisper_modele"])
        backend = str(self.valeurs["moteur"]["whisper_backend"])
        if modele == "auto":
            modele = str(self.choix.get("whisper_modele") or "small")
        if backend == "auto":
            backend = str(self.choix.get("whisper_backend") or "mlx")
        return modele, backend


def _fusionner(lues: dict[str, Any], erreurs: list[str]) -> dict[str, dict[str, Any]]:
    valeurs = {section: dict(cles) for section, cles in DEFAUTS.items()}
    for section, cles in lues.items():
        if section not in DEFAUTS:
            erreurs.append(f"section inconnue ignorée : [{section}]")
            continue
        if not isinstance(cles, dict):
            erreurs.append(f"[{section}] doit être une section")
            continue
        for cle, valeur in cles.items():
            if cle not in DEFAUTS[section]:
                erreurs.append(f"réglage inconnu ignoré : {section}.{cle}")
                continue
            defaut = DEFAUTS[section][cle]
            if isinstance(defaut, bool):
                if not isinstance(valeur, bool):
                    erreurs.append(f"{section}.{cle} doit valoir true ou false")
                    continue
            elif isinstance(defaut, (int, float)):
                if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
                    erreurs.append(f"{section}.{cle} doit être un nombre")
                    continue
                bornes = BORNES.get((section, cle))
                if bornes and not bornes[0] <= valeur <= bornes[1]:
                    erreurs.append(f"{section}.{cle} = {valeur} hors bornes [{bornes[0]}, {bornes[1]}] : ignoré")
                    continue
                valeur = type(defaut)(valeur) if isinstance(defaut, float) else valeur
            elif isinstance(defaut, str):
                if not isinstance(valeur, str):
                    erreurs.append(f"{section}.{cle} doit être un texte")
                    continue
                permis = CHOIX_PERMIS.get((section, cle))
                if permis and valeur not in permis:
                    erreurs.append(f"{section}.{cle} = {valeur!r} : choix possibles {', '.join(permis)}")
                    continue
            valeurs[section][cle] = valeur
    return valeurs


def charger(chemins: Chemins) -> Reglages:
    erreurs: list[str] = []
    lues: dict[str, Any] = {}
    if chemins.reglages.exists():
        try:
            lues = tomllib.loads(chemins.reglages.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
            erreurs.append(f"reglages.toml illisible ({e}) : réglages par défaut")
    choix: dict[str, Any] = {}
    if chemins.choix.exists():
        try:
            brut = json.loads(chemins.choix.read_text(encoding="utf-8"))
            choix = brut if isinstance(brut, dict) else {}
        except (ValueError, OSError):
            erreurs.append("choix.json illisible : choix automatiques par défaut")
    return Reglages(_fusionner(lues, erreurs), erreurs, choix)


def ecrire_choix(chemins: Chemins, **nouveaux: Any) -> dict[str, Any]:
    """Ajoute des choix automatiques (raccourci retenu, moteur du banc d'essai) sans toucher au reste."""
    chemins.preparer()
    actuels: dict[str, Any] = {}
    if chemins.choix.exists():
        try:
            brut = json.loads(chemins.choix.read_text(encoding="utf-8"))
            actuels = brut if isinstance(brut, dict) else {}
        except (ValueError, OSError):
            actuels = {}
    actuels.update(nouveaux)
    ecrire_atomique(chemins.choix, json.dumps(actuels, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return actuels


def ecrire_atomique(cible: Path, texte: str, droits: int = 0o600) -> None:
    temporaire = cible.with_name(f".{cible.name}.tmp")
    temporaire.write_text(texte, encoding="utf-8")
    os.chmod(temporaire, droits)
    temporaire.replace(cible)


MODELE_REGLAGES = """\
# Réglages de Voix. Ce fichier est à toi : Voix ne le réécrit jamais.
# Une ligne commentée (#) garde la valeur par défaut. Après un changement : voix recharger

[raccourci]
# « auto » : ⌃⌥Espace, ou le premier raccourci libre si macOS l'utilise déjà (voir voix doctor).
# Exemples : "ctrl+option+espace", "ctrl+option+cmd+espace", "ctrl+option+v"
# combinaison = "auto"

[ecoute]
# silence_fin_ms = 500     # silence qui termine la phrase (appui simple)
# duree_max_s = 8          # écoute maximale après un appui simple
# seuil_maintien_ms = 350  # touche gardée plus longtemps : mode « maintenir »

[moteur]
# choix = "auto"           # auto (choisi par le banc d'essai), whisper ou apple
# whisper_modele = "auto"  # auto, base ou small
# whisper_backend = "auto" # auto, mlx (Apple Silicon) ou onnx

[eveil]
# actif = false            # mot d'éveil « hey jarvis » : le point orange du micro reste allumé
# seuil = 0.5
# refractaire_s = 2

[comprehension]
# seuil = 0.80             # en dessous : « Je n'ai pas compris » et 3 suggestions

[retour]
# sons = true
# parler = false           # réponse parlée courte (say)
# voix = "auto"            # une voix française de « say -v '?' »
# duree_bulle_s = 2

[journal]
# actif = true             # les 100 dernières commandes, en local (voix oublier pour l'effacer)
# taille = 100

[confirmation]
# delai_s = 5

[ia]
# actif = false            # Claude choisit une intention de la liste blanche pour une phrase non comprise
# plafond_usd_mois = 0.50
"""
