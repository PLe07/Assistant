"""Découpe le flux du micro en phrases, en mémoire uniquement.

Une phrase commence quand le son dépasse nettement le bruit de fond, et se termine
après un court silence. Le son est rendu phrase par phrase puis oublié :
rien n'est conservé au-delà de la phrase en cours (15 secondes au maximum).
"""

from collections import deque

import numpy as np


class Decoupeur:
    def __init__(self, taux: int = 16000, bloc: int = 512, silence_fin: float = 0.8,
                 duree_max: float = 15.0, duree_min: float = 0.5, marge: float = 3.0, avant: float = 0.3):
        self.taux, self.marge = taux, marge
        self.silence_fin = int(silence_fin * taux)
        self.max = int(duree_max * taux)
        self.min = int(duree_min * taux)
        self.bruit: float | None = None  # niveau du bruit de fond, appris en continu
        self.avant = deque(maxlen=max(1, int(avant * taux / bloc)))  # le tout début du mot
        self.phrase: list[np.ndarray] = []
        self.taille = 0
        self.silence = 0

    def _parle(self, rms: float) -> bool:
        if self.bruit is None:
            self.bruit = rms
        return rms > max(self.bruit * self.marge, 0.003)

    def ajouter(self, bloc: np.ndarray) -> np.ndarray | None:
        """Ajoute 32 ms de son. Renvoie une phrase complète quand elle se termine, sinon None."""
        rms = float(np.sqrt(np.mean(np.square(bloc)))) if len(bloc) else 0.0
        parle = self._parle(rms)
        if not self.phrase:
            if parle:
                self.phrase = [*self.avant, bloc]
                self.taille = sum(len(b) for b in self.phrase)
                self.silence = 0
                self.avant.clear()
            else:
                self.bruit = 0.95 * self.bruit + 0.05 * rms
                self.avant.append(bloc)
            return None
        self.phrase.append(bloc)
        self.taille += len(bloc)
        self.silence = 0 if parle else self.silence + len(bloc)
        if self.silence >= self.silence_fin or self.taille >= self.max:
            utile = self.taille - self.silence
            audio = np.concatenate(self.phrase)
            self.vider()
            return audio if utile >= self.min else None  # trop court : un clic, une toux
        return None

    def vider(self) -> None:
        """Oublie tout le son en cours."""
        self.phrase, self.taille, self.silence = [], 0, 0
        self.avant.clear()
