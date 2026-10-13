from __future__ import annotations

import platform
from pathlib import Path

import pytest

from tests.faux_mac import FauxMac, fabriquer


@pytest.fixture
def mac(tmp_path: Path) -> FauxMac:
    return fabriquer(tmp_path)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Les tests marqués `mac` demandent un vrai Mac : ailleurs, ils sont ignorés en le disant (et rejoués par
    `voix verifier` sur le Mac)."""
    if platform.system() == "Darwin":
        return
    ignore = pytest.mark.skip(reason="demande un vrai Mac : rejoué par voix verifier")
    for item in items:
        if "mac" in item.keywords:
            item.add_marker(ignore)
