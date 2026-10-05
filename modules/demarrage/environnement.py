"""Reconnaissance : sur quelle machine tourne-t-on, et quelles commandes sont là ?

Chaque collecteur dépend d'une ou deux commandes. Celles qui manquent rendent un collecteur « dégradé », jamais un
plantage : `demarrage doctor` le dit en clair.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field

from modules.demarrage.systeme import Systeme

# commande → à quoi elle sert (dans le doctor et dans le rapport)
COMMANDES: dict[str, str] = {
    "launchctl": "programmes chargés, désactivés, relances (S6) ; désactiver et restaurer",
    "ps": "processeur et mémoire de chaque programme",
    "top": "impact énergétique",
    "pmset": "qui empêche la mise en veille",
    "codesign": "l'éditeur et la signature de chaque programme",
    "mdls": "la dernière fois que tu as ouvert une app",
    "sfltool": "les éléments d'ouverture (S5, souvent réservé à l'administrateur)",
    "osascript": "les éléments d'ouverture (S5, secours), les notifications",
    "systemextensionsctl": "les extensions système (S7)",
    "crontab": "les tâches planifiées cron (S9)",
    "sysctl": "l'heure du démarrage",
    "last": "l'heure de l'ouverture de session",
    "log": "l'heure de l'ouverture de session (secours)",
    "zsh": "le temps d'ouverture d'un Terminal",
}


@dataclass
class Environnement:
    architecture: str
    macos: str
    python: str
    commandes: dict[str, bool] = field(default_factory=dict)

    @property
    def manquantes(self) -> list[str]:
        return [nom for nom, la in self.commandes.items() if not la]


def reconnaitre(systeme: Systeme) -> Environnement:
    arch = systeme.executer(["uname", "-m"], delai=5)
    vers = systeme.executer(["sw_vers", "-productVersion"], delai=5)
    return Environnement(
        architecture=arch.sortie.strip() if arch.ok else "inconnue",
        macos=vers.sortie.strip() if vers.ok and vers.sortie.strip() else "inconnu (pas un Mac ?)",
        python=platform.python_version(),
        commandes={nom: systeme.a_la_commande(nom) for nom in COMMANDES},
    )
