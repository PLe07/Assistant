"""§0.6 et §11.2 : la liste blanche du réseau."""

from __future__ import annotations

import socket
import urllib.request
from email.message import Message
from http.client import HTTPMessage
from typing import Any

import pytest

from bouclier import reseau


@pytest.mark.parametrize(
    "hote",
    [
        "api.anthropic.com",
        "haveibeenpwned.com",
        "rdap.org",
        "openphish.com",
        "urlhaus.abuse.ch",
        "imap.gmail.com",
        "www.cybermalveillance.gouv.fr",
        "www.service-public.fr",
        "www.interieur.gouv.fr",
        "www.gouvernement.fr",
        "www.chu-bordeaux.fr",
        "www.centres-antipoison.net",
    ],
)
def test_hotes_permis(hote: str) -> None:
    assert reseau.hote_autorise(hote)


@pytest.mark.parametrize(
    "hote",
    [
        "colissimo-suivi-frais.top",
        "evil.com",
        "gouv.fr.evil.com",
        "faux-gouv.fr",
        "anthropic.com.evil.net",
        "rdap.verisign.com",  # pas tant que rdap.org ne l'a pas désigné
        "pypi.org",  # installation seulement, jamais depuis Bouclier
    ],
)
def test_hotes_refuses(hote: str) -> None:
    assert not reseau.hote_autorise(hote)


def test_telecharger_refuse_sans_contacter(espion_reseau: Any) -> None:
    with pytest.raises(reseau.HoteInterdit):
        reseau.telecharger("https://colissimo-suivi-frais.top/payer")
    with pytest.raises(reseau.HoteInterdit):
        reseau.telecharger("http://haveibeenpwned.com/api/v3/breaches")  # pas de HTTP en clair
    assert espion_reseau.hotes == []


def test_telecharger_hote_permis_mais_reseau_coupe(espion_reseau: Any) -> None:
    with pytest.raises(reseau.ErreurReseau):
        reseau.telecharger("https://haveibeenpwned.com/api/v3/breaches", delai=1)
    assert espion_reseau.hotes == ["haveibeenpwned.com"]


def test_designation_rdap_stricte() -> None:
    with pytest.raises(reseau.HoteInterdit):
        reseau.designer_serveur_rdap("http://rdap.verisign.com/com/v1/domain/exemple.com", "exemple.com")
    with pytest.raises(reseau.HoteInterdit):
        reseau.designer_serveur_rdap("https://evil.example/autre/chose", "exemple.com")
    with pytest.raises(reseau.HoteInterdit):
        reseau.designer_serveur_rdap("https://192.0.2.4/domain/exemple.com", "exemple.com")
    assert reseau.designer_serveur_rdap("https://rdap.verisign.com/com/v1/domain/EXEMPLE.com", "exemple.com")
    assert reseau.hote_autorise("rdap.verisign.com")


def test_redirection_vers_hote_interdit_refusee() -> None:
    gestion = reseau._Redirections(None)
    req = urllib.request.Request("https://haveibeenpwned.com/api/v3/breaches")
    with pytest.raises(reseau.HoteInterdit):
        gestion.redirect_request(req, None, 302, "Found", HTTPMessage(), "https://evil.com/")


def test_redirection_rdap_designee() -> None:
    gestion = reseau._Redirections("exemple.fr")
    req = urllib.request.Request("https://rdap.org/domain/exemple.fr")
    nouvelle = gestion.redirect_request(req, None, 302, "Found", HTTPMessage(), "https://rdap.nic.fr/domain/exemple.fr")
    assert nouvelle is not None and reseau.hote_autorise("rdap.nic.fr")


def test_garde_du_processus(espion_reseau: Any) -> None:
    reseau.installer_garde()
    reseau.installer_garde()  # idempotent
    with pytest.raises(reseau.HoteInterdit):
        socket.getaddrinfo("evil.com", 443)
    with pytest.raises(OSError):  # permis, mais coupé pendant les tests
        socket.getaddrinfo("api.anthropic.com", 443)
    assert espion_reseau.hotes == ["api.anthropic.com"]


def test_reponse_texte() -> None:
    assert reseau.Reponse(200, "é".encode(), "https://rdap.org/").texte() == "é"


class _FauxFlux:
    def __init__(self, corps: bytes, statut: int = 200) -> None:
        self.corps = corps
        self.status = statut
        self.headers = Message()
        self.headers["Content-Type"] = "text/plain"

    def read(self, n: int) -> bytes:
        return self.corps[:n]

    def geturl(self) -> str:
        return "https://openphish.com/feed.txt"

    def __enter__(self) -> _FauxFlux:
        return self

    def __exit__(self, *a: Any) -> None:
        return None


def test_telecharger_lit_et_borne_la_taille(monkeypatch: pytest.MonkeyPatch) -> None:
    class Ouvreur:
        def __init__(self, corps: bytes) -> None:
            self.corps = corps
            self.vu: list[urllib.request.Request] = []

        def open(self, req: urllib.request.Request, timeout: float) -> _FauxFlux:
            self.vu.append(req)
            return _FauxFlux(self.corps)

    ouvreur = Ouvreur(b"https://a.example/x\n")
    monkeypatch.setattr(urllib.request, "build_opener", lambda *h: ouvreur)
    r = reseau.telecharger("https://openphish.com/feed.txt")
    assert r.statut == 200 and r.texte().startswith("https://a.example")
    assert ouvreur.vu[0].get_header("User-agent", "").startswith("Bouclier/")
    ouvreur.corps = b"x" * 20
    with pytest.raises(reseau.ErreurReseau):
        reseau.telecharger("https://openphish.com/feed.txt", max_octets=10)


def test_telecharger_erreur_http(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import urllib.error

    class Ouvreur:
        def open(self, req: urllib.request.Request, timeout: float) -> Any:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", Message(), io.BytesIO(b"lent"))

    monkeypatch.setattr(urllib.request, "build_opener", lambda *h: Ouvreur())
    r = reseau.telecharger("https://haveibeenpwned.com/api/v3/breaches")
    assert r.statut == 429 and r.corps == b"lent"
