from pathlib import Path

import pytest

from modules.trieur import config


def test_defauts_et_fusion():
    r, erreurs = config.charger({"classement": {"seuil_ia": 0.8}, "inconnu": 1, "paralleles": "deux"})
    assert r["classement"]["seuil_ia"] == 0.8 and r["classement"]["nom_max"] == 120
    assert r["paralleles"] == 2 and len(erreurs) == 2
    assert r["arborescence"]["facture_achat"] == "Factures/{annee}" and r["ia"]["budget_mensuel_usd"] == 1.0


def test_chemins_et_bac_a_sable(tmp_path, monkeypatch):
    r = config.pour_le_bac_a_sable(tmp_path)
    assert config.chemin(r, "boite") == tmp_path / "iCloud" / "BoiteMac"
    assert config.chemin(r, "classes") == tmp_path / "Documents" / "Classés"
    assert config.dossier_donnees(r) == tmp_path / "donnees" and r["mode_test"]
    defauts, _ = config.charger({})
    assert config.chemin(defauts, "boite") == Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/BoiteMac"
    monkeypatch.setenv("TRIEUR_DOSSIER", str(tmp_path / "ailleurs"))
    assert config.dossier_donnees(defauts) == tmp_path / "ailleurs"
    with pytest.raises(ValueError):
        config.pour_le_bac_a_sable(tmp_path, {"seuil": 1})


def test_cli_aide(capsys):
    from modules.trieur.cli import main

    assert main([]) == 0 and "trieur ajouter" in capsys.readouterr().out


def test_boucle_s_arrete_sur_demande():
    import threading

    from modules.trieur import module

    class Ctx:
        arret = threading.Event()

        def attendre(self, s):
            return True

    module.boucle(Ctx())
