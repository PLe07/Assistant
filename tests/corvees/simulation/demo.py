"""Le rapport de démonstration : un mois simulé (graine 101), analysé et décrit par le vrai moteur, sans Claude.

    python -m tests.corvees.simulation.demo        → modules/corvees/demo/rapport_demo.html

Données inventées par le simulateur : aucune donnée réelle. Les faux secrets et les applis exclues plantés par le
simulateur sont cherchés dans la page : elle n'est écrite que s'il n'y en a aucun.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from modules.corvees import config, daemon, privacy, suite
from modules.corvees.db import Base
from tests.corvees.simulation.generateur import generer

CIBLE = Path(__file__).resolve().parents[3] / "modules" / "corvees" / "demo" / "rapport_demo.html"


def produire(cible: Path = CIBLE, graine: int = 101) -> Path:
    monde = generer(graine)
    with tempfile.TemporaryDirectory() as tmp:
        reglages, _ = config.charger({"dossier": tmp, "ia": {"actif": False}, "notifications": {"vers_journal": True}})
        base = Base(Path(tmp) / "corvees.db", privacy.Gardien(reglages, privacy.sel(Path(tmp))))
        base.ajouter(monde.evenements)
        candidats = daemon.analyser_base(base, reglages, monde.fin)
        base.fermer()
        suite.traiter(reglages, candidats, monde.fin, lambda m: None, prevenir=False)
        page = (Path(tmp) / "rapport.html").read_text(encoding="utf-8")
    fuites = [s for s in monde.secrets + monde.exclus if s in page]
    if fuites:
        raise SystemExit(f"Fuite dans le rapport de démonstration : {fuites}")
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(page, encoding="utf-8")
    return cible


if __name__ == "__main__":
    chemin = produire()
    print(f"Rapport de démonstration : {chemin}")
    sys.exit(0)
