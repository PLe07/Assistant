"""S8 — les assistants privilégiés : /Library/PrivilegedHelperTools (installés par une app, lancés en root par un
LaunchDaemon). Sans LaunchDaemon qui le lance, un assistant ne démarre plus : c'est souvent un reste d'app
désinstallée. Lecture seule : les retirer exige les droits d'administrateur.
"""

from __future__ import annotations

from modules.demarrage.modele import Fiche, identifiant
from modules.demarrage.systeme import Systeme

DOSSIER = "/Library/PrivilegedHelperTools"


def collecter(systeme: Systeme, fiches: list[Fiche]) -> tuple[list[Fiche], list[str]]:
    try:
        noms = sorted(e.name for e in systeme.chemin(DOSSIER).iterdir() if not e.name.startswith("."))
    except FileNotFoundError:
        return [], []
    except OSError as e:
        return [], [f"{DOSSIER} illisible ({e.strerror or e})"]
    lanceurs = {f.programme: f for f in fiches if f.programme and f.source in ("daemon_global", "daemon_app")}
    trouvees: list[Fiche] = []
    for nom in noms:
        chemin = f"{DOSSIER}/{nom}"
        lanceur = lanceurs.get(chemin)
        f = Fiche(
            id=identifiant("assistant_privilegie", nom),
            label=nom,
            source="assistant_privilegie",
            programme=chemin,
            programme_existe=True,
            actif=lanceur.actif if lanceur else False,
        )
        if lanceur:
            f.details["lance_par"] = lanceur.label
            f.charge, f.pids = lanceur.charge, list(lanceur.pids)
        else:
            f.details["sans_plist"] = True
        trouvees.append(f)
    return trouvees, []
