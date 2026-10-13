"""La transcription locale par Whisper (§4.2), derrière une interface commune à tous les moteurs.

- Sur ton Mac (Apple Silicon) : `mlx-whisper`, modèle `small` (ou `base` si la latence dépasse l'objectif), poids
  téléchargés à l'installation depuis Hugging Face et vérifiés par leur empreinte SHA-256 (`EMPREINTES.json`).
- Langue forcée en français, une invite initiale avec le vocabulaire des commandes et tes noms (apps, dossiers, alias),
  une seule passe à température 0 (pas de nouvelles tentatives qui inventent), sans horodatage.
- Le modèle est chargé à la demande et gardé « au chaud » quelques minutes (`[modeles] garder_au_chaud_min`), puis
  libéré : au repos, la mémoire redescend.
- Modèle absent ou corrompu : `charger` rend None avec la raison ; le moteur passe à Apple Speech (repli) et
  `voix doctor` le dit.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from voix.nlu.catalogue import Catalogue

TAUX = 16_000
MODELES_MLX = {"small": "mlx-community/whisper-small-mlx", "base": "mlx-community/whisper-base-mlx"}
INVITE_BASE = (
    "Commandes vocales en français : ouvre Safari, ferme Notion, mets le volume à 30 %, monte le son, coupe le son, "
    "cherche la facture, va sur YouTube, lance un minuteur de 10 minutes, rappelle-moi dans 20 minutes, mode sombre, "
    "active la concentration, verrouille l'écran, annule."
)
INVITE_MAX = 600  # caractères : Whisper ne lit que 224 jetons d'invite


@dataclass(frozen=True)
class Transcription:
    texte: str
    duree_s: float  # temps de calcul
    sans_parole: float = 0.0  # probabilité « pas de parole » estimée par Whisper
    logprob: float = 0.0  # vraisemblance moyenne des jetons


class Transcripteur(Protocol):
    nom: str

    def transcrire(self, audio: np.ndarray, invite: str = "") -> Transcription: ...

    def liberer(self, maintenant: float | None = None) -> bool: ...


class ModeleIndisponible(Exception):
    pass


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 22), b""):
            h.update(bloc)
    return h.hexdigest()


def verifier_modele(dossier: Path, complet: bool = False) -> str | None:
    """None si le modèle est intact, sinon la raison. `EMPREINTES.json` : {fichier: {"sha256": …, "taille": …}},
    écrit à l'installation d'après Hugging Face. `complet` recalcule chaque empreinte (lent : à l'installation et
    dans `voix doctor`) ; sinon on compare les tailles."""
    try:
        attendu = json.loads((dossier / "EMPREINTES.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "modèle absent (pas d'EMPREINTES.json)"
    if not isinstance(attendu, dict) or not attendu:
        return "EMPREINTES.json illisible"
    for nom, infos in attendu.items():
        if not isinstance(infos, dict) or "/" in nom or nom.startswith("."):
            return f"entrée invalide : {nom}"
        f = dossier / nom
        if not f.is_file():
            return f"fichier manquant : {nom}"
        if f.stat().st_size != infos.get("taille"):
            return f"taille inattendue : {nom}"
        if complet and empreinte(f) != infos.get("sha256"):
            return f"empreinte différente : {nom}"
    return None


def invite(catalogue: Catalogue | None) -> str:
    """L'invite initiale : la manière de parler aux commandes, puis tes noms (apps d'abord)."""
    if catalogue is None:
        return INVITE_BASE
    ordre = {"app": 0, "alias": 1, "routine": 2, "playlist": 3, "dossier": 4, "raccourci": 5}
    noms = [o.nom for o in sorted(catalogue.objets, key=lambda o: ordre.get(o.genre, 9)) if o.genre in ordre]
    texte = INVITE_BASE
    for nom in dict.fromkeys(n.removesuffix(" (dossier)") for n in noms):
        if len(texte) + len(nom) + 2 > INVITE_MAX:
            break
        texte += (" Noms : " if texte == INVITE_BASE else ", ") + nom
    return texte


def apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


class WhisperMlx:
    """mlx-whisper : le décodeur appelé directement sur un seul morceau (≤ 30 s), sans la boucle de `transcribe`."""

    nom = "whisper"

    def __init__(self, dossier: Path, garder_s: float = 300.0, horloge: Callable[[], float] = time.monotonic) -> None:
        self.dossier = dossier
        self.garder_s = garder_s
        self.horloge = horloge
        self._modele: Any = None
        self._dernier = 0.0
        self._verrou = threading.Lock()

    def _charger(self) -> Any:
        if self._modele is None:
            import mlx.core as mx
            from mlx_whisper.load_models import load_model

            self._modele = load_model(str(self.dossier), dtype=mx.float16)
        return self._modele

    def transcrire(self, audio: np.ndarray, invite: str = "") -> Transcription:
        from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim
        from mlx_whisper.decoding import DecodingOptions, decode

        with self._verrou:
            debut = self.horloge()
            modele = self._charger()
            mel = log_mel_spectrogram(audio.astype(np.float32), n_mels=modele.dims.n_mels, padding=N_SAMPLES)
            mel = pad_or_trim(mel[:N_FRAMES], N_FRAMES, axis=-2)
            options = DecodingOptions(
                task="transcribe", language="fr", temperature=0.0, without_timestamps=True, fp16=True,
                prompt=invite or None, sample_len=96,
            )  # fmt: skip
            r = decode(modele, mel, options)
            self._dernier = self.horloge()
            return Transcription(
                str(r.text).strip(), self._dernier - debut, float(r.no_speech_prob), float(r.avg_logprob)
            )

    def liberer(self, maintenant: float | None = None) -> bool:
        """Libère le modèle s'il n'a pas servi depuis `garder_s` (appelé chaque seconde) ; True s'il est libéré."""
        with self._verrou:
            if self._modele is None:
                return False
            t = self.horloge() if maintenant is None else maintenant
            if t - self._dernier < self.garder_s:
                return False
            self._modele = None
            return True

    @property
    def charge(self) -> bool:
        return self._modele is not None


def mlx_installe() -> bool:
    return importlib.util.find_spec("mlx_whisper") is not None and importlib.util.find_spec("mlx") is not None


@dataclass(frozen=True)
class Choix:
    transcripteur: Transcripteur | None
    raison: str  # pourquoi ce moteur, ou pourquoi aucun


def charger(modeles: Path, taille: str = "small", backend: str = "auto", garder_min: float = 5.0) -> Choix:
    """Le Whisper local disponible, ou None avec la raison (le moteur passe alors à Apple Speech)."""
    if taille == "auto":
        taille = "small"
    if backend not in ("auto", "mlx"):
        return Choix(None, f"moteur Whisper « {backend} » non disponible (mlx seulement)")
    if not apple_silicon():
        return Choix(None, "mlx-whisper demande un Mac Apple Silicon")
    if not mlx_installe():
        return Choix(None, "mlx-whisper n'est pas installé")
    dossier = modeles / f"whisper-{taille}-mlx"
    raison = verifier_modele(dossier)
    if raison is not None:
        return Choix(None, raison)
    return Choix(WhisperMlx(dossier, garder_s=garder_min * 60), f"Whisper {taille} (mlx)")
