"""Le temps du tableau de bord : tours réguliers, veille du Mac, redémarrages, échéances locales.

- **Veille** : l'horloge monotone ne compte pas le temps de veille, l'horloge murale si. Entre deux tours, si la
  seconde a avancé bien plus que la première, le Mac dormait : la période est notée dans notre base. Un trou sans
  explication (le tableau de bord était arrêté, ou figé) est noté de la même façon : on n'y a rien vu, donc on n'y
  juge rien.
- **Temps éveillé** : un module qui écrit toutes les 5 minutes n'est pas « en retard » parce que le Mac a dormi la
  nuit : on compte le temps éveillé depuis sa dernière trace.
- **Échéances locales** : « 7h15 » est calculé avec l'heure locale du Mac (`mktime`), changement d'heure compris.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from tableau.db import Base

# Au-delà de cet écart entre horloges (s), c'était une veille ; au-delà de ce trou (s), on n'a pas observé.
ECART_VEILLE_S = 45.0


def echeance_locale(jour_ts: float, hhmm: str, decalage_jours: int = 0) -> float:
    """L'instant de « hh:mm » le jour de `jour_ts` (+ `decalage_jours`), à l'heure locale."""
    h, _, m = hhmm.partition(":")
    t = time.localtime(jour_ts)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday + decalage_jours, int(h), int(m), 0, 0, 0, -1))


def debut_du_jour(ts: float) -> float:
    t = time.localtime(ts)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def noter_veille(base: Base, debut: float, fin: float) -> None:
    if fin > debut:
        base.executer("INSERT OR REPLACE INTO veilles (debut, fin) VALUES (?, ?)", (debut, fin))


def veilles(base: Base, depuis: float, jusqua: float | None = None) -> list[tuple[float, float]]:
    fin = jusqua if jusqua is not None else float("inf")
    return [
        (float(r["debut"]), float(r["fin"]))
        for r in base.lignes(
            "SELECT debut, fin FROM veilles WHERE fin >= ? AND debut <= ? ORDER BY debut", (depuis, fin)
        )
    ]


def temps_eveille(base: Base, debut: float, fin: float) -> float:
    """Secondes entre `debut` et `fin`, sans les veilles (et les trous) notées."""
    if fin <= debut:
        return 0.0
    dormi = 0.0
    for a, b in veilles(base, debut, fin):
        dormi += max(0.0, min(b, fin) - max(a, debut))
    return max(0.0, fin - debut - dormi)


def dernier_reveil(base: Base) -> float | None:
    v = base.valeur("SELECT MAX(fin) FROM veilles")
    return float(v) if v is not None else None


@dataclass
class Tour:
    maintenant: float
    reveil: float | None  # fin de la veille (ou du trou) constatée à ce tour, sinon None


class Horloge:
    """Les deux horloges, et la mémoire du tour précédent (dans notre base, pour survivre à un redémarrage)."""

    def __init__(
        self,
        base: Base,
        mur: Callable[[], float] = time.time,
        mono: Callable[[], float] = time.monotonic,
        intervalle_s: float = 60.0,
    ) -> None:
        self.base = base
        self.mur = mur
        self.mono = mono
        self.intervalle_s = intervalle_s
        self._mur_avant: float | None = None
        self._mono_avant: float | None = None

    def tour(self) -> Tour:
        mur, mono = self.mur(), self.mono()
        reveil: float | None = None
        if self._mur_avant is None:
            # Premier tour depuis le démarrage : le temps passé arrêté n'a pas été observé.
            precedent = self.base.lire_meta("dernier_tour")
            if precedent is not None and mur - float(precedent) > 2 * self.intervalle_s + ECART_VEILLE_S:
                noter_veille(self.base, float(precedent), mur)
                reveil = mur
        elif self._mono_avant is not None:
            ecart_mur = mur - self._mur_avant
            ecart_mono = mono - self._mono_avant
            trou = ecart_mur > 3 * self.intervalle_s + ECART_VEILLE_S
            if ecart_mur - ecart_mono > ECART_VEILLE_S or trou:
                noter_veille(self.base, self._mur_avant, mur)
                reveil = mur
        self._mur_avant, self._mono_avant = mur, mono
        self.base.ecrire_meta("dernier_tour", str(mur))
        return Tour(mur, reveil)


class Echeancier:
    """Des tâches à intervalle fixe (découverte, intégrité, tailles, instantané), dues au premier tour."""

    def __init__(self) -> None:
        self._dernier: dict[str, float] = {}

    def du(self, nom: str, intervalle_s: float, maintenant: float) -> bool:
        dernier = self._dernier.get(nom)
        if dernier is None or maintenant - dernier >= intervalle_s or maintenant < dernier:
            self._dernier[nom] = maintenant
            return True
        return False

    def forcer(self, nom: str) -> None:
        self._dernier.pop(nom, None)
