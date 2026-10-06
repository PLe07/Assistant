"""Réglages et emplacements de Bouclier.

- Données : `~/Library/Application Support/Bouclier/` (base SQLite en 600, réglages, caches des flux).
- Journal : `~/Library/Logs/Bouclier/` (toujours caviardé).
- iCloud : `iCloud Drive/Bouclier/` (entrée et réponses du raccourci « Arnaque ? », fiche urgence en PDF) ;
  l'app Raccourcis enregistre aussi dans son propre dossier iCloud (`iCloud Drive/Shortcuts/Bouclier/`) : on
  surveille les deux (leçon du Trieur, D-12).

Pour les tests, `BOUCLIER_MAISON` remplace le dossier personnel : rien n'est alors écrit ailleurs.
"""

from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NOM_CONFIG = "config.toml"
NOM_INFOS_URGENCE = "mes_infos_urgence.toml"

DEFAUTS: dict[str, Any] = {
    "ia": {
        "active": True,
        # Modèle économique (claude-haiku-4-5 : 1 $ / 5 $ par million de jetons, vérifié dans la doc le 2026-10-06).
        "modele": "claude-haiku-4-5",
        "prix_entree_par_million": 1.0,
        "prix_sortie_par_million": 5.0,
        "budget_mensuel_usd": 2.0,
        "seuil_bas": 20,
        "seuil_haut": 80,
        "delai_secondes": 30,
        # "auto" : la clé API (ANTHROPIC_API_KEY ou trousseau) sinon l'abonnement Claude par Claude Code.
        "moyen": "auto",
    },
    "gmail": {
        "active": True,
        "adresse": "",
        "intervalle_minutes": 5,
        "taille_max_octets": 5_000_000,
    },
    "notifications": {
        "max_par_jour": 3,
        "silence_debut": 23,
        "silence_fin": 8,
    },
    "fuites": {
        "cle_hibp": "",
    },
    "comptes": {
        "ia_domaines_inconnus": False,
    },
    "moi": {
        # Ce qui doit être retiré avant tout envoi à l'IA, dans le journal et l'historique.
        "noms": [],
        "telephones": [],
        "adresses": [],
        "emails": [],
    },
    "installation": {
        # Préfixe du LaunchAgent (com.<prefixe>.bouclier) ; vide = ton nom de session macOS.
        "prefixe_label": "",
    },
    "historique": {
        "jours": 90,
    },
}


def maison() -> Path:
    return Path(os.environ.get("BOUCLIER_MAISON") or Path.home())


@dataclass(frozen=True)
class Chemins:
    maison: Path

    @property
    def support(self) -> Path:
        return self.maison / "Library" / "Application Support" / "Bouclier"

    @property
    def logs(self) -> Path:
        return self.maison / "Library" / "Logs" / "Bouclier"

    @property
    def base(self) -> Path:
        return self.support / "bouclier.db"

    @property
    def config(self) -> Path:
        return self.support / NOM_CONFIG

    @property
    def infos_urgence(self) -> Path:
        return self.support / NOM_INFOS_URGENCE

    @property
    def caches(self) -> Path:
        return self.support / "caches"

    @property
    def sorties(self) -> Path:
        """Fiche urgence, tableau de bord : fichiers locaux, jamais envoyés sur iCloud (sauf le PDF de la fiche)."""
        return self.support / "sorties"

    @property
    def tableau_de_bord(self) -> Path:
        return self.support / "Bouclier.html"

    @property
    def icloud_drive(self) -> Path:
        return self.maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs"

    @property
    def icloud(self) -> Path:
        return self.icloud_drive / "Bouclier"

    @property
    def icloud_raccourcis(self) -> Path:
        """Le dossier iCloud de l'app Raccourcis : « iCloud Drive/Shortcuts/Bouclier »."""
        documents = self.maison / "Library" / "Mobile Documents" / "iCloud~is~workflow~my~workflows" / "Documents"
        return documents / "Bouclier"

    def entrees(self) -> list[Path]:
        return [self.icloud / "entree", self.icloud_raccourcis / "entree"]

    def dossiers_reponses(self) -> list[Path]:
        return [self.icloud / "reponses", self.icloud_raccourcis / "reponses"]

    @property
    def launch_agents(self) -> Path:
        return self.maison / "Library" / "LaunchAgents"

    @property
    def services(self) -> Path:
        return self.maison / "Library" / "Services"


def chemins() -> Chemins:
    return Chemins(maison())


def _fusion(base: dict[str, Any], ajout: dict[str, Any]) -> dict[str, Any]:
    resultat = copy.deepcopy(base)
    for cle, valeur in ajout.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = _fusion(resultat[cle], valeur)
        elif cle in resultat:
            attendu = type(resultat[cle])
            # Un réglage du mauvais type (ex. "3" au lieu de 3) est ignoré : la valeur par défaut reste.
            if isinstance(valeur, attendu) or (attendu is float and isinstance(valeur, int)):
                resultat[cle] = valeur
        else:
            resultat[cle] = valeur
    return resultat


class ConfigIllisible(Exception):
    pass


def charger(c: Chemins | None = None) -> dict[str, Any]:
    """Les réglages : valeurs par défaut + ton fichier config.toml (s'il existe et se lit)."""
    c = c or chemins()
    if not c.config.exists():
        return copy.deepcopy(DEFAUTS)
    try:
        with c.config.open("rb") as f:
            perso = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigIllisible(f"{c.config} ne se lit pas ({e}) : corrige-le ou supprime-le.") from e
    return _fusion(DEFAUTS, perso)


def charger_ou_defauts(c: Chemins | None = None) -> tuple[dict[str, Any], str | None]:
    """Comme `charger`, mais un fichier abîmé n'arrête rien : défauts + message pour doctor."""
    try:
        return charger(c), None
    except ConfigIllisible as e:
        return copy.deepcopy(DEFAUTS), str(e)


MODELE_CONFIG = """# Réglages de Bouclier. Les lignes qui commencent par # sont des explications.
# Après une modification, rien à relancer : le démon relit ce fichier à chaque tour.

[gmail]
# La boîte surveillée en lecture seule (rien n'y est jamais modifié).
adresse = ""
active = true

[ia]
# L'avis de Claude, seulement quand les règles locales hésitent. Plafond : 2 $ par mois.
active = true
budget_mensuel_usd = 2.0
modele = "claude-haiku-4-5"

[moi]
# Ce qui est retiré de tout texte envoyé à l'IA, du journal et de l'historique.
# Exemple : noms = ["Prénom Nom"]  telephones = ["06 12 34 56 78"]  adresses = ["12 rue X"]
noms = []
telephones = []
adresses = []
emails = []

[fuites]
# Facultatif et payant : une clé Have I Been Pwned permet la vérification exacte de ton adresse.
cle_hibp = ""
"""


def ecrire_modele_si_absent(c: Chemins | None = None) -> bool:
    c = c or chemins()
    if c.config.exists():
        return False
    c.support.mkdir(parents=True, exist_ok=True)
    c.config.write_text(MODELE_CONFIG, encoding="utf-8")
    os.chmod(c.config, 0o600)
    return True


def preparer_dossiers(c: Chemins | None = None) -> None:
    """Crée nos dossiers locaux (jamais ceux d'iCloud : seul l'installateur les crée, si iCloud Drive existe)."""
    c = c or chemins()
    for d in (c.support, c.logs, c.caches, c.sorties):
        d.mkdir(parents=True, exist_ok=True)
    for d in (c.support, c.caches, c.sorties):
        os.chmod(d, 0o700)
