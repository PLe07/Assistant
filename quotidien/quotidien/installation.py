"""Ce que `install.sh` et `uninstall.sh` posent sur le Mac, et rien d'autre :

- le LaunchAgent `com.<session>.quotidien` dans ~/Library/LaunchAgents ;
- la commande `~/.local/bin/quotidien` (seulement si elle est libre ou déjà à nous) ;
- les 2 raccourcis signés dans iCloud Drive/Quotidien ;
- nos dossiers (Application Support/Quotidien, Logs/Quotidien, iCloud Drive/Quotidien) et `profil.toml` s'il manque.

Chaque étape peut être relancée sans effet de bord ; un fichier du même nom qui n'est pas à Quotidien n'est jamais
touché (on s'arrête et on l'explique). La désinstallation retire l'agent et la commande ; tes listes de Rappels
seulement si tu le confirmes, et seulement celles que Quotidien a créées.
"""

from __future__ import annotations

import getpass
import os
import plistlib
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quotidien import config, icloud
from quotidien.db import Base as BaseDonnees
from quotidien.raccourcis import generer
from quotidien.systeme import Systeme

MARQUE_LANCEUR = "# lanceur de Quotidien"
PATH_DEMON = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def prefixe(reglages: dict[str, Any]) -> str:
    """Le nom de ta session macOS (comme les autres projets), ou celui choisi dans reglages.toml."""
    brut = str(reglages.get("installation", {}).get("prefixe_label") or "") or getpass.getuser()
    return re.sub(r"[^a-z0-9-]", "", brut.lower()) or "utilisateur"


def label(reglages: dict[str, Any]) -> str:
    return f"com.{prefixe(reglages)}.quotidien"


def launch_agents() -> Path:
    return config.maison() / "Library" / "LaunchAgents"


def chemin_agent(lab: str) -> Path:
    return launch_agents() / f"{lab}.plist"


def plist_agent(lab: str, python: Path, projet: Path) -> dict[str, Any]:
    logs = config.dossier_logs()
    return {
        "Label": lab,
        "ProgramArguments": [str(python), "-m", "quotidien", "demon"],
        "WorkingDirectory": str(projet),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "demon.sortie.log"),
        "StandardErrorPath": str(logs / "demon.erreurs.log"),
        "EnvironmentVariables": {
            "PATH": f"{config.maison()}/.local/bin:{PATH_DEMON}",
            "LANG": "fr_FR.UTF-8",
            "PYTHONUNBUFFERED": "1",
        },  # fmt: skip
    }


def agent_est_a_nous(chemin: Path) -> bool:
    try:
        with chemin.open("rb") as f:
            p = plistlib.load(f)
        return list(p.get("ProgramArguments", []))[1:] == ["-m", "quotidien", "demon"]
    except (OSError, plistlib.InvalidFileException, ValueError):
        return False


def lanceur() -> Path:
    return config.maison() / ".local" / "bin" / "quotidien"


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


def collisions(reglages: dict[str, Any]) -> list[str]:
    """Avant toute installation : la commande `quotidien` et le label sont-ils libres (ou déjà à nous) ?"""
    refus = []
    commande = shutil.which("quotidien")
    if commande and Path(commande) != lanceur() and not lanceur_est_a_nous(Path(commande)):
        refus.append(f"une autre commande « quotidien » existe déjà ({commande})")
    lien = lanceur()
    if lien.exists() and not lanceur_est_a_nous(lien):
        refus.append(f"{lien} existe déjà et n'est pas le lanceur de Quotidien")
    agent = chemin_agent(label(reglages))
    if agent.exists() and not agent_est_a_nous(agent):
        refus.append(f"{agent} existe déjà et n'est pas l'agent de Quotidien")
    return refus


def preparer(reglages: dict[str, Any], python: Path, projet: Path) -> Bilan:
    """Dossiers, profil, commande, LaunchAgent (sans le charger : install.sh s'en charge)."""
    b = Bilan()
    b.refus = collisions(reglages)
    if b.refus:
        return b
    for d in (config.dossier_support(), config.dossier_logs()):
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    for modele, nom in (("profil.example.toml", "profil.toml"), ("reglages.example.toml", "reglages.toml")):
        cible = config.dossier_support() / nom
        if not cible.exists() and (projet / modele).is_file():
            shutil.copyfile(projet / modele, cible)
            os.chmod(cible, 0o600)
            b.fait.append(f"réglages créés (à adapter) : {cible}")
    lien = lanceur()
    lien.parent.mkdir(parents=True, exist_ok=True)
    lien.write_text(f'#!/bin/zsh\n{MARQUE_LANCEUR} ({projet})\nexec "{python}" -m quotidien "$@"\n', encoding="utf-8")
    os.chmod(lien, 0o755)
    b.fait.append(f"commande quotidien : {lien}")
    lab = label(reglages)
    agent = chemin_agent(lab)
    agent.parent.mkdir(parents=True, exist_ok=True)
    with agent.open("wb") as f:
        plistlib.dump(plist_agent(lab, python, projet), f)
    b.fait.append(f"agent de démarrage : {agent}")
    if config.icloud_drive().is_dir():
        icloud.preparer_dossiers()
        b.fait.append(f"dossier iCloud : {config.dossier_icloud()}")
    else:
        b.avertissements.append("iCloud Drive introuvable : les raccourcis de l'iPhone ne pourront pas joindre le Mac")
    return b


def raccourcis(sorties: Path, signer: Callable[[Path, Path], tuple[bool, str]] = generer.signer) -> Bilan:
    """Les 2 raccourcis : écrits, vérifiés (`plutil -lint`), signés, déposés dans iCloud Drive/Quotidien."""
    b = Bilan()
    for fichier in generer.ecrire(sorties):
        ok, message = generer.plutil_lint(fichier)
        if not ok:
            b.refus.append(f"{fichier.name} : plist invalide ({message})")
            continue
        nom = fichier.name.replace(".non-signé", "")
        if not config.icloud_drive().is_dir():
            b.avertissements.append(f"{nom} : pas d'iCloud Drive pour le déposer")
            continue
        config.dossier_icloud().mkdir(parents=True, exist_ok=True)
        ok, message = signer(fichier, config.dossier_icloud() / nom)
        if ok:
            b.fait.append(f"raccourci signé : {config.dossier_icloud() / nom}")
        else:
            b.avertissements.append(f"{nom} non signé ({message}) : recette manuelle dans ACTIONS_HUMAINES.md")
    return b


def desinstaller(reglages: dict[str, Any], tout: bool = False) -> Bilan:
    """Retire ce que Quotidien a posé (l'agent doit déjà être arrêté par uninstall.sh). Tes données restent, sauf
    `tout` ; le dossier iCloud Drive/Quotidien reste toujours (il est dans ton iCloud : à toi de le supprimer)."""
    b = Bilan()
    agent = chemin_agent(label(reglages))
    if agent.exists() and agent_est_a_nous(agent):
        agent.unlink()
        b.fait.append(f"agent retiré : {agent}")
    lien = lanceur()
    if lien.exists() and lanceur_est_a_nous(lien):
        lien.unlink()
        b.fait.append(f"commande retirée : {lien}")
    if tout:
        for d in (config.dossier_support(), config.dossier_logs()):
            if d.is_dir() and d.name == "Quotidien":
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


# --- La vérification réelle, sur le Mac, juste après l'installation (P9) ---------------------------------------------


def _attendre_que(condition: Callable[[], bool], delai: float, attendre: Callable[[float], None],
                  horloge: Callable[[], float], pas: float = 1.0) -> float | None:  # fmt: skip
    debut = horloge()
    while True:
        if condition():
            return horloge() - debut
        if horloge() - debut >= delai:
            return None
        attendre(pas)


def verifier_reel(reglages: dict[str, Any], db: BaseDonnees, systeme: Systeme,
                  attendre: Callable[[float], None] = time.sleep, horloge: Callable[[], float] = time.time,
                  delai_relance: float = 90, delai_reponse: float = 60) -> Bilan:  # fmt: skip
    """Le démon tourne, est relancé par launchd après un `kill`, et répond à une demande de vide-frigo déposée dans
    un dossier iCloud de test (`Quotidien-TEST/`), retiré ensuite quoi qu'il arrive."""
    b = Bilan()
    lab = label(reglages)
    avant = etat_agent(systeme, lab)
    if not avant.charge or not avant.pid:
        b.refus.append(f"{lab} n'est pas lancé par launchd (dernier code : {avant.dernier_code or 'inconnu'})")
        return b
    b.fait.append(f"launchctl print : {lab} tourne (pid {avant.pid})")
    systeme.executer(["kill", "-TERM", str(avant.pid)], None, 10)
    nouveau: list[int] = []

    def relance() -> bool:
        e = etat_agent(systeme, lab)
        if e.pid and e.pid != avant.pid:
            nouveau.append(e.pid)
            return True
        return False

    duree = _attendre_que(relance, delai_relance, attendre, horloge, pas=2.0)
    if duree is None:
        b.refus.append(f"après kill {avant.pid}, launchd n'a pas relancé le démon en {int(delai_relance)} s")
        return b
    b.fait.append(f"kill {avant.pid} : relancé par launchd en {int(duree)} s (pid {nouveau[-1]})")
    _aller_retour_icloud(b, db, attendre, horloge, delai_reponse)
    return b


def _aller_retour_icloud(b: Bilan, db: BaseDonnees, attendre: Callable[[float], None], horloge: Callable[[], float],
                         delai_reponse: float) -> None:  # fmt: skip
    if not config.icloud_drive().is_dir():
        b.avertissements.append("iCloud Drive absent : aller-retour du raccourci non vérifié")
        return
    entree, reponses = config.dossier_icloud() / "entree", config.dossier_icloud() / "reponses"
    entree.mkdir(parents=True, exist_ok=True)
    nom = f"frigo-verification-{int(horloge())}"
    demande = entree / f"{nom}.txt"
    reponse = reponses / f"{nom}.txt"
    demande.write_text("2 courgettes, feta, 4 oeufs", encoding="utf-8")
    try:
        duree = _attendre_que(reponse.exists, delai_reponse, attendre, horloge)
        if duree is None:
            b.refus.append(f"vide-frigo déposé dans iCloud : pas de réponse en {int(delai_reponse)} s")
        else:
            premiere = reponse.read_text(encoding="utf-8").splitlines()[0]
            b.fait.append(f"vide-frigo déposé dans iCloud : réponse du démon en {int(duree)} s ({premiere})")
    finally:
        for f in (demande, reponse):
            f.unlink(missing_ok=True)
        with db.transaction() as cx:
            cx.execute("DELETE FROM demandes WHERE id = ?", (nom,))
        b.fait.append("fichiers de vérification retirés d'iCloud")
