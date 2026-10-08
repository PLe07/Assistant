"""Le filet commun à tous les tests.

1. Un dossier personnel imité (`TABLEAU_MAISON`) : aucun test n'écrit dans ton vrai dossier, ni dans iCloud.
2. Le réseau est coupé, sauf vers 127.0.0.1 (la page locale, n8n imité) : toute autre connexion fait échouer le test.
3. Le fuseau est celui de Paris, comme sur ton Mac.
"""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

LOCAUX = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def maison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    m = tmp_path / "maison"
    m.mkdir()
    monkeypatch.setenv("TABLEAU_MAISON", str(m))
    monkeypatch.delenv("TABLEAU_ICLOUD", raising=False)
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    for variable in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(variable, raising=False)
    yield m


@pytest.fixture(autouse=True)
def reseau_coupe(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Seul 127.0.0.1 est joignable pendant les tests ; toute autre tentative est notée et fait échouer le test."""
    tentatives: list[str] = []
    connect_origine = socket.socket.connect
    getaddrinfo_origine = socket.getaddrinfo

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        nom = host.decode() if isinstance(host, bytes) else str(host or "")
        if nom not in LOCAUX:
            tentatives.append(nom)
            raise OSError(f"réseau coupé pendant les tests ({nom})")
        return getaddrinfo_origine(host, *args, **kwargs)

    def connect(self: socket.socket, adresse: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6) and str(adresse[0]) not in LOCAUX:
            tentatives.append(str(adresse[0]))
            raise OSError(f"réseau coupé pendant les tests ({adresse[0]})")
        return connect_origine(self, adresse)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
    yield tentatives
    assert not tentatives, f"connexion sortante tentée pendant le test : {tentatives}"


@pytest.fixture
def horloge() -> Any:
    """Une horloge qu'on avance à la main."""

    class Horloge:
        def __init__(self) -> None:
            # Mercredi 7 octobre 2026, 10:00 à Paris.
            self.t = 1791360000.0

        def __call__(self) -> float:
            return self.t

        def avancer(self, secondes: float) -> None:
            self.t += secondes

    return Horloge()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    est_mac = os.uname().sysname == "Darwin"
    for item in items:
        if item.get_closest_marker("mac") and not est_mac:
            item.add_marker(pytest.mark.skip(reason="seulement sur un Mac (lancé par install.sh)"))


@pytest.fixture
def site(maison: Path) -> Iterator[Any]:
    """La page locale servie sur un port libre, avec le jeu de données de `tests/fabrique_web.py`."""
    from tableau.web import serveur
    from tests import fabrique_web

    source, notif = fabrique_web.construire(maison)
    s = serveur.Serveur(source, fabrique_web.JETON, 0, battement_s=0.5).demarrer()
    s.notificateur = notif  # type: ignore[attr-defined]
    try:
        yield s
    finally:
        s.arreter()
        source.base.fermer()
