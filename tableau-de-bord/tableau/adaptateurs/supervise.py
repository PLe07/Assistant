"""Les modules lancés par le superviseur de l'assistant (Corvées, Nettoyeur, Trieur) — D-07.

Ils n'ont pas de LaunchAgent à eux : le superviseur (`com.assistant.superviseur`) les lance en
`python -m modules.<nom>`, les relance s'ils tombent, publie leur statut dans `donnees/etat.db` (table `modules`) et
écrit leurs lignes dans `logs/assistant.log` (`[composant]`). Si un jour ils ont leur propre plist
(`com.<session>.<module>`), on les suit comme n'importe quel LaunchAgent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tableau.adaptateurs.base import Adaptateur, noter_relances
from tableau.adaptateurs.contexte import Contexte
from tableau.caviardage import caviarder
from tableau.module import DefModule, Observation
from tableau.sondes.logs import Ligne


class AdaptateurSupervise(Adaptateur):
    dossier_par_defaut = ""  # sous donnees/ de l'assistant

    def a_son_agent(self, defn: DefModule, ctx: Contexte) -> bool:
        return any(self.plist(ctx, label).exists() for label in defn.labels)

    def est_installe(self, defn: DefModule, ctx: Contexte) -> bool:
        if self.a_son_agent(defn, ctx):
            return True
        racine = ctx.racine_assistant()
        return bool(racine is not None and defn.superviseur and (racine / "modules" / defn.superviseur).is_dir())

    def reglages_module(self, defn: DefModule, ctx: Contexte) -> dict[str, Any]:
        modules = ctx.reglages_assistant().get("modules", {})
        valeur = modules.get(defn.superviseur or "", {}) if isinstance(modules, dict) else {}
        return valeur if isinstance(valeur, dict) else {}

    def dossier_donnees_module(self, defn: DefModule, ctx: Contexte) -> Path | None:
        """Le dossier de données réglé dans l'assistant (`modules.<nom>.dossier`), sinon `donnees/<nom>`."""
        choisi = self.reglages_module(defn, ctx).get("dossier")
        if isinstance(choisi, str) and choisi:
            return Path(choisi).expanduser() if not choisi.startswith("~/") else ctx.chemins.maison / choisi[2:]
        racine = ctx.racine_assistant()
        return racine / "donnees" / (self.dossier_par_defaut or defn.superviseur or defn.id) if racine else None

    def dossiers_donnees(self, defn: DefModule, ctx: Contexte) -> list[Path]:
        d = self.dossier_donnees_module(defn, ctx)
        return [d] if d is not None else []

    def lire_launchd(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        if self.a_son_agent(defn, ctx):
            super().lire_launchd(defn, ctx, obs)
            return
        etat_superviseur = ctx.launchd.etat("com.assistant.superviseur")
        statuts = ctx.statuts_superviseur()
        statut = (statuts or {}).get(defn.superviseur or "")
        actif_reglages = self.reglages_module(defn, ctx).get("actif")
        obs.superviseur = {
            "superviseur_en_marche": None if etat_superviseur is None else bool(etat_superviseur.pid),
            "statut": statut.get("statut") if statut else None,
            "detail": caviarder(str(statut.get("detail") or ""), 200) if statut else "",
            "relances": statut.get("relances") if statut else None,
            "actif_reglages": actif_reglages if isinstance(actif_reglages, bool) else None,
        }
        valeur_statut = str(statut.get("statut") or "") if statut else ""
        if valeur_statut == "désactivé" or (not valeur_statut and actif_reglages is False):
            obs.actif = False
            obs.raison_inactif = (
                f"éteint dans l'assistant (pour l'allumer : python assistant.py activer {defn.superviseur})"
            )
        elif valeur_statut == "en pause":
            obs.actif = False
            detail = str(statut.get("detail") or "") if statut else ""
            obs.raison_inactif = f"en pause ({detail})" if detail else "l'assistant est en pause"
        elif valeur_statut or actif_reglages is True:
            obs.actif = True
        relances = ctx.relances_superviseur(defn.superviseur or "")
        noter_relances(ctx, defn.id, relances)
        obs.relances.extend(relances)

    def pids(self, defn: DefModule, ctx: Contexte, obs: Observation) -> list[int]:
        if self.a_son_agent(defn, ctx):
            return super().pids(defn, ctx, obs)
        return list(ctx.fils_superviseur().get(defn.superviseur or "", []))

    def lignes(self, defn: DefModule, ctx: Contexte) -> list[Ligne]:
        propres = super().lignes(defn, ctx)
        communes = [lg for lg in ctx.lignes_assistant() if lg.composant == defn.superviseur]
        return propres + communes
