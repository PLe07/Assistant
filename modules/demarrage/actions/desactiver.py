"""`demarrage desactiver ID` : d'abord un plan, établi en lisant l'état actuel (rien n'est modifié) ; puis, seulement
avec `--confirmer`, son exécution, sa vérification et son inscription au journal.

- Agent de ta session (S1, S4, chargé par launchd) : `launchctl bootout` puis `launchctl disable`, plist gardé.
- Orphelin dans ~/Library/LaunchAgents : `bootout` s'il est chargé, puis le plist part en quarantaine.
- Élément d'ouverture de session : retiré par System Events si l'autorisation existe, sinon le chemin des Réglages.
- Global (/Library, daemons, assistants privilégiés), extension système, cron : des instructions, rien d'exécuté.
- 🍎 Apple, ou l'Assistant lui-même : refus.
- ⚠️ Inconnu : seulement de quoi le vérifier.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.demarrage.actions import instructions, quarantaine
from modules.demarrage.actions.journal import Action, Journal
from modules.demarrage.analyse import Element
from modules.demarrage.collecteurs.launchd_etat import analyser_desactives
from modules.demarrage.systeme import Systeme

# Les seules commandes qu'une simulation a le droit de lancer : elles ne font que lire.
LECTURE = {
    "launchctl": {"list", "print", "print-disabled", "blame"},
    "ps": None, "top": None, "pmset": {"-g"}, "codesign": {"-d", "-dv"}, "mdls": None, "sysctl": None, "last": None,
    "log": {"show"}, "sfltool": {"dumpbtm"}, "systemextensionsctl": {"list"}, "crontab": {"-l"}, "uname": None,
    "sw_vers": None, "id": None, "scutil": {"--get"}, "hostname": None, "zsh": None,
}  # fmt: skip


def est_lecture(commande: list[str]) -> bool:
    """Vrai si la commande ne fait que lire. osascript n'est en lecture que pour lister les éléments d'ouverture."""
    nom = Path(commande[0]).name
    if nom == "osascript":
        script = " ".join(commande[1:])
        return "every login item" in script and not any(m in script for m in ("delete", "make", "set ", "do shell"))
    if nom not in LECTURE:
        return False
    permis = LECTURE[nom]
    return permis is None or (len(commande) > 1 and commande[1] in permis)


@dataclass
class Plan:
    fiche_id: str
    nom: str
    label: str
    genre: str  # launchd, quarantaine, system_events, instructions, verifier, refus, rien
    message: str
    commandes: list[list[str]] = field(default_factory=list)  # lancées seulement avec --confirmer
    annulation: str = ""  # comment revenir en arrière (à l'écran)
    texte: str = ""  # instructions à recopier, ou de quoi vérifier
    avant: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def agit(self) -> bool:
        return self.genre in ("launchd", "quarantaine", "system_events")


@dataclass
class Bilan:
    plan: Plan
    fait: bool
    message: str
    action_id: int | None = None
    erreurs: list[str] = field(default_factory=list)


def _affiche(commandes: list[list[str]]) -> str:
    return "\n".join(shlex.join(c) for c in commandes)


def applescript(texte: str) -> str:
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def etat_launchd(systeme: Systeme, label: str) -> dict[str, bool]:
    """Chargé dans ta session ? Désactivé ? (deux commandes de lecture)"""
    domaine = f"gui/{systeme.uid}"
    charge = systeme.executer(["launchctl", "print", f"{domaine}/{label}"], delai=5).ok
    r = systeme.executer(["launchctl", "print-disabled", domaine], delai=5)
    desactive = analyser_desactives(r.sortie).get(label, False) if r.ok else False
    return {"charge": charge, "desactive": desactive}


def planifier(e: Element, systeme: Systeme) -> Plan:
    f = e.fiche
    plan = Plan(f.id, e.nom, f.label, "rien", "")
    action = e.verdict.action
    if e.verdict.code == "apple":
        plan.genre, plan.message = "refus", "🍎 Élément de macOS : je n'y touche jamais."
        return plan
    if f.c_est_moi:
        plan.genre = "refus"
        plan.message = ("C'est moi, l'Assistant. Pour arrêter la surveillance : « demarrage surveiller off » ; "
                        "pour tout arrêter : « python service.py desinstaller ».")  # fmt: skip
        return plan
    if action == "verifier":
        plan.genre, plan.message = "verifier", "⚠️ Inconnu : je ne propose que de le vérifier, jamais de le supprimer."
        plan.texte = instructions.verifier(e.nom, e.editeur, f.chemin_plist, f.programme, e.premiere_vue,
                                           e.verdict.raison)  # fmt: skip
        return plan
    if action == "aucune":
        plan.message = "Rien à faire : il ne se lance déjà plus."
        return plan
    if action == "instructions":
        plan.genre = "instructions"
        plan.message = "Je ne le fais pas à ta place (il concerne tout le Mac). Voici quoi taper toi-même :"
        if f.source == "agent_global":
            plan.texte, plan.annulation = instructions.agent_global(f.label, systeme.uid, f.chemin_plist)
        elif f.source == "assistant_privilegie":
            plan.texte, plan.annulation = instructions.assistant_privilegie(
                f.programme or f.label, f.details.get("lance_par")
            )
        elif f.source == "extension":
            plan.texte, plan.annulation = instructions.extension(e.nom)
        elif f.source == "cron":
            plan.texte, plan.annulation = instructions.cron(str(f.details.get("horaire", "")))
        else:  # daemons globaux ou embarqués
            plan.texte, plan.annulation = instructions.daemon(f.label, f.chemin_plist)
        return plan
    if action == "reglages":
        texte, annulation = instructions.ouverture(e.nom)
        if systeme.a_la_commande("osascript"):
            nom = str(f.details.get("nom_ouverture") or e.fiche.nom or e.nom)
            plan.genre = "system_events"
            plan.message = f"Je retire « {nom} » des éléments d'ouverture (par System Events)."
            plan.commandes = [
                ["osascript", "-e", f'tell application "System Events" to delete login item {applescript(nom)}']
            ]
            plan.annulation = f"demarrage restaurer {f.id} --confirmer  (ou : {annulation})"
            plan.details = {"nom": nom, "app": f.app_parente}
            plan.texte = texte  # le chemin des Réglages, si l'autorisation manque
        else:
            plan.genre, plan.message, plan.texte, plan.annulation = (
                "instructions",
                "À faire dans les Réglages :",
                texte,
                annulation,
            )
        return plan
    # desactiver ou quarantaine : un élément de ta session
    domaine = f"gui/{systeme.uid}"
    etat = etat_launchd(systeme, f.label)
    plan.avant = etat
    plan.details = {"domaine": domaine, "chemin_plist": f.chemin_plist}
    if etat["charge"]:
        plan.commandes.append(["launchctl", "bootout", f"{domaine}/{f.label}"])
    if action == "quarantaine":
        if not f.chemin_plist or not systeme.chemin(f.chemin_plist).exists():
            plan.message = "Rien à faire : son fichier n'est plus là."
            return plan
        plan.genre = "quarantaine"
        plan.message = (f"Orphelin : je retire son fichier {f.chemin_plist} (déplacé en quarantaine, pas effacé)."
                        + (" Il est chargé : je l'arrête d'abord." if etat["charge"] else ""))  # fmt: skip
        plan.annulation = f"demarrage restaurer {f.id} --confirmer"
        return plan
    if not etat["desactive"]:
        plan.commandes.append(["launchctl", "disable", f"{domaine}/{f.label}"])
    if not plan.commandes:
        plan.message = "Rien à faire : il est déjà arrêté et désactivé."
        return plan
    plan.genre = "launchd"
    plan.message = "Je l'arrête et l'empêche de se relancer au démarrage. Son fichier reste en place."
    defaire = [["launchctl", "enable", f"{domaine}/{f.label}"]]
    if etat["charge"] and f.chemin_plist:
        defaire.append(["launchctl", "bootstrap", domaine, f.chemin_plist])
    plan.annulation = (
        f"demarrage restaurer {f.id} --confirmer\n(c'est-à-dire : {'  puis  '.join(shlex.join(c) for c in defaire)})"
    )
    return plan


def desactiver(e: Element, systeme: Systeme, journal: Journal, dossier: Path, confirmer: bool = False) -> Bilan:
    plan = planifier(e, systeme)
    if not confirmer or not plan.agit:
        return Bilan(plan, False, "Simulation : rien n'a été modifié." if plan.agit else plan.message)
    faites: list[list[str]] = []
    erreurs: list[str] = []
    for commande in plan.commandes:
        r = systeme.executer(commande, delai=15)
        if not r.ok:
            erreurs.append(f"{shlex.join(commande)} : {r.erreur.strip()[:200] or f'code {r.code}'}")
            break
        faites.append(commande)
    details = dict(plan.details)
    if plan.genre == "system_events" and erreurs:
        refus = "-1743" in erreurs[0] or "Not authorized" in erreurs[0]
        message = "System Events refuse (autorisation « Automatisation »). " if refus else "System Events a échoué. "
        return Bilan(plan, False, message + "À faire à la main : " + plan.texte, erreurs=erreurs)
    if plan.genre == "quarantaine" and not erreurs:
        try:
            infos = {"label": e.fiche.label, "fiche_id": e.fiche.id, "avant": plan.avant}
            cible = quarantaine.mettre(systeme, str(plan.details["chemin_plist"]), dossier, infos)
            details["quarantaine"] = str(cible)
        except OSError as err:
            erreurs.append(f"quarantaine impossible : {err}")
    if not faites and "quarantaine" not in details:
        return Bilan(plan, False, "Rien n'a été modifié.", erreurs=erreurs)
    apres = etat_launchd(systeme, e.fiche.label) if plan.genre in ("launchd", "quarantaine") else {}
    action = Action(0, systeme.maintenant(), e.fiche.id, e.fiche.label, plan.genre, plan.avant, apres, faites, details)
    action_id = journal.noter(action)
    if erreurs:
        return Bilan(plan, True, "Fait en partie seulement (noté au journal, « restaurer » sait le défaire).",
                     action_id, erreurs)  # fmt: skip
    if plan.genre == "launchd" and (apres.get("charge") or not apres.get("desactive")):
        return Bilan(plan, True, "Commandes passées, mais launchd ne le montre pas encore désactivé.", action_id)
    return Bilan(plan, True, "C'est fait. Pour annuler : " + plan.annulation.splitlines()[0], action_id)
