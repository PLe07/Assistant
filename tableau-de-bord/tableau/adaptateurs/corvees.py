"""Corvées (`modules/corvees`, sous le superviseur de l'assistant ; éteint au départ).

Lu dans la copie de `donnees/corvees/corvees.db` : le battement (`etat.battement`, chaque minute), la dernière
analyse (`etat.derniere_analyse`, vers 21 h chaque jour, reportée si la batterie est faible ou le Mac en veille), la
pause éventuelle (`etat.pause`) et les dépenses Claude du mois (`couts`). Plafond : `modules.corvees.ia.
budget_mensuel_usd` (2 $ par défaut). L'heure de l'analyse se lit dans `modules.corvees.analyse.heure`.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from tableau.adaptateurs.base import debut_du_mois, en_nombre, mois_courant, somme_couts, valeur_cle
from tableau.adaptateurs.contexte import Contexte
from tableau.adaptateurs.supervise import AdaptateurSupervise
from tableau.module import Credits, DefModule, Observation


def lire(mois: str, debut_mois: float) -> Any:
    def lecture(db: sqlite3.Connection) -> dict[str, Any]:
        return {
            "battement": en_nombre(valeur_cle(db, "etat", "battement")),
            "derniere_analyse": en_nombre(valeur_cle(db, "etat", "derniere_analyse")),
            "pause": valeur_cle(db, "etat", "pause"),
            "mois_usd": somme_couts(db, "couts", mois, debut_mois),
        }

    return lecture


class Corvees(AdaptateurSupervise):
    nom = "corvees"
    battement_periode_s = 60.0

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        reglages = self.reglages_module(defn, ctx)
        ia = reglages.get("ia", {})
        plafond = en_nombre(ia.get("budget_mensuel_usd")) if isinstance(ia, dict) else None
        analyse = reglages.get("analyse", {})
        if isinstance(analyse, dict) and isinstance(analyse.get("heure"), str):
            obs.reglages_attentes["analyse"] = {"heure": analyse["heure"]}
        dossier = self.dossier_donnees_module(defn, ctx)
        chemin = dossier / "corvees.db" if dossier else None
        donnees = ctx.bases.lire(chemin, "corvees", lire(mois_courant(ctx), debut_du_mois(ctx))) if chemin else None
        obs.credits = Credits(None, plafond if plafond is not None else defn.plafond_usd)
        if donnees is None:
            obs.inconnus.append("base")
            return
        obs.credits.mois_usd = donnees.get("mois_usd")
        obs.battement_periode_s = self.battement_periode_s
        candidats = [v for v in (donnees.get("battement"), self.battement_par_fichier(chemin)) if v]
        obs.battement_ts = max(candidats) if candidats else None
        if donnees.get("derniere_analyse"):
            obs.preuves["analyse"] = donnees["derniere_analyse"]
            obs.activite = ("dernière analyse", donnees["derniere_analyse"])
        pause = donnees.get("pause")
        if pause:
            jusqua = en_nombre(pause.get("jusqua")) if isinstance(pause, dict) else en_nombre(pause)
            if jusqua is None or jusqua > ctx.maintenant:
                obs.actif = False
                quand = time.strftime("%d/%m à %H:%M", time.localtime(jusqua)) if jusqua else None
                obs.raison_inactif = (
                    f"en pause jusqu'au {quand}" if quand else "en pause (corvees resume pour rallumer)"
                )
