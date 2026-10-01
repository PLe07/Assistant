"""Transcription locale (faster-whisper) : le son ne quitte jamais le Mac."""

import numpy as np

from modules.oreilles import parametres as p

# Phrases que le modèle « invente » parfois sur du bruit (sous-titres de vidéos d'entraînement).
HALLUCINATIONS = (
    "sous-titrage", "sous-titres réalisés", "amara.org", "merci d'avoir regardé",
    "abonnez-vous", "st' 501", "merci de votre attention", "sous-titres par",
)


class Transcripteur:
    def __init__(self, modele: str = "small"):
        self.nom = modele
        self.modele = None

    def charger(self) -> None:
        """Charge le modèle (le télécharge la toute première fois, environ 460 Mo pour « small »)."""
        if self.modele is None:
            from faster_whisper import WhisperModel

            p.MODELES.mkdir(parents=True, exist_ok=True)
            self.modele = WhisperModel(self.nom, device="cpu", compute_type="int8", download_root=str(p.MODELES))

    @staticmethod
    def contient_de_la_voix(audio: np.ndarray) -> bool:
        """Détecteur de voix local (Silero) : évite de transcrire un bruit de clavier ou de la musique."""
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        return bool(get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=300)))

    def transcrire(self, audio: np.ndarray) -> str:
        if not self.contient_de_la_voix(audio):
            return ""
        self.charger()
        segments, _ = self.modele.transcribe(
            audio, language="fr", beam_size=1, vad_filter=True,
            condition_on_previous_text=False, without_timestamps=True,
        )
        texte = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()
        if any(h in texte.lower() for h in HALLUCINATIONS):
            return ""
        return texte
