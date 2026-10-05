"""Outils communs : des réglages, un gardien et une base isolés dans un dossier temporaire."""

from __future__ import annotations

import pytest

from modules.corvees import config, privacy
from modules.corvees.db import Base


@pytest.fixture
def reglages(tmp_path):
    r, erreurs = config.charger({"dossier": str(tmp_path / "donnees")})
    assert erreurs == []
    return r


@pytest.fixture
def gardien(reglages):
    return privacy.Gardien(reglages, b"sel-de-test-32-octets-exactement")


@pytest.fixture
def base(tmp_path, gardien):
    b = Base(tmp_path / "donnees" / "corvees.db", gardien)
    yield b
    b.fermer()
