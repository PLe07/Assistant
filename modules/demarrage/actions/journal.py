"""Le journal des actions : chaque désactivation confirmée y est notée (avant, après, commandes, de quoi annuler).
Il sert à `historique` et à `restaurer`."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from modules.demarrage.db import Base


@dataclass
class Action:
    id: int
    ts: float
    fiche_id: str
    label: str
    genre: str  # launchd, quarantaine, system_events
    avant: dict[str, Any] = field(default_factory=dict)
    apres: dict[str, Any] = field(default_factory=dict)
    commandes: list[list[str]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    annulee: float | None = None


def _json(texte: str | None) -> Any:
    try:
        return json.loads(texte) if texte else None
    except ValueError:
        return None


class Journal:
    def __init__(self, base: Base):
        self.base = base

    def noter(self, a: Action) -> int:
        with self.base.transaction() as db:
            curseur = db.execute(
                "INSERT INTO actions (ts, fiche_id, label, genre, avant, apres, commandes, details)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (a.ts, a.fiche_id, a.label, a.genre, json.dumps(a.avant), json.dumps(a.apres),
                 json.dumps(a.commandes), json.dumps(a.details, ensure_ascii=False)),
            )  # fmt: skip
            a.id = int(curseur.lastrowid or 0)
        return a.id

    def annuler(self, id_: int, quand: float) -> None:
        with self.base.transaction() as db:
            db.execute("UPDATE actions SET annulee = ? WHERE id = ?", (quand, id_))

    def _lire(self, ligne: tuple[Any, ...]) -> Action:
        return Action(
            id=ligne[0], ts=ligne[1], fiche_id=ligne[2], label=ligne[3], genre=ligne[4],
            avant=_json(ligne[5]) or {}, apres=_json(ligne[6]) or {}, commandes=_json(ligne[7]) or [],
            details=_json(ligne[8]) or {}, annulee=ligne[9],
        )  # fmt: skip

    def toutes(self) -> list[Action]:
        colonnes = "id, ts, fiche_id, label, genre, avant, apres, commandes, details, annulee"
        return [self._lire(x) for x in self.base.db.execute(f"SELECT {colonnes} FROM actions ORDER BY ts, id")]

    def a_annuler(self, fiche_id: str) -> Action | None:
        """La dernière action encore en place sur cet élément."""
        actives = [a for a in self.toutes() if a.fiche_id == fiche_id and a.annulee is None]
        return actives[-1] if actives else None
