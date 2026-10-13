"""Le socket Unix du moteur (`~/Library/Application Support/Voix/voix.sock`, droits 0600 dans un dossier 0700).

- `Serveur` : accepte l'app (et `voix dire`), découpe les lignes (1 Mio au plus), vérifie chaque message
  (`protocole.decoder`) et le passe au moteur ; une ligne invalide est ignorée et comptée, jamais fatale.
- `Travailleur` : un seul fil pour tout le travail du moteur (dans l'ordre d'arrivée) ; une erreur est notée dans le
  journal technique et le moteur continue.
- `PontSocket` : envoie un ordre fermé à l'app et attend sa réponse (5 s au plus). Les réponses de l'app sont
  traitées tout de suite par le fil du socket, jamais derrière le travailleur (qui attend justement cette réponse).
"""

from __future__ import annotations

import contextlib
import errno
import itertools
import logging
import os
import queue
import selectors
import socket
import stat
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from voix import protocole
from voix.actions.pont import ReponsePont, valider

journal = logging.getLogger("voix.socket")


class DejaLance(Exception):
    """Un autre moteur écoute déjà sur ce socket."""


class Connexion:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.tampon = bytearray()
        self.en_rejet = False
        self.client = "?"
        self.verrou = threading.Lock()
        self.fermee = False
        self.invalides = 0

    def envoyer(self, message: dict[str, Any]) -> bool:
        donnees = protocole.encoder(message)
        with self.verrou:
            if self.fermee:
                return False
            try:
                self.sock.sendall(donnees)
            except OSError:
                self.fermee = True
                return False
        return True

    def lignes(self, octets: bytes) -> list[bytes]:
        """Les lignes complètes reçues ; une ligne trop longue est jetée entière."""
        sorties: list[bytes] = []
        debut = 0
        while True:
            i = octets.find(b"\n", debut)
            if i < 0:
                reste = octets[debut:]
                if not self.en_rejet:
                    self.tampon += reste
                    if len(self.tampon) > protocole.TAILLE_MAX_LIGNE:
                        self.tampon.clear()
                        self.en_rejet = True
                        self.invalides += 1
                break
            if self.en_rejet:
                self.en_rejet = False
            else:
                ligne = bytes(self.tampon + octets[debut:i]).rstrip(b"\r")
                if len(ligne) > protocole.TAILLE_MAX_LIGNE:
                    self.invalides += 1
                elif ligne:
                    sorties.append(ligne)
            self.tampon.clear()
            debut = i + 1
        return sorties


class Travailleur:
    def __init__(self) -> None:
        self.file: queue.Queue[Callable[[], object] | None] = queue.Queue()
        self.fil = threading.Thread(target=self._boucle, name="voix-travail", daemon=True)
        self.erreurs = 0

    def demarrer(self) -> None:
        self.fil.start()

    def soumettre(self, travail: Callable[[], object]) -> None:
        self.file.put(travail)

    def arreter(self, delai_s: float = 5.0) -> None:
        self.file.put(None)
        if self.fil.is_alive():
            self.fil.join(delai_s)

    def _boucle(self) -> None:
        while True:
            travail = self.file.get()
            if travail is None:
                return
            try:
                travail()
            except Exception:  # noqa: BLE001 - le moteur ne doit jamais tomber pour une commande
                self.erreurs += 1
                journal.exception("erreur pendant un travail du moteur")


class PontSocket:
    """Le pont vers l'app par le socket : des ordres de la liste fermée, une réponse attendue 5 s au plus."""

    def __init__(self, delai_s: float = 5.0) -> None:
        self.delai_s = delai_s
        self.envoyer: Callable[[dict[str, Any]], bool] | None = None
        self._ids = itertools.count(1)
        self._attentes: dict[int, list[Any]] = {}
        self._verrou = threading.Lock()

    def demander(self, ordre: str, params: dict[str, Any]) -> ReponsePont:
        propres = valider(ordre, params)
        envoyer = self.envoyer
        if envoyer is None:
            return ReponsePont(False, {}, "l'app Commandes Vocales n'est pas lancée")
        ident = next(self._ids)
        evenement = threading.Event()
        with self._verrou:
            self._attentes[ident] = [evenement, None]
        try:
            if not envoyer({"type": "pont", "id": ident, "ordre": ordre, "params": propres}):
                return ReponsePont(False, {}, "l'app Commandes Vocales n'est pas lancée")
            if not evenement.wait(self.delai_s):
                return ReponsePont(False, {}, "l'app Commandes Vocales ne répond pas")
            with self._verrou:
                reponse = self._attentes[ident][1]
            assert isinstance(reponse, ReponsePont)
            return reponse
        finally:
            with self._verrou:
                self._attentes.pop(ident, None)

    def recevoir(self, m: dict[str, Any]) -> None:
        with self._verrou:
            attente = self._attentes.get(m["id"])
            if attente is None:
                return
            donnees = m.get("donnees") or {}
            attente[1] = ReponsePont(bool(m["ok"]), dict(donnees), str(m.get("erreur") or "")[:300])
            attente[0].set()


def _ancien_socket(chemin: Path) -> None:
    """Un socket laissé par un moteur arrêté net est retiré ; un moteur vivant fait refuser le démarrage."""
    try:
        mode = chemin.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(mode):
        raise DejaLance(f"{chemin} existe et n'est pas un socket : rien n'est touché")
    essai = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    essai.settimeout(1.0)
    try:
        essai.connect(str(chemin))
    except OSError as e:
        if e.errno in (errno.ECONNREFUSED, errno.ENOENT):
            chemin.unlink(missing_ok=True)
            return
        raise
    finally:
        essai.close()
    raise DejaLance("un moteur Voix tourne déjà")


class Serveur:
    def __init__(
        self,
        chemin: Path,
        quand_message: Callable[[Connexion, dict[str, Any]], None],
        quand_depart: Callable[[Connexion], None] = lambda _c: None,
        tic: Callable[[], None] = lambda: None,
        periode_tic_s: float = 1.0,
    ) -> None:
        self.chemin = chemin
        self.quand_message = quand_message
        self.quand_depart = quand_depart
        self.tic = tic
        self.periode_tic_s = periode_tic_s
        self.selecteur = selectors.DefaultSelector()
        self.ecoute: socket.socket | None = None
        self.connexions: dict[int, Connexion] = {}
        self.invalides = 0

    def demarrer(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.chemin.parent, 0o700)
        _ancien_socket(self.chemin)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ancien = os.umask(0o177)
        try:
            s.bind(str(self.chemin))
        finally:
            os.umask(ancien)
        os.chmod(self.chemin, 0o600)
        s.listen(8)
        s.setblocking(False)
        self.ecoute = s
        self.selecteur.register(s, selectors.EVENT_READ, None)

    def tourner(self, arret: threading.Event) -> None:
        prochain_tic = time.monotonic() + self.periode_tic_s
        while not arret.is_set():
            attente = max(0.0, prochain_tic - time.monotonic())
            for cle, _ in self.selecteur.select(timeout=min(attente, 0.5)):
                if cle.data is None:
                    self._accepter()
                else:
                    self._lire(cle.data)
            if time.monotonic() >= prochain_tic:
                prochain_tic = time.monotonic() + self.periode_tic_s
                self.tic()

    def _accepter(self) -> None:
        assert self.ecoute is not None
        try:
            sock, _ = self.ecoute.accept()
        except OSError:
            return
        sock.settimeout(5.0)  # un envoi bloqué plus de 5 s ferme la connexion (la lecture suit le sélecteur)
        c = Connexion(sock)
        self.connexions[id(c)] = c
        self.selecteur.register(sock, selectors.EVENT_READ, c)

    def _lire(self, c: Connexion) -> None:
        try:
            octets = c.sock.recv(65536)
        except (BlockingIOError, TimeoutError):
            return
        except OSError:
            octets = b""
        if not octets:
            self._fermer(c)
            return
        for ligne in c.lignes(octets):
            try:
                m = protocole.decoder(ligne)
            except protocole.MessageInvalide as e:
                self.invalides += 1
                journal.warning("message ignoré : %s", e)
                continue
            self.quand_message(c, m)

    def _fermer(self, c: Connexion) -> None:
        with contextlib.suppress(KeyError, ValueError):
            self.selecteur.unregister(c.sock)
        self.connexions.pop(id(c), None)
        with c.verrou:
            c.fermee = True
        with contextlib.suppress(OSError):
            c.sock.close()
        self.quand_depart(c)

    def diffuser(self, message: dict[str, Any]) -> None:
        for c in list(self.connexions.values()):
            c.envoyer(message)

    def fermer(self) -> None:
        for c in list(self.connexions.values()):
            self._fermer(c)
        if self.ecoute is not None:
            with contextlib.suppress(KeyError, ValueError):
                self.selecteur.unregister(self.ecoute)
            self.ecoute.close()
            self.ecoute = None
            self.chemin.unlink(missing_ok=True)
        self.selecteur.close()
