# Crédits et licences

| Élément | Licence | Usage dans Voix |
|---|---|---|
| openWakeWord (code), David Scripka | Apache-2.0 | mot d'éveil (option) |
| Modèles préentraînés openWakeWord (`hey_jarvis_v0.1`, `melspectrogram`, `embedding_model`) | CC BY-NC-SA 4.0 (pas d'usage commercial, à cause des données d'entraînement) | **usage personnel seulement** : c'est ton cas ; à ne pas revendre ni intégrer à un produit commercial |
| Silero VAD | MIT | détection de voix |
| WebRTC VAD (`webrtcvad-wheels`) | MIT (bindings) / BSD (WebRTC) | détection de voix de repli |
| Whisper (OpenAI) : poids et code | MIT | transcription locale |
| `mlx-whisper` et conversions `mlx-community/whisper-*` | MIT | Whisper sur Apple Silicon |
| Conversions ONNX `Xenova/whisper-*` | Apache-2.0 (conversion) / MIT (poids) | Whisper portable (onnxruntime) |
| onnxruntime | MIT | exécution des modèles ONNX |
| RapidFuzz | MIT | correspondance approximative |
| tokenizers (Hugging Face) | Apache-2.0 | décodage Whisper ONNX |
| espeak-ng | GPL-3.0 | **construction seulement** (corpus audio du conteneur), jamais installé |
| Voix MBROLA fr1 à fr7 | licence MBROLA (non commerciale) | **construction seulement** (corpus audio du conteneur), jamais installées |
