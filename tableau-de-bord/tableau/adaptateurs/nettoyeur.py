"""Le Nettoyeur de démarrage (`modules/demarrage`, sous le superviseur ; surveillance éteinte au départ).

Lu dans la copie de `donnees/demarrage/demarrage.db` : le battement (`etat.battement`), le dernier relevé (`releves`,
toutes les 2 minutes) et le dernier scan (`scans`, chaque jour). Il n'utilise pas Claude : pas de crédits.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from tableau.adaptateurs.base import en_nombre, valeur_cle
from tableau.adaptateurs.contexte import Contexte
from tableau.adaptateurs.supervise import AdaptateurSupervise
from tableau.module import DefModule, Observation
from tableau.sondes.sqlite_copie import colonnes, tables


def _max(db: sqlite3.Connection, table: str) -> float | None:
    if table in tables(db) and "ts" in colonnes(db, table):
        return en_nombre(db.execute(f'SELECT MAX(ts) FROM "{table}"').fetchone()[0])
    return None


def lire(db: sqlite3.Connection) -> dict[str, Any]:
    return {
        "battement": en_nombre(valeur_cle(db, "etat", "battement")),
        "releve": _max(db, "releves"),
        "scan": _max(db, "scans"),
    }


class Nettoyeur(AdaptateurSupervise):
    nom = "nettoyeur"
    dossier_par_defaut = "demarrage"
    battement_periode_s = 60.0

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        dossier = self.dossier_donnees_module(defn, ctx)
        chemin = dossier / "demarrage.db" if dossier else None
        donnees = ctx.bases.lire(chemin, "nettoyeur", lire) if chemin else None
        if donnees is None:
            obs.inconnus.append("base")
            return
        obs.battement_periode_s = self.battement_periode_s
        candidats = [v for v in (donnees.get("battement"), self.battement_par_fichier(chemin)) if v]
        obs.battement_ts = max(candidats) if candidats else None
        if donnees.get("releve"):
            obs.preuves["releve"] = donnees["releve"]
        if donnees.get("scan"):
            obs.preuves["scan"] = donnees["scan"]
            obs.activite = ("dernier inventaire du démarrage", donnees["scan"])
