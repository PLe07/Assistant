"""`demarrage desactiver ID` : d'abord un plan, établi en lisant l'état actuel (rien n'est modifié) ; puis, seulement
avec `--confirmer`, son exécution, sa vérification et son inscription au journal.

- Agent de ta session (S1, S4, chargé par launchd) : `launchctl disable` puis `launchctl bootout`, plist gardé ;
  puis on attend que launchd le montre arrêté et désactivé (il le fait parfois avec un temps de retard, D-43).
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
from modules.demarrage.modele import SOURCES_GLOBALES
from modules.demarrage.systeme import Resultat, Systeme

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


ATTENTE_LAUNCHD_S = 10.0
PAS_LAUNCHD_S = 0.5


def etat_launchd(systeme: Systeme, label: str) -> dict[str, bool]:
    """Chargé dans ta session ? Désactivé ? (deux commandes de lecture)"""
    domaine = f"gui/{systeme.uid}"
    charge = systeme.executer(["launchctl", "print", f"{domaine}/{label}"], delai=5).ok
    r = systeme.executer(["launchctl", "print-disabled", domaine], delai=5)
    desactive = analyser_desactives(r.sortie, bloc_obligatoire=False).get(label, False) if r.ok else False
    return {"charge": charge, "desactive": desactive}


def attendre_etat(
    systeme: Systeme, label: str, voulu: dict[str, bool], delai_s: float | None = None
) -> dict[str, bool]:
    """Relit l'état jusqu'à ce qu'il soit celui voulu, au plus delai_s secondes : launchd applique parfois un arrêt
    ou un chargement avec un temps de retard (le programme met un instant à s'arrêter). Renvoie le dernier état lu."""
    debut, delai = systeme.maintenant(), ATTENTE_LAUNCHD_S if delai_s is None else delai_s
    while True:
        etat = etat_launchd(systeme, label)
        if all(etat.get(cle) == valeur for cle, valeur in voulu.items()) or systeme.maintenant() - debut >= delai:
            return etat
        systeme.attendre(PAS_LAUNCHD_S)


def ecart(etat: dict[str, bool], voulu: dict[str, bool]) -> str:
    """Ce qui manque, en clair (vide si l'état est celui voulu)."""
    textes = {
        ("charge", True): "pas (encore) chargé",
        ("charge", False): "encore chargé",
        ("desactive", True): "pas (encore) marqué désactivé",
        ("desactive", False): "encore marqué désactivé",
    }
    return " et ".join(textes[(cle, valeur)] for cle, valeur in voulu.items() if etat.get(cle) != valeur)


def _instructions(e: Element, uid: int) -> tuple[str, str]:
    f = e.fiche
    if f.source == "agent_global":
        return instructions.agent_global(f.label, uid, f.chemin_plist)
    if f.source == "assistant_privilegie":
        return instructions.assistant_privilegie(f.programme or f.label, f.details.get("lance_par"))
    if f.source == "extension":
        return instructions.extension(e.nom)
    if f.source == "cron":
        return instructions.cron(str(f.details.get("horaire", "")))
    return instructions.daemon(f.label, f.chemin_plist)  # daemons globaux ou embarqués


def commandes_affichees(e: Element, uid: int) -> tuple[str, str]:
    """(pour agir, pour annuler), prêtes à copier, sans rien lire ni lancer : pour le rapport et RAPPORT_FINAL."""
    f, action = e.fiche, e.verdict.action
    if e.verdict.code == "apple" or f.c_est_moi or action == "aucune":
        return "", ""
    if action == "verifier":
        verification = instructions.verifier(e.nom, e.editeur, f.chemin_plist, f.programme, e.premiere_vue,
                                             e.verdict.raison)  # fmt: skip
        mecanisme = mecanisme_sans_suppression(e)
        if mecanisme == "aucune":
            return verification, ""
        if mecanisme == "instructions":
            arreter, revenir = _instructions(e, uid)
        else:
            arreter, revenir = f"demarrage desactiver {f.id} --confirmer", f"demarrage restaurer {f.id} --confirmer"
        si_tu_veux = "Si, après vérification, tu veux l'arrêter (réversible, rien n'est supprimé) :"
        return f"{verification}\n\n{si_tu_veux}\n{arreter}", revenir
    if action == "instructions":
        return _instructions(e, uid)
    agir, annuler = f"demarrage desactiver {f.id} --confirmer", f"demarrage restaurer {f.id} --confirmer"
    if action == "reglages":
        texte, a_la_main = instructions.ouverture(e.nom)
        return f"{agir}\n(ou à la main : {texte})", f"{annuler}\n(ou à la main : {a_la_main})"
    if action == "quarantaine":
        return f"{agir}\n(son fichier part en quarantaine, rien n'est effacé)", annuler
    cible = f"gui/{uid}/{f.label}"
    faire = shlex.join(["launchctl", "disable", cible]) + "\n" + shlex.join(["launchctl", "bootout", cible])
    defaire = [shlex.join(["launchctl", "enable", cible])]
    if f.chemin_plist:
        defaire.append(shlex.join(["launchctl", "bootstrap", f"gui/{uid}", f.chemin_plist]))
    return f"{agir}\n(c'est-à-dire :\n{faire})", f"{annuler}\n(c'est-à-dire :\n" + "\n".join(defaire) + ")"


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
        verification = instructions.verifier(e.nom, e.editeur, f.chemin_plist, f.programme, e.premiere_vue,
                                             e.verdict.raison)  # fmt: skip
        mecanisme = mecanisme_sans_suppression(e)
        if mecanisme == "aucune":
            plan.genre, plan.message, plan.texte = (
                "verifier",
                "⚠️ Inconnu : je ne propose que de le vérifier.",
                verification,
            )
            return plan
        # Tu l'as vérifié et tu veux l'arrêter : c'est réversible, et jamais une suppression ni une quarantaine.
        plan = _plan(plan, e, systeme, mecanisme)
        plan.message = ("⚠️ Inconnu : vérifie-le d'abord (ci-dessous). Si tu décides de l'arrêter, c'est réversible "
                        "et rien n'est supprimé. " + plan.message)  # fmt: skip
        plan.texte = verification + ("\n\n" + plan.texte if plan.texte else "")
        return plan
    return _plan(plan, e, systeme, action)


def mecanisme_sans_suppression(e: Element) -> str:
    """Pour un élément inconnu : le moyen réversible de l'arrêter, jamais la quarantaine."""
    f = e.fiche
    if f.actif is False:
        return "aucune"
    if f.source == "ouverture":
        return "reglages"
    if f.source in SOURCES_GLOBALES or f.source == "cron":
        return "instructions"
    return "desactiver"


def _plan(plan: Plan, e: Element, systeme: Systeme, action: str) -> Plan:
    f = e.fiche
    if action == "aucune":
        plan.message = "Rien à faire : il ne se lance déjà plus."
        return plan
    if action == "instructions":
        plan.genre = "instructions"
        plan.message = "Je ne le fais pas à ta place (il concerne tout le Mac). Voici quoi taper toi-même :"
        plan.texte, plan.annulation = _instructions(e, systeme.uid)
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
    if action == "quarantaine":
        if etat["charge"]:
            plan.commandes.append(["launchctl", "bootout", f"{domaine}/{f.label}"])
        if not f.chemin_plist or not systeme.chemin(f.chemin_plist).exists():
            plan.message = "Rien à faire : son fichier n'est plus là."
            return plan
        plan.genre = "quarantaine"
        plan.message = (f"Orphelin : je retire son fichier {f.chemin_plist} (déplacé en quarantaine, pas effacé)."
                        + (" Il est chargé : je l'arrête d'abord." if etat["charge"] else ""))  # fmt: skip
        plan.annulation = f"demarrage restaurer {f.id} --confirmer"
        return plan
    # D'abord désactiver (rien ne le relance, pas même son app), puis arrêter.
    if not etat["desactive"]:
        plan.commandes.append(["launchctl", "disable", f"{domaine}/{f.label}"])
    if etat["charge"]:
        plan.commandes.append(["launchctl", "bootout", f"{domaine}/{f.label}"])
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
        if (
            not r.ok
            and commande[1] == "bootout"
            and not attendre_etat(systeme, e.fiche.label, {"charge": False})["charge"]
        ):
            r = Resultat(0, r.sortie)  # « Operation now in progress » : l'arrêt a bien eu lieu, avec retard
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
    voulu = {"charge": False, "desactive": True} if plan.genre == "launchd" else {"charge": False}
    apres = (
        attendre_etat(systeme, e.fiche.label, voulu) if plan.genre in ("launchd", "quarantaine") and not erreurs else {}
    )
    if plan.genre in ("launchd", "quarantaine") and erreurs:
        apres = etat_launchd(systeme, e.fiche.label)
    action = Action(0, systeme.maintenant(), e.fiche.id, e.fiche.label, plan.genre, plan.avant, apres, faites, details)
    action_id = journal.noter(action)
    if erreurs:
        return Bilan(plan, True, "Fait en partie seulement (noté au journal, « restaurer » sait le défaire).",
                     action_id, erreurs)  # fmt: skip
    manque = ecart(apres, voulu) if plan.genre == "launchd" else ""
    if manque:
        return Bilan(plan, True, f"Commandes passées, mais après {ATTENTE_LAUNCHD_S:.0f} s launchd le montre {manque} "
                                 "(noté au journal ; « demarrage restaurer » sait le défaire).", action_id)  # fmt: skip
    return Bilan(plan, True, "C'est fait. Pour annuler : " + plan.annulation.splitlines()[0], action_id)
