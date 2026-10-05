"""S5 — l'ouverture de session et les tâches de fond déclarées (Réglages Système > Général > Ouverture).

Trois façons, essayées dans l'ordre, sans jamais demander les droits d'administrateur :
1. `sfltool dumpbtm` : la liste complète, avec l'état activé/désactivé de chaque élément. Souvent réservé à root ;
2. `osascript` sur System Events : les apps « Ouvrir à la connexion ». Il peut déclencher une demande
   d'autorisation « Automatisation » ; délai maximum de 10 s, on n'attend jamais plus ;
3. la déduction : les apps lancées par launchd dans les 2 minutes après l'ouverture de session, vues par
   l'échantillonneur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import unquote

from modules.demarrage.collecteurs.applications import Index, lire_app
from modules.demarrage.collecteurs.plists import app_contenant
from modules.demarrage.fichiers import existe
from modules.demarrage.modele import Fiche, identifiant
from modules.demarrage.systeme import Systeme

FENETRE_DEDUCTION_S = 120

SCRIPT_SYSTEM_EVENTS = [
    'tell application "System Events"',
    'set sortie to ""',
    "repeat with e in every login item",
    "set sortie to sortie & (name of e) & tab & (path of e) & tab & (hidden of e) & linefeed",
    "end repeat",
    "end tell",
    "return sortie",
]


@dataclass
class ElementBTM:
    uid: int
    nom: str
    genre: str  # app, login item, agent, daemon, legacy agent, legacy daemon, developer…
    active: bool
    autorise: bool
    identifiant: str = ""
    bundle: str | None = None
    chemin: str | None = None  # depuis URL (file://…)
    executable: str | None = None
    editeur: str | None = None
    equipe: str | None = None

    @property
    def label(self) -> str:
        return self.bundle or re.sub(r"^\d+\.", "", self.identifiant) or self.nom


@dataclass
class ResultatOuverture:
    fiches: list[Fiche] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)
    methode: str = ""  # sfltool, osascript, déduction, aucune
    elements_btm: list[ElementBTM] = field(default_factory=list)


def analyser_dumpbtm(texte: str) -> list[ElementBTM]:
    elements: list[ElementBTM] = []
    uid: int | None = None
    courant: dict[str, str] | None = None

    def fermer() -> None:
        if courant is None or uid is None:
            return
        disposition = set(re.findall(r"[a-z]+", courant.get("Disposition", "").split("(")[0]))
        url = courant.get("URL", "")
        chemin = unquote(url[len("file://") :]).rstrip("/") if url.startswith("file://") else None
        editeur = courant.get("Developer Name")
        elements.append(
            ElementBTM(
                uid=uid,
                nom=courant.get("Name", "?"),
                genre=courant.get("Type", "").split(" (")[0].strip(),
                active="enabled" in disposition and "disabled" not in disposition,
                autorise="allowed" in disposition and "disallowed" not in disposition,
                identifiant=courant.get("Identifier", ""),
                bundle=courant.get("Bundle Identifier"),
                chemin=chemin or None,
                executable=courant.get("Executable Path"),
                editeur=None if editeur in (None, "", "(null)") else editeur,
                equipe=courant.get("Team Identifier"),
            )
        )

    for ligne in texte.splitlines():
        m = re.match(r"^\s*Records for UID (-?\d+)", ligne)
        if m:
            fermer()
            courant, uid = None, int(m.group(1))
            continue
        if re.match(r"^\s*#\d+:\s*$", ligne):
            fermer()
            courant = {}
            continue
        if courant is not None:
            cle, sep, valeur = ligne.strip().partition(": ")
            if sep:
                courant[cle.strip()] = valeur.strip()
    fermer()
    return elements


def analyser_system_events(texte: str) -> list[tuple[str, str, bool]]:
    """(nom, chemin, caché) pour chaque ligne « nom<tab>chemin<tab>caché »."""
    resultats = []
    for ligne in texte.splitlines():
        morceaux = ligne.split("\t")
        if len(morceaux) >= 2 and morceaux[1].strip():
            cache = len(morceaux) > 2 and morceaux[2].strip() == "true"
            resultats.append((morceaux[0].strip(), morceaux[1].strip().rstrip("/"), cache))
    return resultats


def deduire(lancements: list[tuple[str, int, float]]) -> list[str]:
    """Les apps lancées par launchd (parent 1) dans les 2 minutes après l'ouverture de session.

    lancements : (chemin de l'exécutable, PID parent, secondes entre l'ouverture de session et son lancement).
    """
    apps: list[str] = []
    for comm, ppid, apres in lancements:
        app = app_contenant(comm)
        rangee = bool(app) and "/Applications/" in str(app) and not str(app).startswith("/System/")
        if ppid == 1 and 0 <= apres <= FENETRE_DEDUCTION_S and rangee and app not in apps:
            apps.append(str(app))
    return apps


def _fiche_app(systeme: Systeme, index: Index, chemin: str, nom: str, methode: str) -> Fiche:
    app = index.par_chemin(chemin) or (lire_app(systeme, chemin) if existe(systeme, chemin) else None)
    label = (app.bundle_id if app else None) or nom or PurePosixPath(chemin).stem
    return Fiche(
        id=identifiant("ouverture", label),
        label=label,
        source="ouverture",
        nom=nom or (app.nom if app else PurePosixPath(chemin).stem),
        programme=(app.executable or chemin) if app else chemin,
        programme_existe=existe(systeme, app.executable or chemin) if app else False,
        app_parente=chemin,
        actif=True,
        desactive=False,
        details={"methode": methode},
    )


def _depuis_btm(systeme: Systeme, index: Index, elements: list[ElementBTM], fiches: list[Fiche]) -> list[Fiche]:
    """Les apps d'ouverture deviennent des fiches ; les agents et daemons déjà connus sont complétés."""
    nouvelles: list[Fiche] = []
    par_label = {f.label: f for f in fiches}
    par_plist = {f.chemin_plist: f for f in fiches if f.chemin_plist}
    for e in elements:
        if e.uid not in (0, systeme.uid) or e.genre == "developer":
            continue
        connue = (par_plist.get(e.chemin) if e.chemin else None) or par_label.get(e.label)
        if connue is not None:
            connue.details["btm"] = {"active": e.active, "autorise": e.autorise, "genre": e.genre}
            if connue.source in ("agent_app", "daemon_app", "ouverture_app"):
                connue.actif = e.active and e.autorise and not connue.desactive
            elif not e.active:
                connue.actif, connue.desactive = False, True
            continue
        if e.genre in ("app", "login item", "user item") and e.chemin:
            f = _fiche_app(systeme, index, e.chemin, e.nom, "sfltool")
            f.actif, f.desactive = e.active and e.autorise, not e.active
            f.details["btm"] = {"active": e.active, "autorise": e.autorise, "genre": e.genre}
            if e.editeur:
                f.details["editeur_btm"] = e.editeur
            nouvelles.append(f)
    return nouvelles


def collecter(
    systeme: Systeme,
    index: Index,
    fiches: list[Fiche],
    apps_vues_au_demarrage: list[str] | None = None,
    delai_osascript: float = 10.0,
) -> ResultatOuverture:
    r = ResultatOuverture()
    if systeme.a_la_commande("sfltool"):
        sortie = systeme.executer(["sfltool", "dumpbtm"], delai=15.0)
        if sortie.ok and "Items:" in sortie.sortie:
            r.elements_btm = analyser_dumpbtm(sortie.sortie)
            r.fiches = _depuis_btm(systeme, index, r.elements_btm, fiches)
            r.methode = "sfltool"
            return r
        r.erreurs.append("sfltool dumpbtm réservé à l'administrateur")
    else:
        r.erreurs.append("sfltool absent")
    if systeme.a_la_commande("osascript"):
        commande = ["osascript"] + [x for ligne in SCRIPT_SYSTEM_EVENTS for x in ("-e", ligne)]
        sortie = systeme.executer(commande, delai=delai_osascript)
        if sortie.ok:
            vues: set[str] = set()
            for nom, chemin, cache in analyser_system_events(sortie.sortie):
                if chemin in vues:
                    continue
                vues.add(chemin)
                f = _fiche_app(systeme, index, chemin, nom, "osascript")
                f.details["cache"] = cache
                r.fiches.append(f)
            r.methode = "osascript"
            r.erreurs.append("liste lue par System Events (les tâches de fond n'y sont pas)")
            return r
        if "-1743" in sortie.erreur or "Not authorized" in sortie.erreur:
            r.erreurs.append("System Events : autorisation « Automatisation » refusée ou pas encore donnée")
        elif sortie.code == 124:
            r.erreurs.append("System Events ne répond pas (10 s)")
        else:
            r.erreurs.append(f"System Events : {sortie.erreur.strip()[:100] or sortie.code}")
    if apps_vues_au_demarrage:
        r.fiches = [_fiche_app(systeme, index, a, "", "déduction") for a in apps_vues_au_demarrage]
        r.methode = "déduction"
        r.erreurs.append("déduit des apps lancées juste après l'ouverture de session")
        return r
    r.methode = "aucune"
    r.erreurs.append("pas encore d'observation d'une ouverture de session")
    return r
