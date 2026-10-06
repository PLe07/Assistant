"""Outils communs : des réglages dont tous les chemins sont dans un bac à sable temporaire."""

from __future__ import annotations

import pytest

from modules.trieur import config


@pytest.fixture
def reglages(tmp_path):
    return config.pour_le_bac_a_sable(tmp_path / "bac")


@pytest.fixture
def faux_mac():
    from tests.trieur.outils import FauxSysteme

    return FauxSysteme()


@pytest.fixture
def outils(reglages, faux_mac):
    """La chaîne complète dans un bac à sable, avec un faux Mac et un faux OCR (sans texte)."""
    from modules.trieur import traitement
    from tests.trieur.outils import FauxOCR

    o = traitement.outils(reglages, systeme_=faux_mac, moteur=FauxOCR(), ia=None)
    yield o
    o.base.fermer()
