"""L'assistant lui-même : son superviseur (`com.assistant.superviseur`), son icône (`com.assistant.icone`), son
module de tri Gmail (`modules/mails`) et ses appels à Claude.

- Journal : les lignes de `logs/assistant.log` qui n'appartiennent pas à un autre module du registre (superviseur,
  tri des mails, battement, notifications…).
- `donnees/etat.db` (copie) : le battement du superviseur (`cles.superviseur_vivant`, toutes les 2 s), le statut de
  chaque module (`modules`) et les appels à Claude (`appels_claude` : modèle et jetons). L'assistant passe par
  l'abonnement Claude Code : son coût est un **équivalent API** estimé (jetons × tarif public).
- `donnees/mails/memoire.db` (copie) : la date du dernier mail trié. Le tri n'écrit rien quand il n'a rien à trier :
  pas d'attente « toutes les 3 min » (elle donnerait de fausses alertes), seulement son statut dans le superviseur.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from tableau.adaptateurs.base import Adaptateur, debut_du_mois, en_nombre
from tableau.adaptateurs.contexte import Contexte
from tableau.analyse import credits as credits_
from tableau.module import Credits, DefModule, Observation
from tableau.sondes.logs import Ligne
from tableau.sondes.sqlite_copie import colonnes, tables

# Sous `donnees/` : téléchargés une fois, de taille fixe (traduction ~1,4 Go, transcription) : pas des données qui
# gonflent (D-59).
MODELES_TELECHARGES = ("traduction/modele", "traduction/nllb", "oreilles/modeles")


def lire_appels(debut_mois: float, debut_jour: float) -> Any:
    def lecture(db: sqlite3.Connection) -> dict[str, Any]:
        if "appels_claude" not in tables(db):
            return {}
        cols = colonnes(db, "appels_claude")
        if not {"quand", "modele", "tokens_entree", "tokens_sortie"} <= cols:
            return {}
        ok = "AND ok = 1" if "ok" in cols else ""
        jetons = {
            str(m or "inconnu"): (int(e or 0), int(s or 0))
            for m, e, s in db.execute(
                f"SELECT modele, SUM(tokens_entree), SUM(tokens_sortie) FROM appels_claude WHERE quand >= ? {ok} "
                "GROUP BY modele",
                (debut_mois,),
            )
        }
        jour = int(db.execute(f"SELECT COUNT(*) FROM appels_claude WHERE quand >= ? {ok}", (debut_jour,)).fetchone()[0])
        return {"jetons": jetons, "appels_jour": jour}

    return lecture


def lire_mails(db: sqlite3.Connection) -> float | None:
    if "mails" not in tables(db) or "traite_le" not in colonnes(db, "mails"):
        return None
    brut = db.execute("SELECT MAX(traite_le) FROM mails").fetchone()[0]
    if not brut:
        return None
    try:
        return datetime.fromisoformat(str(brut)).timestamp()
    except ValueError:
        return None


class Assistant(Adaptateur):
    nom = "assistant"
    battement_periode_s = 60.0  # le superviseur écrit toutes les 2 s ; on le lit au plus chaque minute

    def est_installe(self, defn: DefModule, ctx: Contexte) -> bool:
        if super().est_installe(defn, ctx):
            return True
        racine = ctx.racine_assistant()
        return bool(racine is not None and (racine / "modules" / "mails").is_dir())

    def lignes(self, defn: DefModule, ctx: Contexte) -> list[Ligne]:
        pris = ctx.composants_pris()
        return super().lignes(defn, ctx) + [lg for lg in ctx.lignes_assistant() if lg.composant not in pris]

    def dossiers_donnees(self, defn: DefModule, ctx: Contexte) -> list:
        racine = ctx.racine_assistant()
        return [racine / "donnees"] if racine else []

    def dossiers_exclus(self, defn: DefModule, ctx: Contexte) -> list[Path]:
        """Les modèles téléchargés une fois (taille fixe), et les données des modules qu'il supervise (comptées
        chez eux)."""
        from tableau.adaptateurs import obtenir  # ici : le registre des adaptateurs importe celui-ci

        racine = ctx.racine_assistant()
        if racine is None:
            return []
        exclus = [racine / "donnees" / modele for modele in MODELES_TELECHARGES]
        for autre in ctx.modules:
            if autre.id != defn.id and autre.superviseur:
                exclus += obtenir(autre.adaptateur).dossiers_donnees(autre, ctx)
        return exclus

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        racine = ctx.racine_assistant()
        if racine is None:
            obs.inconnus.append("base")
            return
        statuts = ctx.statuts_superviseur()
        reglages = ctx.reglages_assistant()
        modules = reglages.get("modules", {}) if isinstance(reglages.get("modules"), dict) else {}
        mails = modules.get("mails", {}) if isinstance(modules.get("mails"), dict) else {}
        if statuts is None:
            obs.inconnus.append("statuts du superviseur")
        else:
            vivant = en_nombre((statuts.get("__superviseur__") or {}).get("vivant"))
            fichier = self.battement_par_fichier(racine / "donnees" / "etat.db")
            candidats = [v for v in (vivant, fichier) if v]
            obs.battement_ts = max(candidats) if candidats else None
            obs.battement_periode_s = self.battement_periode_s
            obs.superviseur = {
                "modules": {
                    nom: {"statut": s.get("statut"), "relances": s.get("relances")}
                    for nom, s in statuts.items()
                    if nom != "__superviseur__"
                },
                "tri_gmail_actif": mails.get("actif") if isinstance(mails.get("actif"), bool) else None,
            }
        t = time.localtime(ctx.maintenant)
        debut_jour = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
        appels = ctx.bases.lire(racine / "donnees" / "etat.db", "appels", lire_appels(debut_du_mois(ctx), debut_jour))
        claude = reglages.get("claude", {}) if isinstance(reglages.get("claude"), dict) else {}
        maximum = claude.get("appels_max_par_jour")
        if appels:
            cout, inconnus = credits_.estimer(appels.get("jetons", {}))
            detail = f"{appels.get('appels_jour', 0)} appel(s) aujourd'hui"
            if isinstance(maximum, int):
                detail += f" sur {maximum} permis"
            obs.credits = Credits(cout, defn.plafond_usd, source="estimation", detail=detail)
            obs.technique["jetons_du_mois"] = appels.get("jetons", {})
            if inconnus:
                obs.technique["modeles_au_tarif_inconnu"] = inconnus
        dernier_mail = ctx.bases.lire(racine / "donnees" / "mails" / "memoire.db", "mails", lire_mails)
        if dernier_mail:
            obs.activite = ("dernier mail trié", dernier_mail)
