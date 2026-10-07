"""Le filet commun à tous les tests.

1. Un dossier personnel imité (`QUOTIDIEN_MAISON`) : aucun test n'écrit dans ton vrai dossier, ni dans iCloud.
2. Le réseau est coupé et espionné : toute résolution de nom ou connexion est notée. Un hôte hors de la liste
   blanche fait échouer le test, même si le code l'a « seulement » tenté.
3. Aucune vraie IA, aucune vraie commande du Mac : les tests `reel` le font exprès, sur le Mac.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from quotidien import journal, reseau


class EspionReseau:
    def __init__(self) -> None:
        self.hotes: list[str] = []
        self.interdits: list[str] = []

    def noter(self, hote: str) -> None:
        self.hotes.append(hote)
        if not (reseau.est_local(hote) or reseau.hote_autorise(hote)):
            self.interdits.append(hote)


@pytest.fixture(autouse=True)
def maison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    m = tmp_path / "maison"
    m.mkdir()
    monkeypatch.setenv("QUOTIDIEN_MAISON", str(m))
    monkeypatch.setenv("TZ", "Europe/Paris")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("QUOTIDIEN_DOSSIER_ICLOUD", raising=False)
    # Comme sur ton Mac : pas de mandataire réseau (celui du conteneur de construction cacherait l'hôte visé).
    for variable in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(variable, raising=False)
    journal.oublier()
    yield m
    journal.oublier()


@pytest.fixture(autouse=True)
def sans_vraie_ia(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun test n'appelle le vrai Claude Code de la machine (les tests `reel` le font exprès, sur le Mac)."""
    from quotidien import ia

    monkeypatch.setattr(ia, "trouver_claude", lambda: "/introuvable/claude")


@pytest.fixture(autouse=True)
def espion_reseau(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Any:
    """Réseau coupé. Les tests `reel` (sur le Mac, à la demande) passent vers les hôtes de la liste blanche
    seulement : tout autre hôte est refusé et fait échouer le test."""
    espion = EspionReseau()
    reel = request.node.get_closest_marker("reel") is not None
    getaddrinfo_origine = socket.getaddrinfo
    resolues: set[str] = set()

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        nom = host.decode() if isinstance(host, bytes) else str(host or "")
        espion.noter(nom)
        if reel and (reseau.hote_autorise(nom) or reseau.est_local(nom)):
            reponse = getaddrinfo_origine(host, *args, **kwargs)
            resolues.update(str(r[4][0]) for r in reponse)
            return reponse
        raise OSError(f"réseau coupé pendant les tests ({nom})")

    connect_origine = socket.socket.connect

    def connect(self: socket.socket, adresse: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            hote = str(adresse[0])
            if not (reel and hote in resolues):
                espion.noter(hote)
                if not reseau.est_local(hote):
                    raise OSError(f"réseau coupé pendant les tests ({hote})")
        return connect_origine(self, adresse)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(reseau, "_getaddrinfo_origine", getaddrinfo)
    monkeypatch.setattr(reseau, "_garde_installee", False)
    monkeypatch.setattr(socket.socket, "connect", connect)
    yield espion
    assert not espion.interdits, f"hôtes hors liste blanche contactés : {sorted(set(espion.interdits))}"
