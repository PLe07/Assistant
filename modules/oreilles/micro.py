"""Le micro (sounddevice). Le son passe par une petite file en mémoire (6 secondes au plus)."""

import queue
import re

import numpy as np

from core.mac import sur_secteur  # noqa: F401 (utilisé par l'écoute)
from modules.oreilles import parametres as p

MICRO_DU_MAC = re.compile(r"macbook|imac|built-in|intégr|integr", re.IGNORECASE)  # « Micro MacBook Air »…


class Micro:
    def __init__(self, appareil=None):
        self.appareil = appareil
        self.file: queue.Queue = queue.Queue(maxsize=200)  # 200 × 32 ms ≈ 6 s
        self.flux = None
        self.nom = "?"  # le micro vraiment utilisé, une fois ouvert

    def _recevoir(self, donnees, images, instant, statut) -> None:
        try:
            self.file.put_nowait(donnees[:, 0].copy())
        except queue.Full:
            pass  # Mac très occupé : on perd un bout de son plutôt que de le stocker

    def __enter__(self):
        import sounddevice as sd

        try:  # relit la liste des micros : l'un a pu être branché, débranché ou changé depuis
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        self.flux = sd.InputStream(samplerate=p.TAUX, channels=1, dtype="float32", blocksize=p.BLOC,
                                   device=self.appareil, callback=self._recevoir)
        self.flux.start()
        self.nom = nom_du_micro(self.appareil)
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


def nom_du_micro(appareil=None) -> str:
    """Le nom d'un micro ; sans appareil, celui que macOS a choisi (Réglages Système → Son → Entrée)."""
    try:
        import sounddevice as sd

        return str(sd.query_devices(appareil, "input")["name"])
    except Exception:
        return "?"


def micro_du_mac() -> str | None:
    """Le micro intégré du Mac (pas celui d'un iPhone ou d'écouteurs), s'il y en a un."""
    try:
        import sounddevice as sd

        return next((str(d["name"]) for d in sd.query_devices()
                     if d["max_input_channels"] > 0 and MICRO_DU_MAC.search(str(d["name"]))), None)
    except Exception:
        return None


def lister_micros() -> list[str]:
    import sounddevice as sd

    defaut = nom_du_micro()
    return [f"{i} : {d['name']}" + ("   ← choisi par macOS (Réglages Système → Son → Entrée)" if d["name"] == defaut else "")
            for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
