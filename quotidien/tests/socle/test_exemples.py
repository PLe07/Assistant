"""Les fichiers d'exemple se lisent sans aucun avertissement (ce que l'installation copie doit être juste)."""

from __future__ import annotations

import shutil
from pathlib import Path

from quotidien import config
from quotidien.anniversaires import proches


def test_exemples_valides(maison: Path) -> None:
    racine = config.racine_projet()
    config.dossier_support().mkdir(parents=True)
    shutil.copyfile(racine / "profil.example.toml", config.dossier_support() / "profil.toml")
    shutil.copyfile(racine / "reglages.example.toml", config.dossier_support() / "reglages.toml")
    r = config.charger()
    assert r.avertissements == []
    assert r.profil == config.defauts().profil and r.reglages == config.defauts().reglages
    lecture = proches.lire_fiches(racine / "proches.example.toml")
    assert lecture.avertissements == [] and [p.prenom for p in lecture.personnes] == ["Camille"]
