"""Quotidien (`com.<session>.quotidien`).

- Journaux : `~/Library/Logs/Quotidien/quotidien.log` (caviardé), `demon.sortie.log`, `demon.erreurs.log`.
- `~/Library/Application Support/Quotidien/quotidien.db` (copie) : `meta.demon_battement` (toutes les 30 s), les
  tâches faites (`taches` : nom, échéance, faite_le — dont le brief du matin), les dépenses Claude (`depenses_ia`).
- `reglages.toml` : l'heure du brief (`[heures] brief`, 7h15 par défaut) et le plafond (`[ia] budget_mensuel_usd`).
- `brief.json` : la date du dernier brief parti.
- File : `iCloud Drive/Quotidien/entree/` (raccourcis « Mon frigo » et « Envie de… »).
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
        taches: dict[str, float] = {}
        if "taches" in tables(db) and {"nom", "faite_le"} <= colonnes(db, "taches"):
            for nom, quand in db.execute("SELECT nom, MAX(faite_le) FROM taches GROUP BY nom"):
                if en_nombre(quand):
                    taches[str(nom)] = float(quand)
        return {
            "battement": en_nombre(valeur_cle(db, "meta", "demon_battement")),
            "taches": taches,
            "mois_usd": somme_couts(db, "depenses_ia", mois, debut_mois),
        }

    return lecture


class Quotidien(Adaptateur):
    nom = "quotidien"
    battement_periode_s = 30.0

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        support = ctx.chemin(defn, defn.dossier_donnees)
        if support is None:
            obs.inconnus.append("base")
            return
        reglages = ctx.lire_reglages(support / "reglages.toml", "toml")
        heures = reglages.get("heures", {}) if isinstance(reglages.get("heures"), dict) else {}
        if isinstance(heures.get("brief"), str):
            obs.reglages_attentes["brief"] = {"heure": heures["brief"]}
        ia = reglages.get("ia", {}) if isinstance(reglages.get("ia"), dict) else {}
        plafond = en_nombre(ia.get("budget_mensuel_usd"))
        chemin = support / "quotidien.db"
        donnees = ctx.bases.lire(chemin, "quotidien", lire(mois_courant(ctx), debut_du_mois(ctx)))
        obs.credits = Credits(None, plafond if plafond is not None else defn.plafond_usd)
        if donnees is None:
            obs.inconnus.append("base")
            return
        obs.credits.mois_usd = donnees.get("mois_usd")
        obs.battement_periode_s = self.battement_periode_s
        candidats = [v for v in (donnees.get("battement"), self.battement_par_fichier(chemin)) if v]
        obs.battement_ts = max(candidats) if candidats else None
        taches = donnees.get("taches", {})
        for nom, quand in taches.items():
            obs.preuves[nom] = quand
        if "brief" in taches:
            obs.activite = ("dernier brief parti", taches["brief"])
        obs.technique["taches"] = sorted(taches)
