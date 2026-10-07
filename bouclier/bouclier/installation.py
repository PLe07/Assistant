"""Ce que `install.sh` et `uninstall.sh` posent sur le Mac, et rien d'autre :

- le LaunchAgent `com.<session>.bouclier` (D-04) dans ~/Library/LaunchAgents ;
- le lanceur `~/.local/bin/bouclier` (seulement si la commande est libre ou déjà à nous) ;
- les 3 actions rapides dans ~/Library/Services (paquets `fr.bouclier.*`) ;
- les 2 raccourcis signés dans iCloud Drive/Bouclier ;
- nos dossiers (~/Library/Application Support/Bouclier, ~/Library/Logs/Bouclier, iCloud Drive/Bouclier).

Chaque étape peut être relancée sans effet de bord ; un fichier du même nom qui n'est pas à Bouclier n'est jamais
touché (on s'arrête et on l'explique).
"""

from __future__ import annotations

import getpass
import os
import plistlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bouclier import config
from bouclier.raccourcis import actions_rapides, generer
from bouclier.systeme import Systeme
from bouclier.urgence import infos

MARQUE_LANCEUR = "# lanceur de Bouclier"
PATH_DEMON = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def prefixe(reglages: dict[str, Any]) -> str:
    """Le nom de ta session macOS (comme les autres projets), ou celui choisi dans config.toml."""
    brut = str(reglages.get("installation", {}).get("prefixe_label") or "") or getpass.getuser()
    return re.sub(r"[^a-z0-9-]", "", brut.lower()) or "utilisateur"


def label(reglages: dict[str, Any]) -> str:
    return f"com.{prefixe(reglages)}.bouclier"


def plist_agent(lab: str, python: Path, projet: Path, logs: Path, maison: Path) -> dict[str, Any]:
    return {
        "Label": lab,
        "ProgramArguments": [str(python), "-m", "bouclier", "demon"],
        "WorkingDirectory": str(projet),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "demon.sortie.log"),
        "StandardErrorPath": str(logs / "demon.erreurs.log"),
        "EnvironmentVariables": {
            "PATH": f"{maison}/.local/bin:{PATH_DEMON}",
            "LANG": "fr_FR.UTF-8",
            "PYTHONUNBUFFERED": "1",
        },  # fmt: skip
    }


def chemin_agent(chemins: config.Chemins, lab: str) -> Path:
    return chemins.launch_agents / f"{lab}.plist"


def agent_est_a_nous(chemin: Path) -> bool:
    try:
        with chemin.open("rb") as f:
            p = plistlib.load(f)
        return list(p.get("ProgramArguments", []))[1:] == ["-m", "bouclier", "demon"]
    except (OSError, plistlib.InvalidFileException, ValueError):
        return False


def lanceur(chemins: config.Chemins) -> Path:
    return chemins.maison / ".local" / "bin" / "bouclier"


def lanceur_est_a_nous(chemin: Path) -> bool:
    try:
        return MARQUE_LANCEUR in chemin.read_text(encoding="utf-8", errors="replace")[:500]
    except OSError:
        return False


@dataclass
class Bilan:
    fait: list[str] = field(default_factory=list)
    refus: list[str] = field(default_factory=list)  # ce qui n'est pas à nous : on n'y touche pas
    avertissements: list[str] = field(default_factory=list)


def collisions(chemins: config.Chemins, reglages: dict[str, Any]) -> list[str]:
    """Avant toute installation : la commande `bouclier` et le label sont-ils libres (ou déjà à nous) ?"""
    refus = []
    commande = shutil.which("bouclier")
    if commande and not lanceur_est_a_nous(Path(commande)) and Path(commande) != lanceur(chemins):
        refus.append(f"une autre commande « bouclier » existe déjà ({commande})")
    lien = lanceur(chemins)
    if lien.exists() and not lanceur_est_a_nous(lien):
        refus.append(f"{lien} existe déjà et n'est pas le lanceur de Bouclier")
    agent = chemin_agent(chemins, label(reglages))
    if agent.exists() and not agent_est_a_nous(agent):
        refus.append(f"{agent} existe déjà et n'est pas l'agent de Bouclier")
    return refus


def preparer(chemins: config.Chemins, reglages: dict[str, Any], python: Path, projet: Path) -> Bilan:
    """Dossiers, réglages, lanceur, actions rapides, LaunchAgent (sans le charger : install.sh s'en charge)."""
    b = Bilan()
    b.refus = collisions(chemins, reglages)
    if b.refus:
        return b
    config.preparer_dossiers(chemins)
    if config.ecrire_modele_si_absent(chemins):
        b.fait.append(f"réglages créés : {chemins.config}")
    if infos.ecrire_modele_si_absent(chemins.infos_urgence):
        b.fait.append(f"tes infos pour la fiche urgence (à remplir si tu veux) : {chemins.infos_urgence}")
    lien = lanceur(chemins)
    lien.parent.mkdir(parents=True, exist_ok=True)
    lien.write_text(f'#!/bin/zsh\n{MARQUE_LANCEUR} ({projet})\nexec "{python}" -m bouclier "$@"\n', encoding="utf-8")
    os.chmod(lien, 0o755)
    b.fait.append(f"commande bouclier : {lien}")
    for nom, resultat in actions_rapides.installer(chemins.services, lien):
        (b.fait if resultat == "installée" else b.refus).append(f"action rapide « {nom} » : {resultat}")
    lab = label(reglages)
    agent = chemin_agent(chemins, lab)
    agent.parent.mkdir(parents=True, exist_ok=True)
    with agent.open("wb") as f:
        plistlib.dump(plist_agent(lab, python, projet, chemins.logs, chemins.maison), f)
    b.fait.append(f"agent de démarrage : {agent}")
    if chemins.icloud_drive.is_dir():
        for d in (chemins.icloud / "entree", chemins.icloud / "reponses"):
            d.mkdir(parents=True, exist_ok=True)
        b.fait.append(f"dossier iCloud : {chemins.icloud}")
    else:
        b.avertissements.append("iCloud Drive introuvable : le raccourci « Arnaque ? » ne pourra pas joindre le Mac")
    return b


def raccourcis(chemins: config.Chemins) -> Bilan:
    """Les 2 raccourcis : écrits, vérifiés (`plutil -lint`), signés dans iCloud Drive/Bouclier."""
    b = Bilan()
    for fichier in generer.ecrire(chemins.sorties / "raccourcis"):
        ok, message = generer.plutil_lint(fichier)
        if not ok:
            b.refus.append(f"{fichier.name} : plist invalide ({message})")
            continue
        nom = fichier.name.replace(".non-signé", "")
        if not chemins.icloud_drive.is_dir():
            b.avertissements.append(f"{nom} : pas d'iCloud Drive pour le déposer")
            continue
        chemins.icloud.mkdir(exist_ok=True)
        ok, message = generer.signer(fichier, chemins.icloud / nom)
        if ok:
            b.fait.append(f"raccourci signé : {chemins.icloud / nom}")
        else:
            b.avertissements.append(f"{nom} non signé ({message}) : recette manuelle dans ACTIONS_HUMAINES.md")
    return b


def desinstaller(chemins: config.Chemins, reglages: dict[str, Any], tout: bool = False) -> Bilan:
    """Retire ce que Bouclier a posé (l'agent doit déjà être arrêté par uninstall.sh). Tes données restent, sauf
    `tout` ; le dossier iCloud Bouclier reste toujours (il est dans ton iCloud : à toi de le supprimer)."""
    b = Bilan()
    agent = chemin_agent(chemins, label(reglages))
    if agent.exists() and agent_est_a_nous(agent):
        agent.unlink()
        b.fait.append(f"agent retiré : {agent}")
    lien = lanceur(chemins)
    if lien.exists() and lanceur_est_a_nous(lien):
        lien.unlink()
        b.fait.append(f"commande retirée : {lien}")
    for nom in actions_rapides.desinstaller(chemins.services):
        b.fait.append(f"action rapide retirée : {nom}")
    if tout:
        for d in (chemins.support, chemins.logs):
            if d.is_dir() and d.name == "Bouclier":
                shutil.rmtree(d)
                b.fait.append(f"données retirées : {d}")
    return b


@dataclass
class EtatAgent:
    charge: bool
    pid: int | None
    dernier_code: str | None


def etat_agent(systeme: Systeme, lab: str) -> EtatAgent:
    if not systeme.mac:
        return EtatAgent(False, None, None)
    r = systeme.executer(["launchctl", "print", f"gui/{os.getuid()}/{lab}"], None, 20)
    if r.code != 0:
        return EtatAgent(False, None, None)
    pid = re.search(r"\bpid = (\d+)", r.sortie)
    code = re.search(r"last exit code = ([^\n]+)", r.sortie)
    return EtatAgent(True, int(pid.group(1)) if pid else None, code.group(1).strip() if code else None)
