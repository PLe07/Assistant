from __future__ import annotations

from pathlib import Path

import pytest

from tests.faux_mac import FauxMac, fabriquer


@pytest.fixture
def mac(tmp_path: Path) -> FauxMac:
    return fabriquer(tmp_path)
