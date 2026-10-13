"""Détection de voix et de fin de phrase (§4.2), sur l'audio en mémoire seulement (16 kHz mono, jamais écrit).

- Silero VAD (modèle ONNX du paquet `silero-vad`, lu avec onnxruntime, sans torch), empreinte vérifiée ; WebRTC VAD
  en repli si le modèle manque ou ne se charge pas.
- `FinDePhrase` : attend le début de la parole, puis la fin (500 ms de silence par défaut, réglable), au plus 8 s ;
  garde 300 ms avant le début pour ne pas couper la première syllabe.
"""

from __future__ import annotations

import hashlib
import importlib.util
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

TAUX = 16_000
TRAME = 512  # 32 ms : la taille qu'attend Silero à 16 kHz
TRAME_MS = TRAME * 1000 // TAUX
CONTEXTE = 64
EMPREINTE_SILERO = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"  # silero-vad 6.2.3


class Vad(Protocol):
    nom: str

    def probabilite(self, trame: np.ndarray) -> float: ...

    def reinitialiser(self) -> None: ...


def modele_silero() -> Path | None:
    """Le modèle ONNX livré avec le paquet `silero-vad` (sans l'importer : il demanderait torch)."""
    spec = importlib.util.find_spec("silero_vad")
    if spec is None or not spec.submodule_search_locations:
        return None
    chemin = Path(next(iter(spec.submodule_search_locations))) / "data" / "silero_vad.onnx"
    return chemin if chemin.is_file() else None


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


class ModeleInvalide(Exception):
    pass


class Silero:
    nom = "silero"

    def __init__(self, chemin: Path | None = None, verifier: bool = True) -> None:
        import onnxruntime as ort

        chemin = chemin or modele_silero()
        if chemin is None:
            raise ModeleInvalide("modèle Silero introuvable")
        if verifier and empreinte(chemin) != EMPREINTE_SILERO:
            raise ModeleInvalide("modèle Silero modifié (empreinte différente)")
        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.log_severity_level = 3
        self.session = ort.InferenceSession(str(chemin), options, providers=["CPUExecutionProvider"])
        self.reinitialiser()

    def reinitialiser(self) -> None:
        self.etat = np.zeros((2, 1, 128), dtype=np.float32)
        self.contexte = np.zeros((1, CONTEXTE), dtype=np.float32)

    def probabilite(self, trame: np.ndarray) -> float:
        x = np.concatenate([self.contexte, trame.astype(np.float32).reshape(1, TRAME)], axis=1)
        sortie, self.etat = self.session.run(
            None, {"input": x, "state": self.etat, "sr": np.array(TAUX, dtype=np.int64)}
        )
        self.contexte = x[:, -CONTEXTE:]
        return float(sortie[0][0])


class WebRtc:
    """Le repli : WebRTC VAD (agressivité 2), sur trois tranches de 10 ms de chaque trame de 32 ms."""

    nom = "webrtc"

    def __init__(self, agressivite: int = 2) -> None:
        import webrtcvad

        self.vad = webrtcvad.Vad(agressivite)

    def reinitialiser(self) -> None:
        pass

    def probabilite(self, trame: np.ndarray) -> float:
        pcm = (np.clip(trame, -1.0, 1.0) * 32767).astype("<i2")
        tranches = [pcm[i : i + 160].tobytes() for i in (0, 160, 320)]
        return sum(self.vad.is_speech(t, TAUX) for t in tranches) / 3


def charger(prefere: str = "silero") -> Vad:
    """Silero si possible, sinon WebRTC (le mode dégradé est visible dans `voix doctor`)."""
    if prefere == "silero":
        try:
            return Silero()
        except (ModeleInvalide, ImportError, OSError, RuntimeError):
            pass
    return WebRtc()


def en_flottants(pcm: bytes) -> np.ndarray:
    """PCM 16 bits petit-boutiste → flottants dans [-1, 1]."""
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


@dataclass
class Evenement:
    genre: str  # debut, pause, fin
    raison: str = ""  # silence, duree_max, rien (aucune parole), relache
    instant_s: float = 0.0  # dans le flux, depuis le début de l'écoute


@dataclass
class FinDePhrase:
    """Découpe une écoute : début de parole, puis fin. L'audio reste en mémoire et est oublié avec l'objet."""

    vad: Vad
    silence_fin_ms: int = 500
    duree_max_s: float = 8.0
    attente_max_s: float = 5.0  # appui simple sans parole : on arrête d'écouter
    seuil: float = 0.5
    # Une trame bien plus faible que ta voix (8 dB sous son niveau habituel) compte comme du silence, même si le
    # détecteur y entend des voix : sans ça, le brouhaha d'un café empêcherait de trouver la fin de ta phrase.
    ecart_db: float | None = 8.0
    # Après 200 ms de silence, un événement « pause » : le moteur commence la transcription sans attendre la fin.
    anticipation_ms: int = 200
    debut_ms: int = 96  # parole continue nécessaire pour dire « ça parle »
    avant_ms: int = 300
    trames: list[np.ndarray] = field(default_factory=list)
    _reste: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _avant: deque[np.ndarray] = field(default_factory=deque)
    _niveaux: list[float] = field(default_factory=list)  # l'énergie des trames de parole (dB)
    _suite_parole: int = 0
    _suite_silence: int = 0
    _pause_dite: bool = False
    _n: int = 0
    parle: bool = False
    fini: Evenement | None = None
    debut_parole_s: float | None = None
    fin_parole_s: float | None = None  # fin de la dernière trame de parole
    parole_s: float = 0.0  # durée totale des trames de parole

    def __post_init__(self) -> None:
        self.vad.reinitialiser()
        self._avant = deque(maxlen=max(1, self.avant_ms // TRAME_MS))

    @property
    def secondes(self) -> float:
        return self._n * TRAME / TAUX

    def ajouter(self, echantillons: np.ndarray) -> list[Evenement]:
        """Ajoute de l'audio (flottants 16 kHz) ; renvoie les événements survenus (début, pause, fin)."""
        if self.fini is not None:
            return []
        donnees = np.concatenate([self._reste, echantillons.astype(np.float32)])
        n = len(donnees) // TRAME
        self._reste = donnees[n * TRAME :]
        evenements: list[Evenement] = []
        for i in range(n):
            ev = self._trame(donnees[i * TRAME : (i + 1) * TRAME])
            if ev is not None:
                evenements.append(ev)
                if ev.genre == "fin":
                    break
        return evenements

    def _trame(self, trame: np.ndarray) -> Evenement | None:
        self._n += 1
        p = self.vad.probabilite(trame)
        db = 10 * np.log10(float(np.mean(np.square(trame, dtype=np.float64))) + 1e-12)
        voix = p >= self.seuil
        if voix and self.parle and self.ecart_db is not None and len(self._niveaux) >= 5:
            voix = db >= float(np.percentile(self._niveaux, 80)) - self.ecart_db
        if voix:
            self.parole_s += TRAME / TAUX
            if self.parle:
                self._niveaux.append(db)
        if not self.parle:
            self._avant.append(trame)
            self._suite_parole = self._suite_parole + 1 if voix else 0
            if self._suite_parole * TRAME_MS >= self.debut_ms:
                self.parle = True
                self.trames = list(self._avant)
                self.debut_parole_s = self.secondes - self._suite_parole * TRAME / TAUX
                self.fin_parole_s = self.secondes
                return Evenement("debut", instant_s=self.debut_parole_s)
            if self.secondes >= self.attente_max_s:
                return self._finir("rien")
            return None
        self.trames.append(trame)
        if voix:
            self._suite_silence = 0
            self._pause_dite = False
            self.fin_parole_s = self.secondes
        else:
            self._suite_silence += 1
            if self._suite_silence * TRAME_MS >= self.silence_fin_ms:
                return self._finir("silence")
            if not self._pause_dite and self._suite_silence * TRAME_MS >= self.anticipation_ms:
                self._pause_dite = True
                return Evenement("pause", instant_s=self.secondes)
        if self.debut_parole_s is not None and self.secondes - self.debut_parole_s >= self.duree_max_s:
            return self._finir("duree_max")
        return None

    def relacher(self) -> Evenement:
        """La touche est relâchée (mode « maintenir ») : la phrase s'arrête là."""
        if self.fini is None:
            if len(self._reste):
                self.trames.append(np.pad(self._reste, (0, TRAME - len(self._reste))))
                self._reste = np.zeros(0, dtype=np.float32)
            self._finir("relache" if self.parle else "rien")
        assert self.fini is not None
        return self.fini

    def _finir(self, raison: str) -> Evenement:
        self.fini = Evenement("fin", raison, self.secondes)
        return self.fini

    def audio(self) -> np.ndarray:
        """La phrase (avec 300 ms avant), en mémoire."""
        return np.concatenate(self.trames) if self.trames else np.zeros(0, dtype=np.float32)
