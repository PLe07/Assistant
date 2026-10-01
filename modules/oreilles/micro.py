"""Le micro (sounddevice). Le son passe par une petite file en mémoire (6 secondes au plus)."""

import queue
import subprocess

import numpy as np

from modules.oreilles import parametres as p


class Micro:
    def __init__(self, appareil=None):
        self.appareil = appareil
        self.file: queue.Queue = queue.Queue(maxsize=200)  # 200 × 32 ms ≈ 6 s
        self.flux = None

    def _recevoir(self, donnees, images, instant, statut) -> None:
        try:
            self.file.put_nowait(donnees[:, 0].copy())
        except queue.Full:
            pass  # Mac très occupé : on perd un bout de son plutôt que de le stocker

    def __enter__(self):
        import sounddevice as sd

        self.flux = sd.InputStream(samplerate=p.TAUX, channels=1, dtype="float32", blocksize=p.BLOC,
                                   device=self.appareil, callback=self._recevoir)
        self.flux.start()
        return self

    def lire(self, delai: float = 0.5) -> np.ndarray | None:
        try:
            return self.file.get(timeout=delai)
        except queue.Empty:
            return None

    def __exit__(self, *_):
        if self.flux is not None:
            self.flux.stop()
            self.flux.close()  # le micro est libéré : le point orange de macOS s'éteint
        while not self.file.empty():
            self.file.get_nowait()


def lister_micros() -> list[str]:
    import sounddevice as sd

    return [f"{i} : {d['name']}" for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def sur_secteur() -> bool:
    """True si le Mac est branché (en cas de doute, on considère qu'il l'est)."""
    try:
        sortie = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True
    return "Battery Power" not in sortie
