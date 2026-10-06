"""Le corpus est fabriqué une fois par session de tests (≈ 15 s), dans un dossier temporaire."""

from __future__ import annotations

import pytest

from tests.trieur.corpus.generer import Corpus, generer


@pytest.fixture(scope="session")
def corpus1(tmp_path_factory) -> Corpus:
    return generer(tmp_path_factory.mktemp("corpus1"))
