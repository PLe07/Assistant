"""Outils communs : des réglages isolés dans un dossier temporaire, un faux Mac, les fixtures de format."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.demarrage import config
from tests.demarrage.faux_mac.systeme_faux import FauxMac

FORMATS = Path(__file__).parent / "fixtures" / "formats"
REELLES = Path(__file__).parent / "fixtures" / "reelles"


def fixture(nom: str) -> str:
    return (FORMATS / nom).read_text(encoding="utf-8")


@pytest.fixture
def reglages(tmp_path):
    r, erreurs = config.charger({"dossier": str(tmp_path / "donnees")})
    assert erreurs == []
    return r


@pytest.fixture
def mac(tmp_path):
    return FauxMac(tmp_path / "mac")
