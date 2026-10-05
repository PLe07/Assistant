"""Ce que tous les détecteurs partagent : le candidat, et le flux d'événements découpé en sessions."""

from __future__ import annotations

import base64
import hashlib
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from modules.corvees.db import Evenement
from modules.corvees.normalize import jour_de, jour_semaine

# Ces événements ne sont pas des actions : ils ne font partie d'aucune corvée.
NON_ACTIONS = ("inactif", "fen")


@dataclass
class Candidat:
    type: str  # sequence, routine, fichiers, pont, shell
    tokens: tuple[str, ...]
    occurrences: int
    jours: int  # jours distincts
    debuts: list[float]  # début de chaque occurrence
    durees: list[float]  # durée mesurée de chaque occurrence (secondes, 0 si inconnue)
    regularite: float = 0.0  # 0 à 1 : la part des jours (ou semaines) attendus où elle a eu lieu
    lift: float = 0.0  # combien de fois plus souvent qu'au hasard
    details: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    minutes_mois: float = 0.0
    frequence_mois: float = 0.0
    duree_s: float = 0.0

    @property
    def signature(self) -> str:
        """Stable d'une analyse à l'autre : ne dépend que du type et des étapes."""
        return hashlib.sha1(f"{self.type}|{'|'.join(self.tokens)}".encode()).hexdigest()

    @property
    def id(self) -> str:
        brut = hashlib.sha1(self.signature.encode()).digest()
        return base64.b32encode(brut).decode()[:6].lower()

    def exporter(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "signature": self.signature,
            "type": self.type,
            "tokens": list(self.tokens),
            "occurrences": self.occurrences,
            "jours_distincts": self.jours,
            "duree_moyenne_s": round(self.duree_s, 1),
            "regularite": round(self.regularite, 2),
            "lift": round(self.lift, 1),
            "frequence_mois": round(self.frequence_mois, 1),
            "minutes_mois": round(self.minutes_mois, 1),
            "score": round(self.score, 2),
            "premiere": min(self.debuts) if self.debuts else None,
            "derniere": max(self.debuts) if self.debuts else None,
            "details": self.details,
        }


def mediane(valeurs: list[float]) -> float:
    return float(statistics.median(valeurs)) if valeurs else 0.0


@dataclass
class Session:
    ids: list[int]
    ts: list[float]
    jour: str


@dataclass
class Flux:
    evenements: list[Evenement]
    vocab: list[str]
    sessions: list[Session]
    debut: float
    fin: float
    jours_actifs: set[str]
    compte: Counter[int]

    @property
    def jours_observes(self) -> int:
        """Combien de jours couvre l'observation (au moins 1)."""
        return max(1, round((self.fin - self.debut) / 86400))

    def jours_semaine_actifs(self) -> Counter[int]:
        return Counter(jour_semaine(_midi(j)) for j in self.jours_actifs)


def _midi(jour: str) -> float:
    from datetime import date, datetime

    from modules.corvees.normalize import ZONE

    d = date.fromisoformat(jour)
    return datetime(d.year, d.month, d.day, 12, tzinfo=ZONE).timestamp()


def preparer(
    evenements: list[Evenement], inactivite_min: float, debut: float | None = None, fin: float | None = None
) -> Flux:
    """Trie, numérote les tokens, découpe en sessions (pause de plus de N minutes, inactivité, minuit) et enlève les
    répétitions immédiates (deux fois de suite la même appli, c'est une seule action)."""
    evts = sorted(evenements, key=lambda e: e.ts)
    vocab: list[str] = []
    index: dict[str, int] = {}
    sessions: list[Session] = []
    actuelle: Session | None = None
    dernier_ts = None
    jours_actifs: set[str] = set()
    compte: Counter[int] = Counter()
    pause = inactivite_min * 60
    for e in evts:
        jour = jour_de(e.ts)
        jours_actifs.add(jour)
        coupure = e.kind == "inactif" or actuelle is None or jour != actuelle.jour
        if dernier_ts is not None and e.ts - dernier_ts > pause:
            coupure = True
        dernier_ts = e.ts
        if coupure:
            actuelle = None
        if e.kind in NON_ACTIONS:
            continue
        if actuelle is None:
            actuelle = Session([], [], jour)
            sessions.append(actuelle)
        if e.token not in index:
            index[e.token] = len(vocab)
            vocab.append(e.token)
        t = index[e.token]
        if actuelle.ids and actuelle.ids[-1] == t:
            continue
        actuelle.ids.append(t)
        actuelle.ts.append(e.ts)
        compte[t] += 1
    debut = debut if debut is not None else (evts[0].ts if evts else 0.0)
    fin = fin if fin is not None else (evts[-1].ts if evts else 0.0)
    return Flux(evts, vocab, [s for s in sessions if s.ids], debut, fin, jours_actifs, compte)
