"""Le Trieur (`modules/trieur`, sous le superviseur de l'assistant).

Lu dans la copie de `donnees/trieur/trieur.db` : les documents en attente (`elements.etat` = en_attente ou en_cours,
avec leur heure d'arrivée `ajoute`), les dépenses Claude du mois (`depenses_ia`), le dernier document classé. Plafond :
`modules.trieur.ia.budget_mensuel_usd` dans `reglages.json` (1 $ par défaut, README du Trieur). Files : la boîte iCloud
`BoiteMac/` et les dossiers « À trier ».
"""

from __future__ import annotations

import sqlite3
from typing import Any

from tableau.adaptateurs.base import debut_du_mois, en_nombre, mois_courant, retenir_activite, somme_couts
from tableau.adaptateurs.contexte import Contexte
from tableau.adaptateurs.supervise import AdaptateurSupervise
from tableau.module import Credits, DefModule, FileAttente, Observation
from tableau.sondes.sqlite_copie import colonnes, tables

LIBELLES = {
    "facture_achat": "dernière facture classée",
    "facture_service": "dernière facture classée",
    "ticket_caisse": "dernier ticket classé",
    "releve_bancaire": "dernier relevé classé",
    "bulletin_paie": "dernière fiche de paie classée",
}


def lire(mois: str, debut_mois: float) -> Any:
    def lecture(db: sqlite3.Connection) -> dict[str, Any]:
        r: dict[str, Any] = {"mois_usd": somme_couts(db, "depenses_ia", mois, debut_mois)}
        if "elements" in tables(db):
            cols = colonnes(db, "elements")
            if {"etat", "ajoute"} <= cols:
                n, plus_ancien = db.execute(
                    "SELECT COUNT(*), MIN(ajoute) FROM elements WHERE etat IN ('en_attente', 'en_cours')"
                ).fetchone()
                r["attente"] = (int(n), en_nombre(plus_ancien))
            if "etat" in cols:
                r["etats"] = {
                    str(e): int(n) for e, n in db.execute("SELECT etat, COUNT(*) FROM elements GROUP BY etat")
                }
            if {"etat", "traite", "type"} <= cols:
                d = db.execute(
                    "SELECT type, traite FROM elements WHERE etat = 'classe' AND traite IS NOT NULL "
                    "ORDER BY traite DESC LIMIT 1"
                ).fetchone()
                r["dernier"] = (str(d[0] or ""), en_nombre(d[1])) if d else None
        return r

    return lecture


class Trieur(AdaptateurSupervise):
    nom = "trieur"

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        dossier = self.dossier_donnees_module(defn, ctx)
        if dossier is None:
            obs.inconnus.append("base")
            return
        donnees = ctx.bases.lire(dossier / "trieur.db", "trieur", lire(mois_courant(ctx), debut_du_mois(ctx)))
        ia = self.reglages_module(defn, ctx).get("ia", {})
        plafond = en_nombre(ia.get("budget_mensuel_usd")) if isinstance(ia, dict) else None
        if donnees is None:
            obs.inconnus.append("base")
            obs.credits = Credits(None, plafond if plafond is not None else defn.plafond_usd)
            return
        obs.credits = Credits(donnees.get("mois_usd"), plafond if plafond is not None else defn.plafond_usd)
        attente = donnees.get("attente")
        if attente is not None:
            n, plus_ancien = attente
            age = max(0.0, ctx.maintenant - plus_ancien) if n and plus_ancien else 0.0
            obs.files.append(FileAttente("documents en attente de classement", n, age, seuil_min=defn.file_max_min))
        else:
            obs.inconnus.append("file du Trieur")
        dernier = donnees.get("dernier")
        if dernier and dernier[1]:
            retenir_activite(ctx, defn.id, LIBELLES.get(dernier[0], "dernier document classé"), dernier[1])
            obs.activite = (LIBELLES.get(dernier[0], "dernier document classé"), dernier[1])
        obs.technique["documents"] = donnees.get("etats", {})
