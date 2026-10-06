"""Le filet commun à tous les tests.

1. Un dossier personnel imité (`BOUCLIER_MAISON`) : aucun test n'écrit dans ton vrai dossier.
2. Le réseau est coupé et espionné : toute résolution de nom ou connexion est notée. Un hôte hors de la liste
   blanche fait échouer le test, même si le code l'a « seulement » tenté.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from bouclier import reseau


class EspionReseau:
    def __init__(self) -> None:
        self.hotes: list[str] = []
        self.interdits: list[str] = []

    def noter(self, hote: str) -> None:
        self.hotes.append(hote)
        if not (reseau.est_local(hote) or reseau.hote_autorise(hote)):
            self.interdits.append(hote)


@pytest.fixture(autouse=True)
def maison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    m = tmp_path / "maison"
    m.mkdir()
    monkeypatch.setenv("BOUCLIER_MAISON", str(m))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    # Comme sur ton Mac : pas de mandataire réseau (celui du conteneur de construction cacherait l'hôte visé).
    for variable in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(variable, raising=False)
    return m


@pytest.fixture(autouse=True)
def espion_reseau(monkeypatch: pytest.MonkeyPatch) -> Any:
    espion = EspionReseau()

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        nom = host.decode() if isinstance(host, bytes) else str(host or "")
        espion.noter(nom)
        raise OSError(f"réseau coupé pendant les tests ({nom})")

    connect_origine = socket.socket.connect

    def connect(self: socket.socket, adresse: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            hote = str(adresse[0])
            espion.noter(hote)
            if not reseau.est_local(hote):
                raise OSError(f"réseau coupé pendant les tests ({hote})")
        return connect_origine(self, adresse)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(reseau, "_getaddrinfo_origine", getaddrinfo)
    monkeypatch.setattr(reseau, "_garde_installee", False)
    monkeypatch.setattr(socket.socket, "connect", connect)
    reseau._rdap_designes.clear()
    yield espion
    assert not espion.interdits, f"hôtes hors liste blanche contactés : {sorted(set(espion.interdits))}"
