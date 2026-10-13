"""Le démon sur un vrai socket Unix : une fausse app se connecte, parle, répond aux ordres ; `voix dire` ; un seul
moteur à la fois ; un vieux socket est remplacé ; les messages invalides ne cassent rien ; arrêt propre."""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tests.faux_mac import FauxMac, fabriquer
from tests.integration.test_moteur import PHRASE, FauxWhisper
from tests.unitaires.test_audio import VadScript
from voix import config, demon, protocole
from voix.actions.pont import OrdreRefuse, ReponsePont
from voix.audio.vad import TRAME
from voix.socket_serveur import Connexion, DejaLance, PontSocket, Travailleur


class FausseApp:
    def __init__(self, chemin: Path) -> None:
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(10)
        self.s.connect(str(chemin))
        self.tampon = b""

    def envoyer(self, **m: Any) -> None:
        self.s.sendall(protocole.encoder(m))

    def attendre(self, genre: str, delai_s: float = 10.0) -> dict[str, Any]:
        fin = time.monotonic() + delai_s
        while time.monotonic() < fin:
            while b"\n" in self.tampon:
                ligne, self.tampon = self.tampon.split(b"\n", 1)
                m = json.loads(ligne)
                assert m["v"] == 1
                if m["type"] == genre:
                    return m
            self.tampon += self.s.recv(65536)
        raise AssertionError(f"pas de message {genre}")

    def fermer(self) -> None:
        self.s.close()


@pytest.fixture
def court() -> Iterator[Path]:
    """Un dossier au chemin court : un socket Unix ne dépasse pas 104 caractères sur macOS."""
    d = Path(tempfile.mkdtemp(prefix="vx", dir="/tmp"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


class Demon:
    def __init__(self, mac: FauxMac, whisper: FauxWhisper) -> None:
        self.mac = mac
        self.chemins = config.Chemins(mac.maison)
        self.arret = threading.Event()
        self.pret = threading.Event()
        self.code: list[int] = []

        def outils(ch: config.Chemins, rg: config.Reglages, pont: PontSocket) -> Any:
            return mac.outils(pont=pont, chemins=ch)

        self.fil = threading.Thread(target=lambda: self.code.append(demon.lancer(
            self.chemins, None, self.arret, (whisper, "faux Whisper"), lambda: VadScript(PHRASE),
            lambda _m: self.pret.set(), outils)), daemon=True)  # fmt: skip

    def __enter__(self) -> Demon:
        self.fil.start()
        assert self.pret.wait(20)
        return self

    def __exit__(self, *_: object) -> None:
        self.arret.set()
        self.fil.join(10)


def test_le_demon_de_bout_en_bout(court: Path) -> None:
    mac = fabriquer(court)
    with Demon(mac, FauxWhisper()) as d:
        sock = d.chemins.socket
        assert sock.stat().st_mode & 0o777 == 0o600 and d.chemins.support.stat().st_mode & 0o777 == 0o700
        app = FausseApp(sock)
        app.envoyer(type="bonjour", client="app", version="1.0.0")
        b = app.attendre("bonjour")
        assert b["transcription"] == "whisper" and "Notion" in b["vocabulaire"]
        # Une écoute : l'audio par morceaux de 100 ms, comme l'app.
        app.envoyer(type="ecoute", etat="debut", id=1, mode="appui")
        pcm = (np.ones(len(PHRASE) * TRAME) * 3000).astype("<i2").tobytes()
        for i in range(0, len(pcm), 3200):
            app.envoyer(type="audio", id=1, pcm=base64.b64encode(pcm[i : i + 3200]).decode())
        assert app.attendre("micro")["raison"] == "silence"
        r = app.attendre("reponse")
        assert r["statut"] == "fait" and r["texte"] == "✓ Notion ouvert"
        # Un ordre pour l'app (quitter Spotify) : le moteur demande, l'app répond.
        app.envoyer(type="texte", texte="ferme Spotify", source="clic")
        ordre = app.attendre("pont")
        assert ordre["ordre"] == "app.quitter" and ordre["params"] == {"bundle": "com.spotify.client"}
        app.envoyer(type="pont", id=ordre["id"], ok=True, donnees={})
        assert app.attendre("reponse")["statut"] == "fait"
        # Des lignes invalides : ignorées, le moteur continue.
        app.s.sendall(b"pas du json\n" + b'{"v": 1, "type": "shell", "cmd": "rm -rf ~"}\n')
        app.s.sendall(b"x" * (protocole.TAILLE_MAX_LIGNE + 10) + b"\n")
        r = demon.dire("ouvre YouTube", sock)
        assert r is not None and r["statut"] == "fait" and r["ref"].startswith("cli")
        assert mac.appels()[-1] == ("open", ["https://www.youtube.com"])
        # Un second moteur refuse de démarrer.
        assert demon.lancer(d.chemins, None, threading.Event(), (None, "x")) == 1
        # L'app part : les ordres ne partent plus, et on le dit.
        app.fermer()
        time.sleep(0.3)
        r = demon.dire("ferme Spotify", sock)
        assert r is not None and "pas lancée" in r["texte"]
    assert d.code == [0] and not sock.exists()
    etat = json.loads(d.chemins.etat.read_text())
    assert etat["transcription"] == "whisper" and etat["raison"] == "faux Whisper" and "arrete" in etat
    assert etat["messages_ignores"] >= 2 and etat["erreurs"] == 0
    assert d.chemins.etat.stat().st_mode & 0o777 == 0o600
    assert "moteur démarré" in (d.chemins.logs / "moteur.log").read_text()
    assert not any(f.suffix in (".wav", ".aiff", ".caf", ".raw") for f in court.rglob("*"))  # jamais d'audio écrit


def test_vieux_socket_remplace_et_fichier_inattendu(court: Path) -> None:
    mac = fabriquer(court)
    chemins = config.Chemins(mac.maison)
    chemins.preparer()
    vieux = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    vieux.bind(str(chemins.socket))
    vieux.close()  # un moteur arrêté net laisse son socket
    with Demon(mac, FauxWhisper()) as d:
        assert demon.dire("quelle heure est-il", d.chemins.socket) is not None
    chemins.socket.write_text("pas un socket")
    assert demon.lancer(chemins, None, threading.Event(), (None, "x")) == 1
    assert chemins.socket.read_text() == "pas un socket"  # rien n'est touché


def test_dire_sans_moteur_et_choix_de_la_transcription(court: Path) -> None:
    assert demon.dire("ouvre Safari", court / "absent.sock") is None
    ch = config.Chemins(court)
    r = config.Reglages({s: dict(v) for s, v in config.DEFAUTS.items()})
    t, raison = demon.choisir_transcription(ch, r)
    assert t is None and raison.startswith("Apple Speech (Whisper indisponible")
    r.valeurs["moteur"]["choix"] = "apple"
    assert demon.choisir_transcription(ch, r) == (
        None,
        "Apple Speech (choisi dans les réglages ou par le banc d'essai)",
    )


def test_pont_socket_delai_et_refus() -> None:
    p = PontSocket(delai_s=0.2)
    assert p.demander("app.cacher", {"bundle": "com.apple.Safari"}).erreur == "l'app Commandes Vocales n'est pas lancée"
    envoyes: list[dict[str, Any]] = []
    p.envoyer = lambda m: envoyes.append(m) is None
    assert p.demander("app.cacher", {"bundle": "com.apple.Safari"}) == ReponsePont(
        False, {}, "l'app Commandes Vocales ne répond pas"
    )
    with pytest.raises(OrdreRefuse):
        p.demander("shell", {"cmd": "rm -rf ~"})
    assert [m["ordre"] for m in envoyes] == ["app.cacher"]
    p.envoyer = lambda m: False
    assert "pas lancée" in p.demander("ecran.verrouiller", {}).erreur
    p.recevoir({"id": 999, "ok": True})  # une réponse sans demande : ignorée


def test_travailleur_survit_aux_erreurs() -> None:
    t = Travailleur()
    t.demarrer()
    fait = threading.Event()
    t.soumettre(lambda: 1 / 0)
    t.soumettre(fait.set)
    assert fait.wait(5) and t.erreurs == 1
    t.arreter()


def test_connexion_decoupe_les_lignes() -> None:
    a, b = socket.socketpair()
    c = Connexion(a)
    assert c.lignes(b'{"v":1}\n{"v"') == [b'{"v":1}'] and c.lignes(b":2}\r\n\n") == [b'{"v":2}']
    assert c.lignes(b"x" * (protocole.TAILLE_MAX_LIGNE + 1)) == [] and c.invalides == 1
    assert c.lignes(b"suite de la ligne trop longue\nok\n") == [b"ok"]
    assert c.envoyer({"type": "etat"}) and b.recv(100).startswith(b'{"v": 1')
    a.close()
    b.close()
    assert c.envoyer({"type": "etat"}) is False


def test_deja_lance_est_une_erreur_claire(court: Path) -> None:
    from voix.socket_serveur import _ancien_socket

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(court / "v.sock"))
    s.listen(1)
    with pytest.raises(DejaLance, match="tourne déjà"):
        _ancien_socket(court / "v.sock")
    s.close()
    assert os.path.exists(court / "v.sock")
