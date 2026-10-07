"""La liste blanche du réseau (§0.6) : Anthropic et Open-Meteo, rien d'autre."""

from __future__ import annotations

import socket
import urllib.request
from typing import Any

import pytest

from quotidien import reseau


def test_la_liste_blanche_est_exactement_celle_de_la_mission() -> None:
    assert reseau.HOTES_PERMIS == {"api.anthropic.com", "api.open-meteo.com", "geocoding-api.open-meteo.com"}


@pytest.mark.parametrize(
    "hote",
    ["api.anthropic.com", "API.Open-Meteo.com", "geocoding-api.open-meteo.com", "api.open-meteo.com."],
)
def test_hotes_permis(hote: str) -> None:
    assert reseau.hote_autorise(hote)


@pytest.mark.parametrize(
    "hote",
    [
        "open-meteo.com",
        "archive-api.open-meteo.com",
        "api.open-meteo.com.pirate.net",
        "evil-api.anthropic.com",
        "anthropic.com",
        "pypi.org",
        "google.com",
        "",
        "1.2.3.4",
    ],
)
def test_hotes_refuses(hote: str) -> None:
    assert not reseau.hote_autorise(hote)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.open-meteo.com/v1/forecast",  # pas de HTTPS
        "https://api.open-meteo.com.pirate.net/v1/forecast",
        "https://www.marmiton.org/recettes",
        "ftp://api.open-meteo.com/x",
        "https:///sans-hote",
    ],
)
def test_telecharger_refuse_avant_tout_contact(url: str, espion_reseau: Any) -> None:
    with pytest.raises(reseau.HoteInterdit):
        reseau.telecharger(url)
    assert espion_reseau.hotes == []


def test_telecharger_hote_permis_mais_reseau_coupe_donne_erreur_reseau(espion_reseau: Any) -> None:
    with pytest.raises(reseau.ErreurReseau):
        reseau.telecharger("https://api.open-meteo.com/v1/forecast?latitude=44.8&longitude=-0.6", delai=2)
    assert "api.open-meteo.com" in espion_reseau.hotes


def test_une_redirection_hors_liste_est_refusee() -> None:
    poignee = reseau._Redirections()
    requete = urllib.request.Request("https://api.open-meteo.com/v1/forecast")
    with pytest.raises(reseau.HoteInterdit):
        poignee.redirect_request(requete, None, 302, "Found", None, "https://pirate.example/vol")  # type: ignore[arg-type]
    suivie = poignee.redirect_request(requete, None, 302, "Found", None, "https://api.open-meteo.com/v1/autre")  # type: ignore[arg-type]
    assert suivie is not None and suivie.full_url.endswith("/v1/autre")


def test_garde_du_processus_refuse_les_autres_hotes() -> None:
    reseau.installer_garde()
    reseau.installer_garde()  # idempotent
    try:
        with pytest.raises(reseau.HoteInterdit):
            socket.getaddrinfo("example.com", 443)
        for permis in ("api.anthropic.com", "api.open-meteo.com", "localhost"):
            # Laissé passer par la garde (ce n'est pas HoteInterdit), puis coupé par l'espion des tests.
            with pytest.raises(OSError) as e:
                socket.getaddrinfo(permis, 443)
            assert not isinstance(e.value, reseau.HoteInterdit)
    finally:
        socket.getaddrinfo = reseau._getaddrinfo_origine


def test_les_hotes_d_installation_ne_sont_pas_dans_le_processus() -> None:
    for hote in reseau.HOTES_INSTALLATION:
        assert not reseau.hote_autorise(hote)


def test_espion_refuse_un_hote_hors_liste(espion_reseau: Any) -> None:
    """L'espion lui-même : un hôte hors liste tenté est noté (et ferait échouer le test)."""
    with pytest.raises(OSError):
        socket.getaddrinfo("www.marmiton.org", 443)
    assert espion_reseau.interdits == ["www.marmiton.org"]
    espion_reseau.interdits.clear()  # noté comme attendu : ce test-ci ne doit pas échouer pour ça


def test_reponse_texte() -> None:
    r = reseau.Reponse(200, "été".encode(), "https://api.open-meteo.com/")
    assert r.texte() == "été"
