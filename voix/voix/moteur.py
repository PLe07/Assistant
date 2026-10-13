"""Le moteur : une écoute (l'audio de l'app) → fin de phrase → transcription → filtre → compréhension → réponse.

- La fin de phrase vient du détecteur de voix (500 ms de silence, 8 s au plus) ou de la touche relâchée.
- Dès 200 ms de silence, la transcription commence en avance ; si tu reprends la parole, elle est jetée. À la fin,
  il ne reste souvent presque rien à attendre.
- Mode Apple : l'app transcrit elle-même (Apple Speech sur l'appareil) ; le moteur lui dit quand la phrase est finie.
- L'audio n'existe qu'en mémoire, le temps d'une écoute ; il n'est jamais écrit.
- Les gros calculs (transcription, actions) passent par `en_fond` : un seul travailleur, dans l'ordre d'arrivée.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from voix import VERSION
from voix.actions.base import Reponse
from voix.audio import anti_hallucination
from voix.audio.vad import FinDePhrase, Vad, en_flottants
from voix.audio.whisper_local import Transcripteur, Transcription, invite
from voix.session import Session

SANS_PAROLE_MAX = 0.6  # Whisper : « pas de parole » au-delà, avec une vraisemblance faible → rejeté
LOGPROB_MIN = -1.0
ECOUTE_MUETTE_S = 10.0  # une écoute sans audio depuis 10 s est abandonnée (app partie, micro coupé…)
Envoyer = Callable[[dict[str, Any]], None]


def immediat(travail: Callable[[], None]) -> None:
    travail()


@dataclass
class Ecoute:
    ident: int
    mode: str
    fin: FinDePhrase
    debut: float
    dernier_audio: float
    anticipee: tuple[float, Transcription] | None = None  # (fin de la parole quand elle a été lancée, résultat)
    fin_vue: float = 0.0  # l'heure où la fin de phrase a été décidée
    terminee: bool = False
    attend_texte: bool = False  # mode Apple : on attend la transcription de l'app


@dataclass
class Mesures:
    latences_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    transcriptions_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    rejets: int = 0
    anticipees_utiles: int = 0

    def latence_moyenne(self) -> float | None:
        return sum(self.latences_ms) / len(self.latences_ms) if self.latences_ms else None


class Moteur:
    def __init__(
        self,
        session: Session,
        envoyer: Envoyer,
        vad: Callable[[], Vad],
        transcripteur: Transcripteur | None = None,
        mode_transcription: str = "whisper",
        en_fond: Callable[[Callable[[], None]], None] = immediat,
        horloge: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = session
        self.envoyer = envoyer
        self.vad_fabrique = vad
        self._vad: Vad | None = None
        self.transcripteur = transcripteur
        self.mode_transcription = mode_transcription if transcripteur is not None else "apple"
        self.en_fond = en_fond
        self.horloge = horloge
        self.ecoute: Ecoute | None = None
        self.mesures = Mesures()
        self.invite = invite(session.o.catalogue)
        r = session.o.reglages
        self.silence_fin_ms = int(r["ecoute"]["silence_fin_ms"])
        self.duree_max_s = float(r["ecoute"]["duree_max_s"])

    @property
    def nom_vad(self) -> str:
        return self._vad.nom if self._vad is not None else "pas encore chargé"

    @property
    def vad(self) -> Vad:
        if self._vad is None:
            self._vad = self.vad_fabrique()
        return self._vad

    # --- messages de l'app -----------------------------------------------------------------------------------------

    def bonjour(self) -> dict[str, Any]:
        noms = [o.nom.removesuffix(" (dossier)") for o in self.session.o.catalogue.objets
                if o.genre in ("app", "alias", "dossier", "routine", "playlist", "raccourci")]  # fmt: skip
        return {"type": "bonjour", "moteur": VERSION, "transcription": self.mode_transcription,
                "vocabulaire": list(dict.fromkeys(noms))[:300]}  # fmt: skip

    def recevoir(self, m: dict[str, Any]) -> None:
        """Un message déjà vérifié par `protocole.decoder`."""
        genre = m["type"]
        if genre == "bonjour":
            self.envoyer(self.bonjour())
        elif genre == "ecoute":
            self._ecoute(m)
        elif genre == "audio":
            self._audio(m["id"], en_flottants(m["octets"]))
        elif genre == "texte":
            self._texte(m)

    def _ecoute(self, m: dict[str, Any]) -> None:
        e = self.ecoute
        if m["etat"] == "debut":
            if e is not None and not e.terminee:
                e.terminee = True  # une nouvelle écoute remplace l'ancienne
            fin = FinDePhrase(self.vad, silence_fin_ms=self.silence_fin_ms, duree_max_s=self.duree_max_s)
            maintenant = self.horloge()
            self.ecoute = Ecoute(m["id"], m.get("mode", "appui"), fin, maintenant, maintenant)
            self.envoyer({"type": "etat", "etat": "ecoute", "id": m["id"]})
            return
        if e is None or e.ident != m["id"] or e.terminee:
            return
        if m["etat"] == "annule":
            e.terminee = True
            self.envoyer({"type": "etat", "etat": "repos", "id": e.ident})
        elif m["etat"] == "relache" and e.fin.fini is None:
            self._fin(e, e.fin.relacher().raison)

    def _audio(self, ident: int, echantillons: np.ndarray) -> None:
        e = self.ecoute
        if e is None or e.ident != ident or e.terminee or e.fin.fini is not None:
            return
        e.dernier_audio = self.horloge()
        for ev in e.fin.ajouter(echantillons):
            if ev.genre == "pause" and self.mode_transcription == "whisper":
                self._anticiper(e)
            elif ev.genre == "fin":
                self._fin(e, ev.raison)

    def _texte(self, m: dict[str, Any]) -> None:
        if m["source"] == "apple":
            e = self.ecoute
            if e is None or e.ident != m["id"] or not e.attend_texte:
                return
            e.attend_texte = False
            parole_s = e.fin.parole_s
            self.en_fond(lambda: self._comprendre(e.ident, m["texte"], parole_s, e))
            return
        texte, ref = m["texte"], m.get("ref")
        self.en_fond(lambda: self._repondre(None, self.session.entendre(texte), texte, ref))

    # --- la fin d'une phrase ---------------------------------------------------------------------------------------

    def _anticiper(self, e: Ecoute) -> None:
        if self.transcripteur is None:
            return
        audio = e.fin.audio().copy()
        fin_parole = e.fin.fin_parole_s or 0.0
        transcripteur = self.transcripteur

        def travail() -> None:
            if not e.terminee:
                e.anticipee = (fin_parole, transcripteur.transcrire(audio, self.invite))

        self.en_fond(travail)

    def _fin(self, e: Ecoute, raison: str) -> None:
        e.fin_vue = self.horloge()
        self.envoyer({"type": "micro", "ouvert": False, "id": e.ident, "raison": raison})
        if raison == "rien" or e.fin.parole_s < anti_hallucination.PAROLE_MIN_S:
            e.terminee = True
            self._repondre(e.ident, Reponse("rien", ""))
            return
        self.envoyer({"type": "etat", "etat": "reflexion", "id": e.ident})
        if self.mode_transcription == "apple":
            e.attend_texte = True
            self.envoyer({"type": "transcrire", "id": e.ident})
            return
        self.en_fond(lambda: self._transcrire(e))

    def _transcrire(self, e: Ecoute) -> None:
        assert self.transcripteur is not None
        if e.terminee:
            return
        fin_parole = e.fin.fin_parole_s or 0.0
        if e.anticipee is not None and e.anticipee[0] == fin_parole:
            t = e.anticipee[1]
            self.mesures.anticipees_utiles += 1
        else:
            t = self.transcripteur.transcrire(e.fin.audio(), self.invite)
        self.mesures.transcriptions_ms.append(t.duree_s * 1000)
        if t.sans_parole > SANS_PAROLE_MAX and t.logprob < LOGPROB_MIN:
            self._rejet(e)
            return
        self._comprendre(e.ident, t.texte, e.fin.parole_s, e)

    def _rejet(self, e: Ecoute) -> None:
        self.mesures.rejets += 1
        e.terminee = True
        self._repondre(e.ident, Reponse("rien", "Je n'ai rien entendu."))

    def _comprendre(self, ident: int, texte: str, parole_s: float, e: Ecoute) -> None:
        verdict = anti_hallucination.filtrer(texte, parole_s)
        if verdict.texte is None:
            self._rejet(e)
            return
        r = self.session.entendre(verdict.texte)
        e.terminee = True
        if e.fin.fini is not None and e.fin.fin_parole_s is not None:
            attente_s = e.fin.fini.instant_s - e.fin.fin_parole_s  # le silence qu'il a fallu attendre
            self.mesures.latences_ms.append((attente_s + self.horloge() - e.fin_vue) * 1000)
        self._repondre(ident, r, verdict.texte)

    def _repondre(self, ident: int | None, r: Reponse, entendu: str = "", ref: str | None = None) -> None:
        self.envoyer({
            "type": "reponse", "id": ident, "ref": ref, "statut": r.statut, "texte": r.texte, "intention": r.intention,
            "entendu": entendu, "suggestions": r.donnees.get("suggestions", []), "choix": r.donnees.get("choix", []),
            "parler": self.session.etat.parler,
        })  # fmt: skip
        self.envoyer({"type": "etat", "etat": "repos", "id": ident})

    def annuler_ecoute(self) -> None:
        """L'app est partie en pleine écoute : l'écoute est abandonnée (et son audio oublié)."""
        if self.ecoute is not None and not self.ecoute.terminee:
            self.ecoute.terminee = True
        self.ecoute = None

    # --- chaque seconde --------------------------------------------------------------------------------------------

    def tic(self) -> None:
        for r in self.session.tic():
            self._repondre(None, r)
        e = self.ecoute
        if e is not None and not e.terminee and e.fin.fini is None:
            if self.horloge() - e.dernier_audio > ECOUTE_MUETTE_S:
                e.terminee = True
                self.envoyer({"type": "etat", "etat": "repos", "id": e.ident})
        if self.transcripteur is not None:
            self.transcripteur.liberer()
