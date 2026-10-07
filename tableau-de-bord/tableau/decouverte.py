"""La découverte : ce qui est installé sur le Mac, au démarrage puis toutes les 10 minutes (§3).

- `~/Library/LaunchAgents/*.plist`, lus avec plistlib (lecture seule) : label, programme, dossier de travail,
  journaux, KeepAlive, lancement périodique ; le dossier du projet est déduit du programme
  (`…/bouclier/.venv/bin/python` → `…/bouclier`).
- L'assistant, retrouvé par son superviseur (`com.assistant.superviseur`) ou, à défaut, par son module de tri Gmail
  (`modules/mails/tri.py`) dans `~/Assistant` ou `~/Projets/…`.
- Les conteneurs Docker (n8n), par `docker ps -a`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau.adaptateurs.base import lire_plist
from tableau.config import Chemins
from tableau.sondes.docker_n8n import SondeDocker

LABEL_SUPERVISEUR = "com.assistant.superviseur"
MARQUEUR_ASSISTANT = Path("modules") / "mails" / "tri.py"


@dataclass
class Agent:
    label: str
    plist: Path
    programme: list[str] = field(default_factory=list)
    dossier_travail: str | None = None
    sortie: str | None = None
    erreurs: str | None = None
    garde_en_vie: bool = False
    periodique: bool = False
    projet: Path | None = None


@dataclass
class Decouverte:
    agents: dict[str, Agent] = field(default_factory=dict)
    assistant: Path | None = None
    conteneurs: list[str] = field(default_factory=list)
    docker: bool | None = None
    erreurs: list[str] = field(default_factory=list)


def projet_du_programme(programme: list[str], dossier_travail: str | None) -> Path | None:
    """Le dossier du projet d'un agent : avant `.venv/`, ou le dossier du script, ou son dossier de travail."""
    for morceau in programme:
        if not morceau.startswith("/"):
            continue
        if "/.venv/" in morceau or "/venv/" in morceau:
            return Path(re.split(r"/\.?venv/", morceau, maxsplit=1)[0])
        p = Path(morceau)
        if p.suffix in (".py", ".sh") and p.parent != Path("/"):
            return _racine_de_projet(p.parent)
    if dossier_travail and dossier_travail.startswith("/"):
        return Path(dossier_travail)
    return None


def _racine_de_projet(dossier: Path) -> Path:
    """Remonte (3 niveaux au plus) jusqu'au dossier qui a un `.git` ou un `pyproject.toml`."""
    courant = dossier
    for _ in range(4):
        if (courant / ".git").exists() or (courant / "pyproject.toml").exists():
            return courant
        if courant.parent == courant:
            break
        courant = courant.parent
    return dossier


def _garde_en_vie(valeur: Any) -> bool:
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, dict):
        # {"SuccessfulExit": False} : relancé s'il plante ; c'est un programme qui doit tourner.
        return bool(valeur)
    return False


def lister_agents(chemins: Chemins) -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    dossier = chemins.launch_agents
    if not dossier.is_dir():
        return agents
    for plist in sorted(dossier.glob("*.plist")):
        d = lire_plist(plist)
        label = str(d.get("Label") or plist.stem)
        programme = [str(x) for x in d.get("ProgramArguments", []) if isinstance(x, str)]
        if not programme and isinstance(d.get("Program"), str):
            programme = [d["Program"]]
        travail = d.get("WorkingDirectory") if isinstance(d.get("WorkingDirectory"), str) else None
        agents[label] = Agent(
            label=label,
            plist=plist,
            programme=programme,
            dossier_travail=travail,
            sortie=d.get("StandardOutPath") if isinstance(d.get("StandardOutPath"), str) else None,
            erreurs=d.get("StandardErrorPath") if isinstance(d.get("StandardErrorPath"), str) else None,
            garde_en_vie=_garde_en_vie(d.get("KeepAlive")),
            periodique="StartInterval" in d or "StartCalendarInterval" in d,
            projet=projet_du_programme(programme, travail),
        )
    return agents


def trouver_assistant(chemins: Chemins, agents: dict[str, Agent]) -> Path | None:
    superviseur = agents.get(LABEL_SUPERVISEUR)
    candidats: list[Path] = []
    if superviseur is not None:
        if superviseur.dossier_travail:
            candidats.append(Path(superviseur.dossier_travail))
        if superviseur.projet is not None:
            candidats.append(superviseur.projet)
    m = chemins.maison
    candidats += [m / "Assistant", m / "Projets" / "Assistant", m / "Projets" / "assistant", m / "assistant"]
    for c in candidats:
        if (c / MARQUEUR_ASSISTANT).is_file():
            return c
    return None


def decouvrir(chemins: Chemins, docker: SondeDocker | None = None) -> Decouverte:
    d = Decouverte()
    try:
        d.agents = lister_agents(chemins)
    except OSError as e:
        d.erreurs.append(f"LaunchAgents illisibles : {e.__class__.__name__}")
    d.assistant = trouver_assistant(chemins, d.agents)
    if docker is not None:
        etat = docker.etat([])
        d.docker = etat.disponible
        if etat.disponible:
            r = docker.executer(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}"])
            for ligne in r.sortie.splitlines() if r.ok else []:
                nom, _, image = ligne.partition("\t")
                if "n8n" in nom.lower() or "n8n" in image.lower():
                    d.conteneurs.append(nom.strip())
    return d
