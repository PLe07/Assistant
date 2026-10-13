"""Ce que partagent les actions : la réponse rendue, les outils (exécuteur, pont, chemins), l'état de la conversation.

Une action reçoit une compréhension (intention de la liste blanche + paramètres validés) et rend une `Reponse` :
le texte de la bulle (« ✓ Notion ouvert »), un statut, et ce qu'il faut pour « annule ».
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from voix.actions.executeur import Executeur, ProgrammeRefuse, Resultat
from voix.actions.pont import OrdreRefuse, Pont, PontAbsent, ReponsePont
from voix.config import Chemins, Reglages
from voix.nlu.alias import Commandes
from voix.nlu.catalogue import Catalogue


@dataclass
class Reponse:
    statut: str  # fait, info, erreur, refus, question, choix, rien
    texte: str
    intention: str | None = None
    donnees: dict[str, Any] = field(default_factory=dict)


def fait(texte: str, intention: str | None = None, **donnees: Any) -> Reponse:
    return Reponse("fait", f"✓ {texte}", intention, dict(donnees))


def info(texte: str, intention: str | None = None, **donnees: Any) -> Reponse:
    return Reponse("info", texte, intention, dict(donnees))


def erreur(texte: str, intention: str | None = None) -> Reponse:
    return Reponse("erreur", texte, intention)


@dataclass(frozen=True)
class Annulation:
    """De quoi défaire la dernière action réversible : son genre et l'état d'avant."""

    genre: str  # volume, apparence, wifi, concentration
    avant: dict[str, Any]
    libelle: str


@dataclass
class Etat:
    """La conversation en cours (en mémoire) : résultats Spotlight numérotés, annulations, dernière réponse."""

    resultats: list[str] = field(default_factory=list)
    annulations: list[Annulation] = field(default_factory=list)
    derniere: Reponse | None = None
    parler: bool = False

    def retenir(self, a: Annulation) -> None:
        self.annulations.append(a)
        del self.annulations[:-20]


@dataclass
class Outils:
    executeur: Executeur
    chemins: Chemins
    reglages: Reglages
    catalogue: Catalogue
    commandes: Commandes = field(default_factory=Commandes)
    pont: Pont = field(default_factory=PontAbsent)
    maintenant: Callable[[], datetime] = datetime.now
    modules: dict[str, str] = field(default_factory=dict)  # nom → chemin trouvé par which
    modes_ambiance: dict[str, str] = field(default_factory=dict)

    def lancer(self, programme: str, *arguments: str, delai_s: float | None = None) -> Resultat:
        try:
            return self.executeur.lancer(programme, list(arguments), delai_s)
        except ProgrammeRefuse as e:
            return Resultat(126, erreur=str(e))

    def demander(self, ordre: str, **params: Any) -> ReponsePont:
        try:
            return self.pont.demander(ordre, {k: v for k, v in params.items() if v is not None})
        except OrdreRefuse as e:
            return ReponsePont(False, {}, str(e))


# --- chemins et adresses : ce qu'on accepte d'ouvrir ----------------------------------------------------------------

# Des fichiers qui s'exécutent quand on les ouvre : jamais ouverts par la voix (un alias ou un résultat Spotlight
# qui pointerait vers un script ne lance rien).
EXTENSIONS_EXECUTABLES = {
    ".command", ".sh", ".bash", ".zsh", ".tool", ".scpt", ".scptd", ".applescript", ".workflow", ".terminal",
    ".jar", ".pkg", ".mpkg", ".dmg", ".py", ".pl", ".rb", ".js", ".jxa", ".action", ".inetloc", ".webloc",
    ".fileloc", ".shortcut", ".prefpane", ".kext", ".plugin", ".osax", ".service", ".mobileconfig",
}  # fmt: skip
CARACTERES_INTERDITS = re.compile(r"[\x00-\x1f\x7f]")


class CheminRefuse(ValueError):
    pass


def chemin_ouvrable(brut: str, maison: Path, dossier: bool | None = None, apps: bool = False) -> str:
    """Un chemin qu'on peut passer à `open` : absolu, existant, dans ta maison (ou une app de /Applications si
    `apps`), jamais un fichier qui s'exécute. `dossier` : True exige un dossier, False un fichier."""
    if not brut or CARACTERES_INTERDITS.search(brut) or brut.startswith("-"):
        raise CheminRefuse("chemin invalide")
    p = Path(brut)
    if not p.is_absolute():
        raise CheminRefuse("chemin relatif")
    try:
        reel = p.resolve(strict=True)
        maison_reelle = maison.resolve()
    except (OSError, RuntimeError) as e:
        raise CheminRefuse("introuvable") from e
    dans_maison = reel == maison_reelle or maison_reelle in reel.parents
    est_app = reel.suffix == ".app" and reel.is_dir()
    racines_apps = (Path("/Applications"), Path("/System/Applications"), maison_reelle / "Applications")
    if apps and est_app and any(r == reel.parent or r in reel.parents for r in racines_apps):
        return str(reel)
    if not dans_maison:
        raise CheminRefuse("hors de ta maison")
    if reel.is_dir():
        if dossier is False or est_app:
            raise CheminRefuse("c'est un dossier")
        return str(reel)
    if dossier is True:
        raise CheminRefuse("ce n'est pas un dossier")
    if reel.suffix.lower() in EXTENSIONS_EXECUTABLES:
        raise CheminRefuse("un fichier qui s'exécute n'est jamais ouvert par la voix")
    try:
        mode = reel.stat().st_mode
    except OSError as e:
        raise CheminRefuse("illisible") from e
    if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        raise CheminRefuse("un fichier exécutable n'est jamais ouvert par la voix")
    if not os.access(reel, os.R_OK):
        raise CheminRefuse("illisible")
    return str(reel)


ADRESSE = re.compile(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?(?:/[^\s\"'<>`\\]*)?")


def adresse_ouvrable(url: str) -> str:
    if len(url) > 2000 or not ADRESSE.fullmatch(url):
        raise CheminRefuse("adresse refusée (https seulement)")
    return url
