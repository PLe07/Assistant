"""Le rapport de démonstration (modules/demarrage/demo/rapport_demo.html), fait sur le faux Mac n° 1 :
    python -m tests.demarrage.faux_mac.demo
Les sessions des jours précédents sont inventées pour montrer la courbe ; tout le reste vient du faux Mac."""

from __future__ import annotations

import tempfile
from pathlib import Path

from modules.demarrage import config, rapport
from modules.demarrage.analyse import analyser
from modules.demarrage.db import Base
from tests.demarrage.faux_mac.construire import construire
from tests.demarrage.faux_mac.juge import diagnostiquer

SORTIE = Path(__file__).resolve().parents[3] / "modules" / "demarrage" / "demo" / "rapport_demo.html"


def fabriquer(dossier: Path, sortie: Path = SORTIE) -> Path:
    reglages, _ = config.charger({"dossier": str(dossier / "donnees")})
    faux = construire(dossier / "mac")
    diagnostiquer(faux, dossier, reglages)
    base = Base(dossier / "demarrage.db")
    try:
        anciennes = [
            (9, 74.0, 268.0),
            (8, 61.0, None),
            (7, 58.0, 251.0),
            (6, 66.0, 233.0),
            (5, 55.0, 160.0),
            (4, 57.0, 141.0),
            (3, 52.0, 118.0),
        ]
        for jours, demarrage, calme in anciennes:
            boot = faux.boot - jours * 86400
            base.enregistrer_session(
                boot,
                boot + demarrage,
                None if calme is None else boot + demarrage + calme,
                {"demarrage_s": demarrage, "calme_s": calme},
            )
        base.enregistrer_zsh(
            faux.mac.maintenant(),
            412.0,
            {
                "essais_ms": [398.0, 405.0, 412.0, 430.0, 455.0],
                "causes": [
                    {"fonction": "nvm_auto", "cause": "nvm (Node.js)", "ms": 245.1, "part": 60.2},
                    {"fonction": "compinit", "cause": "compinit (complétion)", "ms": 70.0, "part": 17.2},
                ],
            },
        )
        inventaire = base.dernier_scan()
        assert inventaire is not None
        inventaire.shell = {
            "fichiers": {".zshrc": 42},
            "suspects": [
                {"fichier": "~/.zshrc", "ligne": 12, "cause": "nvm (Node.js)", "conseil": "charger nvm à la demande"}
            ],
        }
        bilan = analyser(inventaire, base, reglages, faux.mac.maintenant())
        html = rapport.construire(bilan, reglages, base.sessions(), base.zsh(), 501)
    finally:
        base.fermer()
    return rapport.ecrire(sortie, html)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        print(fabriquer(Path(d)))
