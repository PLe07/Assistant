"""Ce que `install.sh` et `uninstall.sh` posent sur le Mac, et rien d'autre (§7) :

- le LaunchAgent `com.<toi>.tableau` dans ~/Library/LaunchAgents (RunAtLoad, KeepAlive, ThrottleInterval, Nice) ;
- la commande `~/.local/bin/tableau` (seulement si elle est libre ou déjà à nous) ;
- nos dossiers : Application Support/TableauDeBord, Logs/TableauDeBord, et `iCloud Drive/Tableau/Etat.html`.

Chaque étape peut être relancée sans effet de bord ; un fichier du même nom qui n'est pas au tableau de bord n'est
jamais touché (on s'arrête et on l'explique). La désinstallation retire tout cela, et seulement cela : aucun autre
module, aucun autre agent.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau import config, registre
from tableau.decouverte import decouvrir
from tableau.instantane_icloud import NOM as NOM_INSTANTANE

MARQUE_LANCEUR = "# lanceur du tableau de bord"
PATH_DEMON = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


@dataclass
class Bilan:
    fait: list[str] = field(default_factory=list)
    refus: list[str] = field(default_factory=list)  # ce qui n'est pas à nous : on n'y touche pas
    avertissements: list[str] = field(default_factory=list)

    def texte(self) -> str:
        lignes = [f"  ✅ {x}" for x in self.fait]
        lignes += [f"  ⚠️ {x}" for x in self.avertissements]
        lignes += [f"  ❌ {x}" for x in self.refus]
        return "\n".join(lignes)


def chemin_agent(c: config.Chemins, label: str) -> Path:
    return c.launch_agents / f"{label}.plist"


def plist_agent(label: str, python: Path, projet: Path, c: config.Chemins) -> dict[str, Any]:
    return {
        "Label": label,
        "ProgramArguments": [str(python), "-m", "tableau", "demon"],
        "WorkingDirectory": str(projet),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "Nice": 10,
        "LowPriorityIO": True,
        "ProcessType": "Background",
        "LimitLoadToSessionType": "Aqua",  # l'icône de la barre des menus a besoin de ta session graphique
        "StandardOutPath": str(c.logs / "demon.sortie.log"),
        "StandardErrorPath": str(c.logs / "demon.erreurs.log"),
        "EnvironmentVariables": {
            "PATH": f"{c.maison}/.local/bin:{PATH_DEMON}",
            "LANG": "fr_FR.UTF-8",
            "PYTHONUNBUFFERED": "1",
        },
    }


def agent_est_a_nous(chemin: Path) -> bool:
    try:
        with chemin.open("rb") as f:
            p = plistlib.load(f)
        return list(p.get("ProgramArguments", []))[1:] == ["-m", "tableau", "demon"]
    except (OSError, plistlib.InvalidFileException, ValueError):
        return False


def lanceur(c: config.Chemins) -> Path:
    return c.maison / ".local" / "bin" / "tableau"


def lanceur_est_a_nous(chemin: Path) -> bool:
    try:
        return MARQUE_LANCEUR in chemin.read_text(encoding="utf-8", errors="replace")[:500]
    except OSError:
        return False


def collisions(c: config.Chemins, label: str) -> list[str]:
    refus = []
    commande = shutil.which("tableau")
    if commande and Path(commande) != lanceur(c) and not lanceur_est_a_nous(Path(commande)):
        refus.append(f"une autre commande « tableau » existe déjà ({commande})")
    lien = lanceur(c)
    if lien.exists() and not lanceur_est_a_nous(lien):
        refus.append(f"{lien} existe déjà et n'est pas le lanceur du tableau de bord")
    agent = chemin_agent(c, label)
    if agent.exists() and not agent_est_a_nous(agent):
        refus.append(f"{agent} existe déjà et n'est pas l'agent du tableau de bord")
    return refus


def preparer(c: config.Chemins, reglages: config.Reglages, python: Path, projet: Path) -> Bilan:
    """Dossiers, jeton, registre, commande, LaunchAgent (sans le charger : install.sh s'en charge)."""
    b = Bilan()
    label = reglages.label()
    b.refus = collisions(c, label)
    if b.refus:
        return b
    c.preparer()
    config.jeton(c)
    b.fait.append(f"dossiers et jeton : {c.support}".replace(str(c.maison), "~", 1))
    if not c.registre.exists():
        modules, _, erreurs = registre.synchroniser(c.registre, reglages.prefixe(), decouvrir(c), c.maison)
        b.fait.append(f"registre créé ({len(modules)} modules) : tu peux l'ajuster, il est à toi")
        b.avertissements += erreurs
    else:
        b.fait.append("registre déjà présent : gardé tel quel")
    lien = lanceur(c)
    lien.parent.mkdir(parents=True, exist_ok=True)
    lien.write_text(f'#!/bin/zsh\n{MARQUE_LANCEUR} ({projet})\nexec "{python}" -m tableau "$@"\n', encoding="utf-8")
    os.chmod(lien, 0o755)
    b.fait.append(f"commande tableau : {lien}".replace(str(c.maison), "~", 1))
    agent = chemin_agent(c, label)
    agent.parent.mkdir(parents=True, exist_ok=True)
    with agent.open("wb") as f:
        plistlib.dump(plist_agent(label, python, projet, c), f)
    b.fait.append(f"agent de démarrage : {agent}".replace(str(c.maison), "~", 1))
    if not c.icloud_drive.is_dir():
        b.avertissements.append("iCloud Drive introuvable : pas d'instantané pour l'iPhone (le reste marche)")
    return b


def verifier(
    c: config.Chemins,
    attendre: Callable[[float], None] = time.sleep,
    horloge: Callable[[], float] = time.time,
    delai_s: float = 150,
) -> Bilan:
    """Le démon a fait un tour récent et la page locale répond (avec le jeton, et refuse sans)."""
    from tableau.db import Base

    b = Bilan()
    fin = horloge() + delai_s
    battement = None
    base = Base(c.base)
    try:
        while horloge() < fin:
            brut = base.lire_meta("battement_demon")
            if brut is not None and horloge() - float(brut) < 180:
                battement = float(brut)
                break
            attendre(3)
        if battement is None:
            b.refus.append("le démon n'a pas fait de tour (journal : ~/Library/Logs/TableauDeBord/)")
            return b
        b.fait.append("le démon fait ses tours")
        port = int(base.lire_meta("port") or 0)
    finally:
        base.fermer()
    jeton = config.jeton(c)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/?t={jeton}", timeout=10) as r:
            ok = r.status == 200 and b"Tableau de bord" in r.read()
    except OSError:
        ok = False
    if not ok:
        b.refus.append(f"la page locale ne répond pas sur 127.0.0.1:{port}")
        return b
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10)
        b.refus.append("la page répond sans jeton : anormal")
    except OSError:
        b.fait.append(f"page locale sur 127.0.0.1:{port}, refusée sans jeton")
    return b


def desinstaller(c: config.Chemins, reglages: config.Reglages) -> Bilan:
    """Retire ce que le tableau de bord a posé (l'agent doit déjà être arrêté par uninstall.sh)."""
    b = Bilan()
    agent = chemin_agent(c, reglages.label())
    if agent.exists():
        if agent_est_a_nous(agent):
            agent.unlink()
            b.fait.append(f"agent retiré : {agent.name}")
        else:
            b.refus.append(f"{agent} n'est pas l'agent du tableau de bord : laissé")
    lien = lanceur(c)
    if lien.exists():
        if lanceur_est_a_nous(lien):
            lien.unlink()
            b.fait.append("commande tableau retirée")
        else:
            b.refus.append(f"{lien} n'est pas à nous : laissé")
    for dossier, quoi in ((c.support, "données"), (c.logs, "journaux")):
        if dossier.exists():
            shutil.rmtree(dossier)
            b.fait.append(f"{quoi} retirées : {dossier}".replace(str(c.maison), "~", 1))
    instantane = c.icloud / NOM_INSTANTANE
    if instantane.exists():
        instantane.unlink()
        b.fait.append("instantané iPhone retiré")
    if c.icloud.is_dir() and not any(c.icloud.iterdir()):
        c.icloud.rmdir()
        b.fait.append("dossier iCloud Drive/Tableau retiré (il était vide)")
    return b
