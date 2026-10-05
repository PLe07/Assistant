"""Le programme d'analyse à part, appelé directement (le démon le lance avec python -m modules.corvees.analyse)."""

import io
import json

from modules.corvees import analyse, config, daemon
from modules.corvees.db import Evenement
from tests.corvees.unitaires.test_daemon import ts


def test_analyse_a_part(tmp_path, monkeypatch):
    reglages, _ = config.charger(
        {"dossier": str(tmp_path / "d"), "ia": {"actif": False}, "notifications": {"vers_journal": True}}
    )
    base = daemon.ouvrir(reglages)
    for jour in range(1, 6):
        base.ajouter(
            [
                Evenement(
                    ts(jour, 15),
                    "fichiers",
                    "fmove",
                    "fmove:Downloads→Documents/Factures [pdf, Facture_*]",
                    {"fichier": f"f{jour}"},
                    jour,
                )
            ]
        )
    base.fermer()
    sortie = io.StringIO()
    assert analyse.principal([repr(ts(5, 21))], io.StringIO(json.dumps(reglages)), sortie) == 0
    assert "1 corvées repérées" in sortie.getvalue()
    base = daemon.ouvrir(reglages)
    assert len(base.candidats()) == 1
    base.fermer()


def test_sans_reglages_sur_l_entree_ceux_de_l_assistant(tmp_path, monkeypatch):
    monkeypatch.setenv("CORVEES_DOSSIER", str(tmp_path / "d"))
    from unittest import mock

    with mock.patch(
        "core.config.charger",
        return_value={"modules": {"corvees": {"ia": {"actif": False}, "notifications": {"vers_journal": True}}}},
    ):
        sortie = io.StringIO()
        assert analyse.principal([repr(ts(5, 21))], io.StringIO(""), sortie) == 0
    assert "0 corvées repérées" in sortie.getvalue()
