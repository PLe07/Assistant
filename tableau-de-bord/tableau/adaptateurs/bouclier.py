"""Bouclier (`com.<session>.bouclier`).

- Journaux : `~/Library/Logs/Bouclier/bouclier.log` (caviardé par Bouclier), `demon.sortie.log`, `demon.erreurs.log`.
- `~/Library/Application Support/Bouclier/bouclier.db` (copie) : `meta.demon_battement` (toutes les 30 s),
  `meta.gmail_releve_le` (la dernière relève Gmail **réussie**, toutes les 5 min par défaut), `meta.gmail_echecs` et
  `meta.gmail_erreur` (pourquoi elle échoue : cité dans l'alerte), dépenses Claude du mois (`depenses_ia`).
- `config.toml` : plafond (`[ia] budget_mensuel_usd`, 2 $), relève Gmail active et son intervalle (`[gmail]`).
- `etat.json` : son interface publique (score d'hygiène, arnaques de la semaine), affichée dans le détail.
- File : `iCloud Drive/Bouclier/entree/` (le raccourci « Arnaque ? »).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from tableau.adaptateurs.base import Adaptateur, debut_du_mois, en_nombre, mois_courant, somme_couts, valeur_cle
from tableau.adaptateurs.contexte import Contexte
from tableau.caviardage import caviarder
from tableau.module import Credits, DefModule, Observation


def lire(mois: str, debut_mois: float) -> Any:
    def lecture(db: sqlite3.Connection) -> dict[str, Any]:
        return {
            "battement": en_nombre(valeur_cle(db, "meta", "demon_battement")),
            "gmail": en_nombre(valeur_cle(db, "meta", "gmail_releve_le")),
            "gmail_echecs": en_nombre(valeur_cle(db, "meta", "gmail_echecs")),
            "gmail_erreur": valeur_cle(db, "meta", "gmail_erreur"),
            "mois_usd": somme_couts(db, "depenses_ia", mois, debut_mois),
        }

    return lecture


class Bouclier(Adaptateur):
    nom = "bouclier"
    battement_periode_s = 30.0

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        support = ctx.chemin(defn, defn.dossier_donnees)
        if support is None:
            obs.inconnus.append("base")
            return
        config = ctx.lire_reglages(support / "config.toml", "toml")
        ia = config.get("ia", {}) if isinstance(config.get("ia"), dict) else {}
        gmail = config.get("gmail", {}) if isinstance(config.get("gmail"), dict) else {}
        plafond = en_nombre(ia.get("budget_mensuel_usd"))
        if gmail.get("active") is False:
            obs.reglages_attentes["gmail"] = {"actif": False}
        elif en_nombre(gmail.get("intervalle_minutes")):
            obs.reglages_attentes["gmail"] = {"toutes_les_min": int(float(gmail["intervalle_minutes"]))}
        etat = ctx.lire_reglages(support / "etat.json")
        if etat:
            obs.technique["etat_public"] = {k: etat.get(k) for k in ("hygiene", "arnaques_7_jours", "comptes", "fuites")
                                            if k in etat}  # fmt: skip
        chemin = support / "bouclier.db"
        donnees = ctx.bases.lire(chemin, "bouclier", lire(mois_courant(ctx), debut_du_mois(ctx)))
        obs.credits = Credits(None, plafond if plafond is not None else defn.plafond_usd)
        if donnees is None:
            obs.inconnus.append("base")
            return
        obs.credits.mois_usd = donnees.get("mois_usd")
        obs.battement_periode_s = self.battement_periode_s
        candidats = [v for v in (donnees.get("battement"), self.battement_par_fichier(chemin)) if v]
        obs.battement_ts = max(candidats) if candidats else None
        if donnees.get("gmail"):
            obs.preuves["gmail"] = donnees["gmail"]
            obs.activite = ("dernière relève Gmail", donnees["gmail"])
        if donnees.get("gmail_echecs"):
            obs.technique["gmail_echecs"] = int(donnees["gmail_echecs"] or 0)
        erreur = donnees.get("gmail_erreur")
        if isinstance(erreur, str) and erreur.strip():
            obs.technique["raison:gmail"] = caviarder(erreur, 160)  # ce que Bouclier dit de sa relève
