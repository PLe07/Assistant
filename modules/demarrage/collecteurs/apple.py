"""S3 — les éléments de macOS : /System/Library/LaunchAgents et LaunchDaemons. Comptés, étiquetés 🍎, jamais
d'action. Le volume système est scellé et signé par Apple : pas besoin d'appeler codesign pour eux.
"""

from __future__ import annotations

from modules.demarrage.collecteurs.plists import fiches_du_dossier
from modules.demarrage.modele import Fiche
from modules.demarrage.systeme import Systeme

DOSSIERS = {"/System/Library/LaunchAgents": "gui", "/System/Library/LaunchDaemons": "system"}


def collecter(systeme: Systeme) -> tuple[list[Fiche], list[str]]:
    fiches: list[Fiche] = []
    erreurs: list[str] = []
    for dossier, domaine in DOSSIERS.items():
        trouvees, erreur = fiches_du_dossier(systeme, dossier, "apple")
        for f in trouvees:
            f.est_apple, f.signature, f.editeur = True, "apple", "Apple"
            f.details["domaine"] = domaine
        fiches += trouvees
        if erreur:
            erreurs.append(erreur)
    return fiches, erreurs
