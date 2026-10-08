"""Le modèle commun : la fiche d'un module (registre), ce qu'on en observe, et l'état qu'on en déduit.

Tout champ qu'on n'a pas pu lire vaut `None` (« inconnu ») : un adaptateur ne plante jamais pour un format inattendu.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from enum import StrEnum
from pathlib import Path
from typing import Any


class Pastille(StrEnum):
    VERT = "vert"
    JAUNE = "jaune"
    ROUGE = "rouge"
    GRIS = "gris"


EMOJI = {Pastille.VERT: "🟢", Pastille.JAUNE: "🟡", Pastille.ROUGE: "🔴", Pastille.GRIS: "⚪"}
LIBELLE = {
    Pastille.VERT: "tout va bien",
    Pastille.JAUNE: "à regarder",
    Pastille.ROUGE: "problème",
    Pastille.GRIS: "éteint ou pas installé",
}
ORDRE = {Pastille.ROUGE: 0, Pastille.JAUNE: 1, Pastille.VERT: 2, Pastille.GRIS: 3}
PYTHON_DU_PROJET = ".venv/bin/python"  # le Python d'un projet de l'assistant, relatif à son dossier


@dataclass
class Attente:
    """« Quotidien : brief chaque jour vers 7h15 », « Bouclier : relève Gmail toutes les 5 min »…"""

    id: str
    genre: str  # quotidienne, periodique
    libelle: str
    heure: str | None = None  # HH:MM (quotidienne)
    tolerance_min: int = 20
    toutes_les_min: int | None = None  # periodique
    preuve: str = ""  # la clé que l'adaptateur remplit (vide : l'id)

    @property
    def cle_preuve(self) -> str:
        return self.preuve or self.id


@dataclass
class DefModule:
    """Une entrée du registre `modules.toml`."""

    id: str
    nom: str
    emoji: str = "🧩"
    adaptateur: str = "generique"
    labels: list[str] = field(default_factory=list)
    superviseur: str | None = None  # nom du module dans le superviseur de l'assistant
    conteneur: str | None = None  # Docker
    port: int | None = None  # n8n : son port local (5678)
    dossier_projet: str | None = None
    dossier_donnees: str | None = None
    dossier_logs: str | None = None
    logs: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    file_max_min: int | None = None  # au-delà, une entrée de file est « bloquée » (sinon le seuil général)
    perimetre_code: list[str] = field(default_factory=list)
    perimetre_exclu: list[str] = field(default_factory=list)  # sous-dossiers suivis par un autre module
    doit_tourner: bool = True
    plafond_usd: float | None = None
    commande_diagnostic: list[str] = field(default_factory=list)
    aide: str = ""  # la commande à taper toi-même, citée dans les alertes (« bouclier doctor »)
    attentes: list[Attente] = field(default_factory=list)
    attendu: bool = False  # fait partie de ton écosystème connu : absent, il est « pas installé », sans alarme
    actif: bool = True  # false : ignoré (tu l'as désactivé dans modules.toml)

    def chemin(self, brut: str | None, maison: Path, icloud: Path | None = None) -> Path | None:
        """Un chemin du registre : « ~/… », « icloud:Dossier », absolu, ou relatif au dossier du projet."""
        if not brut:
            return None
        if brut.startswith("icloud:"):
            base_icloud = icloud or maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
            return base_icloud / brut[len("icloud:") :]
        if brut.startswith("~/"):
            return maison / brut[2:]
        if brut == "~":
            return maison
        p = Path(brut)
        if not p.is_absolute() and self.dossier_projet:
            base = self.chemin(self.dossier_projet, maison)
            return base / p if base else p
        return p


@dataclass
class EtatLaunchd:
    label: str
    charge: bool
    pid: int | None = None
    dernier_code: int | None = None
    lancements: int | None = None
    etat: str | None = None  # running, waiting, not running…
    programme: str | None = None


@dataclass
class StatsProcessus:
    pids: list[int]
    cpu_pct: float | None  # en % d'un cœur, depuis la mesure précédente (None : première mesure)
    rss_mo: float
    depuis_s: float | None


@dataclass
class StatsLogs:
    erreurs_1h: int = 0
    erreurs_24h: int = 0
    avert_1h: int = 0
    avert_24h: int = 0
    derniere_erreur: str | None = None  # caviardée
    derniere_erreur_ts: float | None = None
    derniere_ligne_ts: float | None = None


@dataclass
class FileAttente:
    nom: str
    n: int
    plus_vieux_s: float
    pas_encore_telecharges: int = 0
    seuil_min: int | None = None  # au-delà, bloquée (None : le seuil général des réglages)


@dataclass
class Credits:
    mois_usd: float | None
    plafond_usd: float | None
    source: str = "base"  # base (le module tient ses comptes), estimation (jetons × tarif)
    detail: str = ""


@dataclass
class Observation:
    """Ce qu'un adaptateur a pu lire d'un module, à un instant. None = inconnu."""

    installe: bool = True
    launchd: list[EtatLaunchd] = field(default_factory=list)
    superviseur: dict[str, Any] | None = None  # statut donné par le superviseur de l'assistant
    processus: StatsProcessus | None = None
    logs: StatsLogs | None = None
    battement_ts: float | None = None
    battement_periode_s: float | None = None
    activite: tuple[str, float] | None = None  # (« dernière facture classée », instant)
    files: list[FileAttente] = field(default_factory=list)
    credits: Credits | None = None
    preuves: dict[str, float] = field(default_factory=dict)  # attente → dernier instant où c'était fait
    relances: list[float] = field(default_factory=list)  # instants des plantages vus (journal du superviseur)
    tailles: tuple[int, int] | None = None  # (données, journaux) en octets
    n8n: dict[str, Any] | None = None
    actif: bool | None = None  # False : éteint par toi dans ses réglages (pas une panne)
    raison_inactif: str = ""
    reglages_attentes: dict[str, dict[str, Any]] = field(default_factory=dict)  # heure, période, actif, lus chez lui
    inconnus: list[str] = field(default_factory=list)
    technique: dict[str, Any] = field(default_factory=dict)


@dataclass
class Probleme:
    module: str
    genre: str  # arrete, boucle, fige, attente, file, pic_erreurs, budget80, budget100, donnees, integrite, n8n, cpu
    gravite: str  # grave (🔴) ou attention (🟡)
    message: str  # la notification, calme et actionnable
    resolution: str  # le message quand c'est réglé
    sous_cle: str = ""
    nuit_permise: bool = False  # une boucle de plantages qui consomme : seule exception au silence de la nuit
    phrase: str = ""  # la phrase d'état de la carte (sinon : le message)

    @property
    def cle(self) -> str:
        return f"{self.module}:{self.genre}" + (f":{self.sous_cle}" if self.sous_cle else "")


@dataclass
class EtatModule:
    id: str
    nom: str
    emoji: str
    pastille: Pastille
    phrase: str
    derniere_activite: str | None = None
    derniere_activite_ts: float | None = None
    erreurs_24h: int | None = None
    cpu_pct: float | None = None
    rss_mo: float | None = None
    credits_mois: float | None = None
    plafond_usd: float | None = None
    projection_usd: float | None = None
    prochaine: str | None = None
    problemes: list[Probleme] = field(default_factory=list)
    attentes: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    integrite: str | None = None
    technique: dict[str, Any] = field(default_factory=dict)
    maj: float = 0.0

    def en_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["pastille"] = str(self.pastille)
        d["emoji_pastille"] = EMOJI[self.pastille]
        return d

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> EtatModule:
        """L'état relu depuis notre base (CLI, page après un redémarrage). Tolérant : un champ inconnu est ignoré."""
        connus = {f.name for f in fields(cls)}
        valeurs = {k: v for k, v in d.items() if k in connus}
        try:
            valeurs["pastille"] = Pastille(str(d.get("pastille", "gris")))
        except ValueError:
            valeurs["pastille"] = Pastille.GRIS
        champs_probleme = {f.name for f in fields(Probleme)}
        valeurs["problemes"] = [
            Probleme(**{k: v for k, v in p.items() if k in champs_probleme})
            for p in d.get("problemes") or []
            if isinstance(p, dict) and {"module", "genre", "gravite", "message", "resolution"} <= set(p)
        ]
        valeurs.setdefault("id", "?")
        valeurs.setdefault("nom", valeurs["id"])
        valeurs.setdefault("emoji", "🧩")
        valeurs.setdefault("phrase", "")
        return cls(**valeurs)
