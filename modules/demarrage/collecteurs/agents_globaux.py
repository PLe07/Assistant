"""S2 — les LaunchAgents et LaunchDaemons globaux : /Library/LaunchAgents et /Library/LaunchDaemons.

Lecture seule : les modifier exige les droits d'administrateur, le Nettoyeur n'y donne que des instructions.
"""

from __future__ import annotations

from modules.demarrage.collecteurs.plists import fiches_du_dossier
from modules.demarrage.modele import Fiche
from modules.demarrage.systeme import Systeme

DOSSIERS = {"/Library/LaunchAgents": "agent_global", "/Library/LaunchDaemons": "daemon_global"}


def collecter(systeme: Systeme) -> tuple[list[Fiche], list[str]]:
    fiches: list[Fiche] = []
    erreurs: list[str] = []
    for dossier, source in DOSSIERS.items():
        trouvees, erreur = fiches_du_dossier(systeme, dossier, source)
        fiches += trouvees
        if erreur:
            erreurs.append(erreur)
    return fiches, erreurs
