"""Le démon du moteur (`voix demon`, lancé par le LaunchAgent `com.<toi>.voix`).

- Un seul moteur à la fois (verrou), un socket Unix privé, un travailleur unique pour la compréhension et les
  actions, un tic chaque seconde (minuteurs, confirmation expirée, modèle libéré après quelques minutes).
- Transcription : Whisper local si le modèle est là et intact, sinon Apple Speech (dans l'app) ; la raison est
  écrite dans `etat.json` pour `voix doctor`.
- Journal technique dans `~/Library/Logs/Voix/moteur.log` (1 Mo × 2) : des états, jamais d'audio ni de phrase.
- Arrêt propre sur SIGTERM ; launchd le relance s'il tombe.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import logging.handlers
import os
import signal
import socket
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from voix import VERSION, config, demarrage, protocole
from voix.audio import vad as vad_mod
from voix.audio import whisper_local
from voix.audio.whisper_local import Transcripteur
from voix.journal import Journal
from voix.moteur import Moteur
from voix.session import Session
from voix.socket_serveur import Connexion, PontSocket, Serveur, Travailleur

journal = logging.getLogger("voix.demon")


def prendre_verrou(fichier: Path) -> IO[str] | None:
    fichier.parent.mkdir(parents=True, exist_ok=True)
    f = fichier.open("a+", encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def configurer_journal(dossier: Path) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    os.chmod(dossier, 0o700)
    racine = logging.getLogger("voix")
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in racine.handlers):
        return
    h = logging.handlers.RotatingFileHandler(dossier / "moteur.log", maxBytes=1_000_000, backupCount=2,
                                             encoding="utf-8")  # fmt: skip
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    racine.addHandler(h)
    racine.setLevel(logging.INFO)


def choisir_transcription(chemins: config.Chemins, reglages: config.Reglages) -> tuple[Transcripteur | None, str]:
    """(Whisper local ou None pour Apple Speech, la raison en clair)."""
    if reglages.moteur() == "apple":
        return None, "Apple Speech (choisi dans les réglages ou par le banc d'essai)"
    modele, backend = reglages.whisper()
    choix = whisper_local.charger(chemins.modeles, modele, backend, float(reglages["modeles"]["garder_au_chaud_min"]))
    if choix.transcripteur is None:
        return None, f"Apple Speech (Whisper indisponible : {choix.raison})"
    return choix.transcripteur, choix.raison


def ecrire_etat(fichier: Path, etat: dict[str, Any]) -> None:
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=fichier.parent, prefix=".etat.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, fichier)


def lancer(
    chemins: config.Chemins | None = None,
    reglages: config.Reglages | None = None,
    arret: threading.Event | None = None,
    transcription: tuple[Transcripteur | None, str] | None = None,
    vad: Callable[[], vad_mod.Vad] | None = None,
    pret: Callable[[Moteur], None] | None = None,
    outils: Callable[[config.Chemins, config.Reglages, PontSocket], Any] | None = None,
) -> int:
    chemins = chemins or config.chemins_par_defaut()
    reglages = reglages or config.charger(chemins)
    chemins.preparer()
    verrou = prendre_verrou(chemins.verrou)
    if verrou is None:
        print("Un moteur Voix tourne déjà.")
        return 1
    configurer_journal(chemins.logs)
    arret = arret or threading.Event()
    pont = PontSocket()
    o = (outils or demarrage.outils)(chemins, reglages, pont)
    j = reglages["journal"]
    session = Session(o, Journal(chemins.journal, bool(j["actif"]), int(j["taille"])))
    transcripteur, raison = transcription or choisir_transcription(chemins, reglages)
    travailleur = Travailleur()
    connexions: dict[str, Connexion | None] = {"app": None}
    serveur: Serveur | None = None

    def diffuser(m: dict[str, Any]) -> None:
        if serveur is not None:
            serveur.diffuser(m)

    moteur = Moteur(session, diffuser, vad or vad_mod.charger, transcripteur,
                    "whisper" if transcripteur is not None else "apple")  # fmt: skip
    debut = time.time()
    tics = [0]

    def etat() -> dict[str, Any]:
        latence = moteur.mesures.latence_moyenne()
        return {
            "version": VERSION, "pid": os.getpid(), "depuis": int(debut), "transcription": moteur.mode_transcription,
            "raison": raison, "vad": moteur.nom_vad,
            "app_connectee": connexions["app"] is not None, "latence_moyenne_ms": latence,
            "modele_charge": bool(getattr(transcripteur, "charge", False)), "rejets": moteur.mesures.rejets,
            "erreurs": travailleur.erreurs, "messages_ignores": serveur.invalides if serveur else 0,
        }  # fmt: skip

    def tic() -> None:
        travailleur.soumettre(moteur.tic)
        tics[0] += 1
        if tics[0] % 60 == 0:
            travailleur.soumettre(lambda: ecrire_etat(chemins.etat, etat()))

    def quand_message(c: Connexion, m: dict[str, Any]) -> None:
        if m["type"] == "pont":
            pont.recevoir(m)  # tout de suite : le travailleur attend peut-être cette réponse
            return
        if m["type"] == "bonjour":
            c.client = str(m.get("client") or "?")[:20]
            if c.client == "app":
                connexions["app"] = c
                pont.envoyer = c.envoyer
                journal.info("app connectée")
            travailleur.soumettre(lambda: c.envoyer(moteur.bonjour()))
            return
        travailleur.soumettre(lambda: moteur.recevoir(m))

    def quand_depart(c: Connexion) -> None:
        if connexions["app"] is c:
            connexions["app"] = None
            pont.envoyer = None
            journal.info("app déconnectée")
            travailleur.soumettre(moteur.annuler_ecoute)

    serveur = Serveur(chemins.socket, quand_message, quand_depart, tic)
    try:
        serveur.demarrer()
    except Exception as e:  # noqa: BLE001 - un autre moteur, un fichier inattendu : on le dit et on s'arrête
        print(f"Le moteur ne peut pas démarrer : {e}")
        verrou.close()
        return 1
    travailleur.demarrer()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: arret.set())
    journal.info("moteur démarré (%s)", raison)
    ecrire_etat(chemins.etat, etat())
    if pret is not None:
        pret(moteur)
    try:
        serveur.tourner(arret)
    finally:
        serveur.fermer()
        travailleur.arreter()
        ecrire_etat(chemins.etat, {**etat(), "arrete": int(time.time())})
        journal.info("moteur arrêté")
        verrou.close()
    return 0


def dire(texte: str, chemin: Path, delai_s: float = 15.0) -> dict[str, Any] | None:
    """`voix dire "phrase"` : envoie une phrase tapée au moteur et rend sa réponse (None s'il ne tourne pas)."""
    ref = f"cli{os.getpid()}"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(delai_s)
    try:
        s.connect(str(chemin))
    except OSError:
        s.close()
        return None
    with contextlib.closing(s):
        s.sendall(protocole.encoder({"type": "texte", "texte": texte, "source": "clavier", "ref": ref}))
        tampon = b""
        fin = time.monotonic() + delai_s
        while time.monotonic() < fin:
            try:
                octets = s.recv(65536)
            except TimeoutError:
                break
            if not octets:
                break
            tampon += octets
            *lignes, tampon = tampon.split(b"\n")
            for ligne in lignes:
                with contextlib.suppress(ValueError):
                    m = json.loads(ligne)
                    if isinstance(m, dict) and m.get("type") == "reponse" and m.get("ref") == ref:
                        return m
    return {"type": "reponse", "statut": "erreur", "texte": "Le moteur n'a pas répondu à temps."}
