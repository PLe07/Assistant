"""Le moteur, de l'audio à l'action, sur le faux Mac : fin de phrase, transcription anticipée, filtre, compréhension,
confirmation, mode Apple, minuteurs. Le détecteur de voix suit un script ; la transcription est simulée."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pytest

from tests.faux_mac import FauxMac
from tests.unitaires.test_audio import VadScript
from voix import protocole
from voix.audio.vad import TRAME
from voix.audio.whisper_local import Transcription
from voix.moteur import ECOUTE_MUETTE_S, Moteur
from voix.session import Session


class FauxWhisper:
    nom = "faux"

    def __init__(self, texte: str = "ouvre Notion", sans_parole: float = 0.0, logprob: float = -0.1) -> None:
        self.texte, self.sans_parole, self.logprob = texte, sans_parole, logprob
        self.appels: list[int] = []
        self.liberations = 0

    def transcrire(self, audio: np.ndarray, invite: str = "") -> Transcription:
        assert "Notion" in invite  # tes noms sont dans l'invite
        self.appels.append(len(audio))
        return Transcription(self.texte, 0.25, self.sans_parole, self.logprob)

    def liberer(self, maintenant: float | None = None) -> bool:
        self.liberations += 1
        return False


class Banc:
    def __init__(self, mac: FauxMac, script: list[float], transcripteur: FauxWhisper | None) -> None:
        self.t = [1000.0]
        self.envois: list[dict[str, Any]] = []
        self.mac = mac
        self.vad = VadScript(script)
        o = mac.outils(maintenant=lambda: datetime(2026, 10, 13, 9, 0) + timedelta(seconds=self.t[0] - 1000))
        self.session = Session(o, horloge=lambda: self.t[0])
        self.moteur = Moteur(self.session, self.envois.append, lambda: self.vad, transcripteur,
                             horloge=lambda: self.t[0])  # fmt: skip

    def message(self, **m: Any) -> None:
        self.moteur.recevoir(protocole.decoder(protocole.encoder(m)))

    def parler(self, ident: int, n_trames: int, mode: str = "appui", debut: bool = True) -> None:
        if debut:
            self.message(type="ecoute", etat="debut", id=ident, mode=mode)
        pcm = (np.ones(n_trames * TRAME) * 3000).astype("<i2").tobytes()
        for i in range(0, len(pcm), 3200):  # des morceaux de 100 ms, comme l'app
            self.t[0] += 0.1
            self.message(type="audio", id=ident, pcm=base64.b64encode(pcm[i : i + 3200]).decode())

    def types(self) -> list[str]:
        return [f"{m['type']}:{m.get('etat') or m.get('raison') or m.get('statut')}" for m in self.envois]

    def reponses(self) -> list[dict[str, Any]]:
        return [m for m in self.envois if m["type"] == "reponse"]


PHRASE = [0.0] * 5 + [1.0] * 25 + [0.0] * 30  # 160 ms de rien, 800 ms de parole, puis le silence


def test_une_ecoute_complete_avec_transcription_anticipee(mac: FauxMac) -> None:
    w = FauxWhisper()
    b = Banc(mac, PHRASE, w)
    b.parler(1, len(PHRASE))
    assert b.types() == ["etat:ecoute", "micro:silence", "etat:reflexion", "reponse:fait", "etat:repos"]
    r = b.reponses()[0]
    assert r["texte"] == "✓ Notion ouvert" and r["entendu"] == "ouvre Notion" and r["id"] == 1
    assert mac.appels() == [("open", ["-b", "notion.id"])]
    assert len(w.appels) == 1 and b.moteur.mesures.anticipees_utiles == 1  # la transcription faite pendant la pause
    assert b.moteur.mesures.latence_moyenne() is not None and b.moteur.mesures.latence_moyenne() < 700
    assert b.envois[1] == {"type": "micro", "ouvert": False, "id": 1, "raison": "silence"}


def test_reprise_apres_une_pause_la_transcription_anticipee_est_refaite(mac: FauxMac) -> None:
    w = FauxWhisper()
    script = [1.0] * 15 + [0.0] * 8 + [1.0] * 15 + [0.0] * 20
    b = Banc(mac, script, w)
    b.parler(2, len(script))
    assert len(w.appels) == 2 and w.appels[1] > w.appels[0]  # la seconde porte sur toute la phrase
    assert b.moteur.mesures.anticipees_utiles == 1 and b.reponses()[0]["statut"] == "fait"


def test_touche_relachee_annulee_et_sans_parole(mac: FauxMac) -> None:
    w = FauxWhisper("monte le son")
    b = Banc(mac, [1.0] * 40, w)
    b.parler(3, 20, mode="maintien")
    b.message(type="ecoute", etat="relache", id=3)
    assert "micro:relache" in b.types() and b.reponses()[0]["statut"] == "fait"
    b.envois.clear()
    b.parler(4, 10)
    b.message(type="ecoute", etat="annule", id=4)
    b.message(type="ecoute", etat="relache", id=4)  # déjà annulée : rien
    assert b.types() == ["etat:ecoute", "etat:repos"]
    b.envois.clear()
    b.vad.script = [0.0] * 400
    b.parler(5, 10, mode="maintien")
    b.message(type="ecoute", etat="relache", id=5)
    assert b.types() == ["etat:ecoute", "micro:rien", "reponse:rien", "etat:repos"]
    assert len(w.appels) == 1  # pas de parole : Whisper n'est même pas appelé


@pytest.mark.parametrize(
    ("texte", "sans_parole", "logprob"),
    [("Sous-titres réalisés par la communauté d'Amara.org", 0.0, -0.1), ("ouvre Notion", 0.9, -1.5),
     ("ferme ferme ferme ferme tout", 0.0, -0.1)],
)  # fmt: skip
def test_hallucinations_jamais_executees(mac: FauxMac, texte: str, sans_parole: float, logprob: float) -> None:
    b = Banc(mac, PHRASE, FauxWhisper(texte, sans_parole, logprob))
    b.parler(6, len(PHRASE))
    assert b.reponses()[0]["statut"] == "rien" and b.reponses()[0]["texte"] == "Je n'ai rien entendu."
    assert mac.appels() == [] and mac.pont.ordres == [] and b.moteur.mesures.rejets == 1


def test_mode_apple_le_moteur_attend_la_transcription_de_l_app(mac: FauxMac) -> None:
    b = Banc(mac, PHRASE, None)
    assert b.moteur.mode_transcription == "apple" and b.moteur.bonjour()["transcription"] == "apple"
    b.parler(7, len(PHRASE))
    assert b.types()[-1] == "transcrire:None" and b.envois[-1]["id"] == 7
    b.message(type="texte", texte="ouvre Notion", source="apple", id=99)  # une autre écoute : ignoré
    assert b.reponses() == []
    b.message(type="texte", texte="ouvre Notion", source="apple", id=7)
    b.message(type="texte", texte="ouvre Notion", source="apple", id=7)  # en double : ignoré
    assert [r["statut"] for r in b.reponses()] == ["fait"] and mac.appels() == [("open", ["-b", "notion.id"])]


def test_confirmation_a_la_voix(mac: FauxMac) -> None:
    w = FauxWhisper("ferme toutes les applications")
    b = Banc(mac, PHRASE, w)
    b.parler(8, len(PHRASE))
    assert b.reponses()[-1]["statut"] == "question" and mac.pont.ordres == []
    w.texte = "oui"
    b.parler(9, len(PHRASE))
    assert b.reponses()[-1]["statut"] == "fait" and mac.pont.ordres[0][0] == "app.quitter_tout"


def test_phrase_tapee_ou_cliquee_et_bonjour(mac: FauxMac) -> None:
    b = Banc(mac, PHRASE, FauxWhisper())
    b.message(type="texte", texte="ouvre YouTube", source="clavier", ref="cli1")
    r = b.reponses()[0]
    assert r["ref"] == "cli1" and r["statut"] == "fait" and r["id"] is None
    b.message(type="bonjour", client="app")
    bonjour = b.envois[-1]
    assert bonjour["transcription"] == "whisper" and "Notion" in bonjour["vocabulaire"]
    assert "Musique" in bonjour["vocabulaire"] and not any("(dossier)" in v for v in bonjour["vocabulaire"])


def test_audio_hors_ecoute_ignore_et_nouvelle_ecoute(mac: FauxMac) -> None:
    w = FauxWhisper()
    b = Banc(mac, PHRASE, w)
    b.parler(10, 5, debut=False)  # aucune écoute en cours
    assert b.envois == []
    b.parler(11, 10)
    b.parler(12, len(PHRASE))  # une nouvelle écoute remplace la précédente
    b.parler(11, 40, debut=False)  # l'ancienne ne reçoit plus rien
    assert [r["id"] for r in b.reponses()] == [12]


def test_tic_minuteur_ecoute_muette_et_modele_libere(mac: FauxMac) -> None:
    w = FauxWhisper("lance un minuteur de 1 minute")
    b = Banc(mac, PHRASE, w)
    b.parler(13, len(PHRASE))
    assert b.reponses()[-1]["statut"] == "fait"
    b.envois.clear()
    b.parler(14, 3)
    b.t[0] += ECOUTE_MUETTE_S + 1
    b.moteur.tic()
    assert "etat:repos" in b.types() and w.liberations == 1
    b.envois.clear()
    b.t[0] += 60
    b.moteur.tic()
    assert [r["statut"] for r in b.reponses()] == ["alerte"]
    b.moteur.annuler_ecoute()
    assert b.moteur.ecoute is None and b.moteur.nom_vad == "script"
