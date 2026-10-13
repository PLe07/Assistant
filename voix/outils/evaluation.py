"""Mesurer la compréhension sur un corpus de phrases (§9.1).

- intention exacte : la bonne intention (ou le refus attendu) ;
- paramètres exacts : parmi les intentions justes, les paramètres attendus tous identiques (objet par identifiant,
  textes libres sans casse ni accents, nombres et durées exacts) ;
- hors catalogue : « pas compris » (ou rien d'exploitable), jamais une intention ;
- sensibles : chaque phrase d'une intention sensible est reconnue comme sensible (donc confirmée avant d'agir).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from outils.corpus_phrases import Cas
from voix.nlu.approx import forme_normale
from voix.nlu.comprendre import Comprehension, Contexte, comprendre
from voix.nlu.intentions import SENSIBLES


@dataclass
class Bilan:
    n: int = 0
    intentions_justes: int = 0
    params_justes: int = 0
    hors_catalogue: int = 0
    hors_catalogue_justes: int = 0  # « pas compris » (ou rien d'exploitable)
    sensibles: int = 0
    sensibles_confirmees: int = 0
    echecs_intention: list[tuple[str, str, str]] = field(default_factory=list)
    echecs_params: list[tuple[str, dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    actions_hors_catalogue: list[tuple[str, str]] = field(default_factory=list)  # compris ou ambigu : une action
    autres_hors_catalogue: list[tuple[str, str]] = field(default_factory=list)  # refus, négation : aucune action

    @property
    def taux_intention(self) -> float:
        return self.intentions_justes / self.n if self.n else 1.0

    @property
    def taux_params(self) -> float:
        return self.params_justes / self.intentions_justes if self.intentions_justes else 1.0

    def resume(self) -> str:
        return (
            f"{self.n} phrases : intention exacte {100 * self.taux_intention:.1f} %, paramètres exacts "
            f"{100 * self.taux_params:.1f} % ; hors catalogue {self.hors_catalogue_justes}/{self.hors_catalogue} "
            f"« pas compris » ({len(self.actions_hors_catalogue)} action, {len(self.autres_hors_catalogue)} refus ou "
            f"négation) ; sensibles confirmées "
            f"{self.sensibles_confirmees}/{self.sensibles}"
        )


def _valeur(v: Any) -> Any:
    if hasattr(v, "ident"):
        return v.ident
    if isinstance(v, str):
        return forme_normale(v)
    return v


def params_identiques(attendus: dict[str, Any], obtenus: dict[str, Any]) -> bool:
    for k, v in attendus.items():
        if k not in obtenus:
            return False
        if k == "objet":
            if getattr(obtenus[k], "ident", obtenus[k]) != v:
                return False
        elif _valeur(obtenus[k]) != _valeur(v):
            return False
    return True


def resume_comprehension(c: Comprehension) -> str:
    return f"{c.statut}:{c.intention or ''}"


def evaluer(cas: Iterable[Cas], ctx: Contexte) -> Bilan:
    b = Bilan()
    for un in cas:
        c = comprendre(un.phrase, ctx)
        if un.intention is None:
            b.hors_catalogue += 1
            if c.statut in ("pas_compris", "vide"):
                b.hors_catalogue_justes += 1
            elif c.statut in ("compris", "ambigu"):
                b.actions_hors_catalogue.append((un.phrase, resume_comprehension(c)))
            else:
                b.autres_hors_catalogue.append((un.phrase, resume_comprehension(c)))
            continue
        b.n += 1
        if un.intention in SENSIBLES:
            b.sensibles += 1
            if c.statut == "compris" and c.sensible:
                b.sensibles_confirmees += 1
        juste = (
            (c.statut == "refus") if un.statut == "refus" else (c.statut == "compris" and c.intention == un.intention)
        )
        if not juste:
            b.echecs_intention.append((un.phrase, un.intention, resume_comprehension(c)))
            continue
        b.intentions_justes += 1
        if params_identiques(un.params, c.params):
            b.params_justes += 1
        else:
            b.echecs_params.append((un.phrase, un.params, {k: _valeur(v) for k, v in c.params.items()}))
    return b
