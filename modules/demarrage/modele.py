"""La fiche d'un élément qui se lance tout seul, et l'inventaire complet d'un scan."""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Any

# source → (code du §3, où on le trouve, en clair)
SOURCES: dict[str, tuple[str, str]] = {
    "agent_utilisateur": ("S1", "~/Library/LaunchAgents (à toi)"),
    "agent_global": ("S2", "/Library/LaunchAgents (pour tous les comptes)"),
    "daemon_global": ("S2", "/Library/LaunchDaemons (système, administrateur)"),
    "apple": ("S3", "/System/Library (macOS)"),
    "agent_app": ("S4", "dans une app (Contents/Library/LaunchAgents)"),
    "daemon_app": ("S4", "dans une app (Contents/Library/LaunchDaemons)"),
    "ouverture_app": ("S4", "dans une app (Contents/Library/LoginItems)"),
    "ouverture": ("S5", "Ouverture à la connexion (Réglages Système)"),
    "launchd": ("S6", "chargé par launchd, sans fichier connu"),
    "extension": ("S7", "extension système"),
    "assistant_privilegie": ("S8", "/Library/PrivilegedHelperTools (administrateur)"),
    "cron": ("S9", "tâche cron"),
}
# Ces sources ne se gèrent qu'en administrateur : le Nettoyeur n'y donne que des instructions.
SOURCES_GLOBALES = {"agent_global", "daemon_global", "daemon_app", "extension", "assistant_privilegie"}


def identifiant(source: str, label: str, discriminant: str = "") -> str:
    """Stable d'un scan à l'autre : la même source et le même libellé donnent le même identifiant."""
    brut = f"{source}\x00{label}" + (f"\x00{discriminant}" if discriminant else "")
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()[:8]


@dataclass
class Declencheurs:
    au_chargement: bool = False  # RunAtLoad : à l'ouverture de session (ou au démarrage pour un daemon)
    garder_en_vie: bool = False  # KeepAlive vrai (ou conditionnel) : relancé s'il s'arrête
    garder_conditions: list[str] = field(default_factory=list)  # KeepAlive en dictionnaire
    intervalle_s: int | None = None  # StartInterval
    calendrier: list[dict[str, int]] = field(default_factory=list)  # StartCalendarInterval
    chemins_surveilles: list[str] = field(default_factory=list)  # WatchPaths + QueueDirectories
    au_montage: bool = False  # StartOnMount

    def resume(self) -> str:
        morceaux = []
        if self.au_chargement:
            morceaux.append("à l'ouverture de session")
        if self.garder_en_vie:
            morceaux.append("relancé s'il s'arrête" + (" (sous conditions)" if self.garder_conditions else ""))
        if self.intervalle_s:
            morceaux.append(f"toutes les {_duree(self.intervalle_s)}")
        if self.calendrier:
            morceaux.append(f"{len(self.calendrier)} horaire(s) fixe(s)")
        if self.chemins_surveilles:
            morceaux.append(f"quand {len(self.chemins_surveilles)} dossier(s) changent")
        if self.au_montage:
            morceaux.append("quand un disque est branché")
        return ", ".join(morceaux) or "à la demande"


def _duree(s: int) -> str:
    if s % 86400 == 0:
        return f"{s // 86400} j"
    if s % 3600 == 0:
        return f"{s // 3600} h"
    if s % 60 == 0:
        return f"{s // 60} min"
    return f"{s} s"


@dataclass
class Fiche:
    id: str
    label: str
    source: str
    nom: str = ""  # nom lisible (base de connaissances, sinon déduit)
    chemin_plist: str | None = None
    programme: str | None = None  # le programme réellement lancé (le script, pas l'interpréteur)
    arguments: list[str] = field(default_factory=list)
    interprete: str | None = None  # /bin/sh, python3… quand programme est un script
    programme_existe: bool | None = None
    app_parente: str | None = None  # l'app (.app) à laquelle il appartient
    bundles_associes: list[str] = field(default_factory=list)  # AssociatedBundleIdentifiers
    app_attendue_absente: bool = False  # il dit appartenir à une app qui n'est plus là
    editeur: str | None = None
    equipe: str | None = None  # TeamIdentifier
    signature: str = "inconnue"  # apple, developpeur, app_store, adhoc, non_signe, invalide, introuvable, inconnue
    est_apple: bool = False
    declencheurs: Declencheurs = field(default_factory=Declencheurs)
    charge: bool | None = None  # chargé dans launchd en ce moment
    desactive: bool | None = None  # désactivé (launchctl disable, clé Disabled, ou Réglages)
    actif: bool | None = None  # se lancera-t-il au prochain démarrage ?
    pids: list[int] = field(default_factory=list)
    derniere_utilisation_app: float | None = None  # mdls kMDItemLastUsedDate de l'app parente
    c_est_moi: bool = False  # l'Assistant lui-même
    doublon: bool = False
    erreurs: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)  # relances, dernier code, équipe BTM…

    def vers_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> Fiche:
        connus = {f.name for f in dataclasses.fields(cls)}
        valeurs = {k: v for k, v in d.items() if k in connus}
        valeurs["declencheurs"] = Declencheurs(**d.get("declencheurs", {}))
        return cls(**valeurs)


@dataclass
class Collecteur:
    nom: str  # S1…S10
    etat: str  # ok, dégradé, indisponible
    detail: str = ""
    nombre: int = 0


@dataclass
class Inventaire:
    ts: float
    fiches: list[Fiche] = field(default_factory=list)
    collecteurs: list[Collecteur] = field(default_factory=list)

    def fiche(self, id_: str) -> Fiche | None:
        return next((f for f in self.fiches if f.id == id_), None)

    def par_label(self, label: str) -> list[Fiche]:
        return [f for f in self.fiches if f.label == label]

    def vers_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "fiches": [f.vers_dict() for f in self.fiches],
            "collecteurs": [dataclasses.asdict(c) for c in self.collecteurs],
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> Inventaire:
        return cls(
            ts=float(d["ts"]),
            fiches=[Fiche.depuis_dict(f) for f in d.get("fiches", [])],
            collecteurs=[Collecteur(**c) for c in d.get("collecteurs", [])],
        )
