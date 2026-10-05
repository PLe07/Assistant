"""S6 — l'état dans launchd : qui est chargé (avec son PID), son dernier code de sortie, qui est désactivé.

La sortie de « launchctl print » change d'une version de macOS à l'autre : chaque analyse est défensive (une ligne
inattendue est ignorée, jamais une exception), et testée sur des sorties reconstruites puis réelles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from modules.demarrage.systeme import Systeme


@dataclass
class Service:
    pid: int | None
    dernier_code: int | None  # dernier code de sortie (négatif : tué par un signal)


@dataclass
class DetailService:
    programme: str | None = None
    chemin: str | None = None
    relances: int | None = None  # « runs »
    dernier_code: int | None = None
    pid: int | None = None
    etat: str | None = None


@dataclass
class EtatLaunchd:
    gui: dict[str, Service] = field(default_factory=dict)  # domaine de ta session
    systeme: dict[str, Service] = field(default_factory=dict)  # domaine système (si lisible sans root)
    desactives_gui: dict[str, bool] = field(default_factory=dict)
    desactives_systeme: dict[str, bool] = field(default_factory=dict)
    systeme_lisible: bool = False
    gui_lisible: bool = False  # faux si ni « print gui/UID » ni « list » n'ont répondu : on ne sait pas
    erreurs: list[str] = field(default_factory=list)


def _entier(texte: str) -> int | None:
    m = re.match(r"^\(?\s*(?:signal\s+)?(-?\d+)", texte.strip())
    if not m:
        return None
    n = int(m.group(1))
    return -n if "signal" in texte else n


def analyser_list(texte: str) -> dict[str, Service]:
    """« launchctl list » : PID<tab>Status<tab>Label."""
    services: dict[str, Service] = {}
    for ligne in texte.splitlines():
        morceaux = ligne.split("\t")
        if len(morceaux) != 3 or morceaux[0] == "PID":
            continue
        pid_t, code_t, label = (m.strip() for m in morceaux)
        if not label:
            continue
        pid = int(pid_t) if pid_t.isdigit() and int(pid_t) > 0 else None
        services[label] = Service(pid, _entier(code_t) if code_t not in ("-", "") else None)
    return services


def _bloc(texte: str, titre: str) -> list[str]:
    """Les lignes du bloc « titre = { … } » (au premier niveau d'imbrication sous lui)."""
    lignes = texte.splitlines()
    for i, ligne in enumerate(lignes):
        if ligne.strip() == f"{titre} = {{":
            profondeur, contenu = 1, list[str]()
            for suite in lignes[i + 1 :]:
                s = suite.strip()
                if s.endswith("{"):
                    profondeur += 1
                elif s == "}":
                    profondeur -= 1
                    if profondeur == 0:
                        return contenu
                if profondeur == 1:
                    contenu.append(s)
            return contenu
    return []


_SERVICE = re.compile(r"^(-?\d+|-)\s+(\(signal \d+\)|-?\d+|-)\s+(.+)$")


def analyser_print_domaine(texte: str) -> dict[str, Service]:
    """Le bloc « services = { PID  dernier-code  label } » de « launchctl print gui/UID » ou « system »."""
    services: dict[str, Service] = {}
    for ligne in _bloc(texte, "services"):
        m = _SERVICE.match(ligne)
        if not m:
            continue
        pid_t, code_t, label = m.groups()
        pid = int(pid_t) if pid_t.lstrip("-").isdigit() and int(pid_t) > 0 else None
        services[label.strip()] = Service(pid, None if code_t == "-" else _entier(code_t))
    return services


_DESACTIVE = re.compile(r'^"(.+)"\s*=>\s*(\w+)\s*$')


def analyser_desactives(texte: str) -> dict[str, bool]:
    """« "label" => disabled|enabled » (macOS récent) ou « => true|false » (ancien). Vrai : désactivé."""
    etats: dict[str, bool] = {}
    for ligne in _bloc(texte, "disabled services"):
        m = _DESACTIVE.match(ligne)
        if m and m.group(2) in ("disabled", "true", "enabled", "false"):
            etats[m.group(1)] = m.group(2) in ("disabled", "true")
    return etats


def analyser_print_service(texte: str) -> DetailService:
    """« launchctl print gui/UID/label » : programme, chemin, nombre de lancements, dernier code."""
    d = DetailService()
    for ligne in texte.splitlines():
        if not ligne.startswith("\t") or ligne.startswith("\t\t"):
            continue  # seulement les clés du premier niveau
        cle, _, valeur = ligne.strip().partition(" = ")
        valeur = valeur.strip()
        if cle == "program":
            d.programme = valeur
        elif cle == "path":
            d.chemin = valeur
        elif cle == "runs":
            d.relances = _entier(valeur)
        elif cle == "last exit code":
            d.dernier_code = _entier(valeur.split(":")[0])
        elif cle == "pid":
            d.pid = _entier(valeur)
        elif cle == "state":
            d.etat = valeur
    return d


def collecter(systeme: Systeme, delai: float = 10.0) -> EtatLaunchd:
    etat = EtatLaunchd()
    if not systeme.a_la_commande("launchctl"):
        etat.erreurs.append("launchctl absent")
        return etat
    gui = f"gui/{systeme.uid}"
    r = systeme.executer(["launchctl", "print", gui], delai=delai)
    if r.ok:
        etat.gui = analyser_print_domaine(r.sortie)
        etat.desactives_gui = analyser_desactives(r.sortie)
        etat.gui_lisible = True
    else:
        etat.erreurs.append(f"launchctl print {gui} : {r.erreur.strip()[:120] or r.code}")
    r = systeme.executer(["launchctl", "list"], delai=delai)
    if r.ok:
        etat.gui_lisible = True
        for label, service in analyser_list(r.sortie).items():
            ancien = etat.gui.get(label)
            etat.gui[label] = Service(service.pid or (ancien.pid if ancien else None), service.dernier_code)
    elif not etat.gui:
        etat.erreurs.append(f"launchctl list : {r.erreur.strip()[:120] or r.code}")
    r = systeme.executer(["launchctl", "print-disabled", gui], delai=delai)
    if r.ok:
        etat.desactives_gui.update(analyser_desactives(r.sortie))
    r = systeme.executer(["launchctl", "print", "system"], delai=delai)
    if r.ok and "services = {" in r.sortie:
        etat.systeme = analyser_print_domaine(r.sortie)
        etat.desactives_systeme = analyser_desactives(r.sortie)
        etat.systeme_lisible = True
    r = systeme.executer(["launchctl", "print-disabled", "system"], delai=delai)
    if r.ok:
        etat.desactives_systeme.update(analyser_desactives(r.sortie))
    return etat


def detail(systeme: Systeme, domaine: str, label: str, delai: float = 5.0) -> DetailService | None:
    r = systeme.executer(["launchctl", "print", f"{domaine}/{label}"], delai=delai)
    return analyser_print_service(r.sortie) if r.ok else None
