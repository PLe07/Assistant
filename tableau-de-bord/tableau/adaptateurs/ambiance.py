"""Ambiance (`com.<session>.ambiance` et `com.<session>.ambiance.audio`).

Ni son code ni son README ne sont dans le dépôt de l'assistant (D-12) : l'adaptateur est générique, avec deux
lectures tolérantes en plus, dans les bases de `~/Library/Application Support/Ambiance/` (copies) :
- un battement, s'il existe une clé `battement` ou `demon_battement` dans une table `meta` ou `etat` ;
- un coût du mois, s'il existe une table de dépenses (`depenses_ia`, `couts`) avec une colonne `cout_usd` (option IA) ;
- la preuve d'une attente du registre, s'il existe une clé `preuve:<id de l'attente>` (date) dans `meta` ou `etat`.
Tout ce qui manque reste « inconnu », sans alarme. C'est aussi l'adaptateur `tolerant`, proposé pour tout futur module
(README : « ajouter un module »).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from tableau.adaptateurs.base import Adaptateur, debut_du_mois, en_nombre, mois_courant, somme_couts, valeur_cle
from tableau.adaptateurs.contexte import Contexte
from tableau.module import Credits, DefModule, Observation
from tableau.sondes.sqlite_copie import colonnes, tables


def lire(mois: str, debut_mois: float) -> Any:
    def lecture(db: sqlite3.Connection) -> dict[str, Any]:
        battements = [
            en_nombre(valeur_cle(db, table, cle))
            for table in ("meta", "etat")
            for cle in ("battement", "demon_battement")
        ]
        couts = [somme_couts(db, table, mois, debut_mois) for table in ("depenses_ia", "couts")]
        connus = [c for c in couts if c is not None]
        return {
            "battement": max((b for b in battements if b), default=None),
            "mois_usd": sum(connus) if connus else None,
            "preuves": _preuves(db),
        }

    return lecture


def _preuves(db: sqlite3.Connection) -> dict[str, float]:
    preuves: dict[str, float] = {}
    for table in ("meta", "etat"):
        if table not in tables(db) or not {"cle", "valeur"} <= colonnes(db, table):
            continue
        for cle, valeur in db.execute(f"SELECT cle, valeur FROM \"{table}\" WHERE cle LIKE 'preuve:%' LIMIT 50"):  # noqa: S608
            quand = en_nombre(valeur)
            if quand is not None:
                ident = str(cle)[len("preuve:") :]
                preuves[ident] = max(quand, preuves.get(ident, 0.0))
    return preuves


class Ambiance(Adaptateur):
    nom = "ambiance"

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        support = ctx.chemin(defn, defn.dossier_donnees)
        if support is None or not support.is_dir():
            return
        resultats = [
            ctx.bases.lire(chemin, "ambiance", lire(mois_courant(ctx), debut_du_mois(ctx)))
            for chemin in sorted(support.glob("*.db"))[:5]
        ]
        lus = [r for r in resultats if r]
        battements = [r["battement"] for r in lus if r.get("battement")]
        if battements:
            obs.battement_ts = max(battements)
            obs.battement_periode_s = 60.0
        for r in lus:
            for ident, quand in (r.get("preuves") or {}).items():
                obs.preuves[ident] = max(quand, obs.preuves.get(ident, 0.0))
        couts = [r["mois_usd"] for r in lus if r.get("mois_usd") is not None]
        if couts or defn.plafond_usd is not None:
            obs.credits = Credits(sum(couts) if couts else None, defn.plafond_usd)
