"""Outils communs : des réglages dont tous les chemins sont dans un bac à sable temporaire."""

from __future__ import annotations

import pytest

from modules.trieur import config


@pytest.fixture
def reglages(tmp_path):
    return config.pour_le_bac_a_sable(tmp_path / "bac")
