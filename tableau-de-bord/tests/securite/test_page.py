"""La sécurité de la page locale (§9.3) : jeton, Host (rebond DNS), Origin, 127.0.0.1 seulement, en-têtes, rien de
personnel dans les réponses, aucune commande d'un autre module sans un POST explicite, aucun jeton dans un journal."""

from __future__ import annotations

import html
import os
import socket
import subprocess
import time
from typing import Any

import pytest

from tableau import config, systeme
from tableau.web import securite, serveur, sse
from tests.fabrique_web import ERREUR_BRUTE, JETON
from tests.outils_http import requete

PAGES = ["/", "/module/trieur", "/module/trieur?jours=30", "/credits", "/ressources", "/integrite", "/journal",
         "/journal?module=trieur", "/fragment/accueil", "/fragment/module/trieur", "/api/etat", "/api/module/trieur",
         "/static/app.css", "/static/app.js"]  # fmt: skip


@pytest.mark.parametrize("chemin", [*PAGES, "/evenements"])
def test_sans_jeton_ou_faux_jeton_refuse(site: Any, chemin: str) -> None:
    for jeton in (None, "", "faux", JETON[:-1], JETON + "x", f"{JETON}&t={JETON}"):
        r = requete(site.port, chemin, jeton=jeton)
        assert r.code == 403, (chemin, jeton)
        assert "Trieur" not in r.texte and "alice" not in r.texte


@pytest.mark.parametrize(
    "hote",
    ["evil.com", "evil.com:{port}", "attaquant.example:{port}", "127.0.0.1", "127.0.0.1:1", "localhost:80",
     "127.0.0.1.nip.io:{port}", "[::1]:{port}", "0.0.0.0:{port}", "", "127.0.0.1:{port}.evil.com"],
)  # fmt: skip
def test_hote_etranger_refuse_meme_avec_le_jeton(site: Any, hote: str) -> None:
    r = requete(site.port, "/", hote=hote.format(port=site.port))
    assert r.code == 421 and "Trieur" not in r.texte


def test_sans_en_tete_host(site: Any) -> None:
    with socket.create_connection(("127.0.0.1", site.port), timeout=5) as s:
        s.sendall(f"GET /?t={JETON} HTTP/1.0\r\n\r\n".encode())
        reponse = b""
        while morceau := s.recv(65536):
            reponse += morceau
    assert reponse.split(b"\r\n", 1)[0].endswith(b" 421 Misdirected Request") and b"Trieur" not in reponse


def test_hotes_permis(site: Any) -> None:
    assert requete(site.port, "/").code == 200
    assert requete(site.port, "/", hote=f"localhost:{site.port}").code == 200
    assert requete(site.port, "/", hote=f"LOCALHOST:{site.port}").code == 200


def test_post_origine_et_jeton(site: Any) -> None:
    corps = {"duree": "1h"}
    assert requete(site.port, "/action/sourdine", "POST", corps=corps).code == 200
    assert (
        requete(site.port, "/action/sourdine", "POST", {"Origin": f"http://127.0.0.1:{site.port}"}, corps).code == 200
    )
    for mauvaise in ("http://evil.com", f"http://evil.com:{site.port}", "null", f"https://127.0.0.1:{site.port}",
                     "http://127.0.0.1:1", ""):  # fmt: skip
        r = requete(site.port, "/action/sourdine", "POST", {"Origin": mauvaise}, corps)
        assert r.code == 403 and r.json()["ok"] is False, mauvaise
    assert requete(site.port, "/action/sourdine", "POST", {"Sec-Fetch-Site": "cross-site"}, corps).code == 403
    assert requete(site.port, "/action/sourdine", "POST", {"X-Jeton": "faux"}, corps).code == 403
    assert requete(site.port, "/action/sourdine", "POST", {"X-Jeton": None}, corps).code == 403  # type: ignore[dict-item]
    assert requete(site.port, "/action/sourdine", "POST", {"Content-Type": "text/plain"}, corps).code == 415
    assert requete(site.port, "/action/sourdine", "POST", corps=corps, jeton=None).code == 403
    # Corps trop long, illisible, ou qui n'est pas un objet.
    assert requete(site.port, "/action/sourdine", "POST", corps={"duree": "x" * 5000}).code == 413
    assert requete(site.port, "/action/sourdine", "POST", corps=["1h"]).code == 400
    assert requete(site.port, "/action/sourdine", "POST", corps={"duree": "demain"}).code == 400
    assert requete(site.port, "/action/inconnue", "POST").code == 404
    assert requete(site.port, "/action/reference/inconnu", "POST").code == 404


def test_autres_methodes_refusees(site: Any) -> None:
    for methode in ("PUT", "DELETE", "PATCH", "OPTIONS"):
        r = requete(site.port, "/", methode)
        assert r.code == 405 and r.entetes.get("Content-Security-Policy") == securite.CSP


def test_en_tetes_de_protection_partout(site: Any) -> None:
    for chemin, jeton in [("/", JETON), ("/credits", JETON), ("/static/app.js", JETON), ("/", None), ("/zut", JETON)]:
        r = requete(site.port, chemin, jeton=jeton)
        for nom, valeur in securite.ENTETES.items():
            assert r.entetes.get(nom) == valeur, (chemin, nom)
    assert "unsafe-inline" not in securite.CSP and "unsafe-eval" not in securite.CSP
    assert "default-src 'none'" in securite.CSP and "frame-ancestors 'none'" in securite.CSP


def test_ecoute_seulement_sur_127_0_0_1(site: Any) -> None:
    assert site.server_address[0] == "127.0.0.1"
    # Le vrai lsof : la seule écoute de ce processus sur ce port est 127.0.0.1.
    r = subprocess.run(["lsof", "-nP", "-a", "-p", str(os.getpid()), f"-iTCP:{site.port}", "-sTCP:LISTEN"],
                       capture_output=True, text=True, timeout=20)  # fmt: skip
    lignes = [ligne for ligne in r.stdout.splitlines()[1:] if ligne.strip()]
    assert lignes and all(f"127.0.0.1:{site.port} (LISTEN)" in ligne for ligne in lignes), r.stdout
    # Depuis une autre adresse de la machine (s'il y en a une), la page est injoignable.
    try:
        autre = socket.gethostbyname(socket.gethostname())
    except OSError:
        autre = "127.0.0.1"
    if not autre.startswith("127."):
        with pytest.raises(OSError), socket.create_connection((autre, site.port), timeout=2):
            pass


def test_rien_de_personnel_dans_les_reponses(site: Any) -> None:
    assert "alice.martin@example.com" in ERREUR_BRUTE  # la base contient bien l'erreur brute
    for chemin in PAGES:
        texte = requete(site.port, chemin).texte
        assert "alice.martin@example.com" not in texte and "/Users/" not in texte, chemin
        assert JETON not in texte or chemin not in ("/api/etat", "/api/module/trieur"), chemin
    detail = html.unescape(requete(site.port, "/module/trieur").texte)
    assert "Échec d'envoi à [e-mail] depuis ~/Projets/trieur/main.py" in detail


def test_aucune_commande_sans_post(site: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Les pages ne lancent rien ; le diagnostic d'un module ne part que sur un POST avec le jeton."""
    lances: list[Any] = []
    origine = systeme.executer_diagnostic

    def espion(commande: list[str], dossier: Any, demande: Any, delai: float = 120) -> systeme.Resultat:
        lances.append(demande)
        return origine(commande, dossier, demande, delai)

    monkeypatch.setattr(systeme, "executer_diagnostic", espion)
    avant = len(systeme.JOURNAL)
    for chemin in [*PAGES, "/action/diagnostic/trieur"]:
        requete(site.port, chemin)
    requete(site.port, "/action/diagnostic/trieur", "POST", {"Origin": "http://evil.com"})
    requete(site.port, "/action/diagnostic/trieur", "POST", jeton=None)
    assert lances == [] and len(systeme.JOURNAL) == avant
    r = requete(site.port, "/action/diagnostic/trieur", "POST")
    assert r.code == 200 and len(lances) == 1 and lances[0] == systeme.DemandeExplicite("page", "trieur")
    d = r.json()
    assert d["ok"] and d["sortie"] == "diagnostic ok pour [e-mail]"  # caviardée elle aussi
    # Un module sans commande de diagnostic : rien n'est lancé.
    assert requete(site.port, "/action/diagnostic/bouclier", "POST").json()["ok"] is False
    assert len(lances) == 1


def test_aucun_jeton_dans_les_journaux(site: Any, capfd: pytest.CaptureFixture[str]) -> None:
    for chemin in PAGES:
        requete(site.port, chemin)
    requete(site.port, "/", jeton="faux")
    sortie, erreurs = capfd.readouterr()
    assert JETON not in sortie + erreurs and "GET /" not in sortie + erreurs


def test_fichiers_statiques_seulement_la_liste(site: Any) -> None:
    for chemin in ("/static/../config.py", "/static/%2e%2e/serveur.py", "/static/", "/static/app.css.map",
                   "/static//etc/passwd", "/../../etc/passwd"):  # fmt: skip
        r = requete(site.port, chemin)
        assert r.code == 404 and b"root:" not in r.corps, chemin


def test_trop_de_pages_en_direct(site: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sse, "CLIENTS_MAX", 0)
    assert requete(site.port, "/evenements").code == 503


def test_port_pris_un_autre_est_choisi_et_retenu(site: Any, maison: Any) -> None:
    retenus: list[int] = []
    occupe = socket.socket()
    occupe.bind(("127.0.0.1", 0))
    occupe.listen()
    pris = occupe.getsockname()[1]
    try:
        s = serveur.ouvrir(site.source, JETON, pris, retenus.append, range(pris + 1, pris + 40))
        try:
            assert s.port != pris and retenus == [s.port] and s.server_address[0] == "127.0.0.1"
            assert s.adresse == f"http://127.0.0.1:{s.port}/?t={JETON}"
        finally:
            s.server_close()
        # Le port retenu est écrit dans les réglages (le reste du fichier est gardé).
        c = config.Chemins(maison)
        c.reglages.write_text("# à moi\n[alertes]\nmax_par_jour = 2\n", encoding="utf-8")
        config.enregistrer_port(s.port, c.reglages)
        r = config.charger(c.reglages)
        assert r["serveur"]["port"] == s.port and r["alertes"]["max_par_jour"] == 2
        with pytest.raises(OSError, match="aucun port libre"):
            serveur.ouvrir(site.source, JETON, pris, None, range(pris, pris + 1))
    finally:
        occupe.close()


def test_head_sur_le_direct_et_longueur_illisible(site: Any) -> None:
    debut = time.monotonic()
    r = requete(site.port, "/evenements", "HEAD")
    assert r.code == 200 and r.corps == b"" and time.monotonic() - debut < 2
    assert site.source.diffuseur.clients == 0
    for longueur in ("abc", "-5"):
        with socket.create_connection(("127.0.0.1", site.port), timeout=5) as s:
            s.sendall((f"POST /action/sourdine?t={JETON} HTTP/1.1\r\nHost: 127.0.0.1:{site.port}\r\n"
                       f"X-Jeton: {JETON}\r\nContent-Type: application/json\r\nContent-Length: {longueur}\r\n"
                       "Connection: close\r\n\r\n").encode())  # fmt: skip
            reponse = s.recv(4096)
        assert reponse.split(b"\r\n", 1)[0].endswith(b" 400 Bad Request"), longueur
