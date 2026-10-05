"""S4 — les agents embarqués dans les apps (SMAppService) : X.app/Contents/Library/LaunchAgents, LaunchDaemons et
LoginItems, pour les apps de /Applications et ~/Applications. Un agent embarqué n'est actif que si l'app l'a
enregistré : launchd (S6) ou les éléments d'ouverture (S5) le disent.
"""

from __future__ import annotations

from modules.demarrage.collecteurs.applications import Index, lire_app
from modules.demarrage.collecteurs.plists import fiches_du_dossier
from modules.demarrage.fichiers import existe
from modules.demarrage.modele import Fiche, identifiant
from modules.demarrage.systeme import Systeme

SOUS_DOSSIERS = {"LaunchAgents": "agent_app", "LaunchDaemons": "daemon_app"}


def collecter(systeme: Systeme, index: Index) -> tuple[list[Fiche], list[str]]:
    fiches: list[Fiche] = []
    erreurs: list[str] = []
    for app in index.apps:
        if app.chemin.startswith("/System/"):
            continue
        for sous, source in SOUS_DOSSIERS.items():
            trouvees, erreur = fiches_du_dossier(systeme, f"{app.chemin}/Contents/Library/{sous}", source)
            for f in trouvees:
                f.app_parente = app.chemin
            fiches += trouvees
            if erreur:
                erreurs.append(erreur)
        dossier = systeme.chemin(f"{app.chemin}/Contents/Library/LoginItems")
        try:
            aides = sorted(e.name for e in dossier.iterdir() if e.name.endswith(".app"))
        except OSError:
            aides = []
        for nom in aides:
            aide = lire_app(systeme, f"{app.chemin}/Contents/Library/LoginItems/{nom}")
            label = aide.bundle_id or nom.removesuffix(".app")
            fiches.append(
                Fiche(
                    id=identifiant("ouverture_app", label),
                    label=label,
                    source="ouverture_app",
                    nom=aide.nom,
                    programme=aide.executable or aide.chemin,
                    programme_existe=existe(systeme, aide.executable or aide.chemin),
                    app_parente=app.chemin,
                    details={"app_aide": aide.chemin},
                )
            )
    return fiches, erreurs
