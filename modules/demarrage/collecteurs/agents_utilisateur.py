"""S1 — les LaunchAgents à toi : ~/Library/LaunchAgents/*.plist (lancés à ton ouverture de session)."""

from __future__ import annotations

from modules.demarrage.collecteurs.plists import fiches_du_dossier
from modules.demarrage.modele import Fiche
from modules.demarrage.systeme import Systeme


def dossier(systeme: Systeme) -> str:
    return f"{systeme.maison}/Library/LaunchAgents"


def collecter(systeme: Systeme) -> tuple[list[Fiche], list[str]]:
    fiches, erreur = fiches_du_dossier(systeme, dossier(systeme), "agent_utilisateur")
    return fiches, [erreur] if erreur else []
