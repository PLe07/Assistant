"""Les apps installées et les raccourcis Apple, lus en lecture seule pour construire le catalogue.

- Apps : `/Applications` (et ses sous-dossiers d'un niveau, comme « Utilities »), `~/Applications`,
  `/System/Applications` (et « Utilities »), le Finder, plus ce que Spotlight connaît (`mdfind`) dans ces dossiers.
  Pour chacune : son identifiant (CFBundleIdentifier), son nom, et son **nom français** s'il en a un
  (`fr.lproj/InfoPlist.strings`, ou `InfoPlist.loctable` sur les macOS récents) ; sinon celui de `apps_connues.json`.
- Raccourcis Apple : `shortcuts list` (leurs noms seulement).
Rien n'est écrit, rien n'est lancé d'autre que `mdfind` et `shortcuts list` (lecture), avec un délai maximum.
"""

from __future__ import annotations

import plistlib
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from voix.actions.executeur import Executeur, ProgrammeRefuse
from voix.nlu.catalogue import Objet, apps_connues, objet_app

APPS_MAX = 2000
FINDER = Path("/System/Library/CoreServices/Finder.app")
REQUETE_MDFIND = "kMDItemContentType == 'com.apple.application-bundle'"

Executer = Callable[[list[str], float], tuple[int, str]]


def executer(args: list[str], delai: float) -> tuple[int, str]:
    """Une commande de lecture, par l'exécuteur de la liste blanche (sans shell, avec un délai maximum)."""
    try:
        r = Executeur().lancer(args[0], args[1:], delai)
    except ProgrammeRefuse:
        return 127, ""
    return r.code, r.sortie


def racines(maison: Path) -> list[Path]:
    return [
        Path("/Applications"),
        maison / "Applications",
        Path("/System/Applications"),
    ]


def _chaines(fichier: Path) -> dict[str, str]:
    """Un `.strings` : plist (binaire ou XML) ou ancien format texte « "clé" = "valeur"; »."""
    try:
        donnees = fichier.read_bytes()
    except OSError:
        return {}
    try:
        lu = plistlib.loads(donnees)
        return {k: v for k, v in lu.items() if isinstance(v, str)} if isinstance(lu, dict) else {}
    except Exception:  # noqa: BLE001 - pas un plist : ancien format texte
        pass
    for codage in ("utf-16", "utf-8"):
        try:
            texte = donnees.decode(codage)
        except UnicodeDecodeError:
            continue
        paires = re.findall(r'"?([A-Za-z]+)"?\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', texte)
        if paires:
            return dict(paires)
    return {}


def nom_francais(app: Path) -> str | None:
    ressources = app / "Contents" / "Resources"
    for dossier in ("fr.lproj", "French.lproj", "fr_FR.lproj"):
        chaines = _chaines(ressources / dossier / "InfoPlist.strings")
        nom = chaines.get("CFBundleDisplayName") or chaines.get("CFBundleName")
        if nom:
            return nom
    table = ressources / "InfoPlist.loctable"
    if table.exists():
        try:
            lu = plistlib.loads(table.read_bytes())
        except Exception:  # noqa: BLE001
            return None
        if isinstance(lu, dict):
            for langue in ("fr", "fr_FR", "fr-FR"):
                d = lu.get(langue)
                if isinstance(d, dict):
                    nom = d.get("CFBundleDisplayName") or d.get("CFBundleName")
                    if isinstance(nom, str) and nom:
                        return nom
    return None


def lire_app(app: Path) -> tuple[str, str] | None:
    """(identifiant, nom affiché) d'un paquet .app, ou None s'il est illisible."""
    try:
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    except Exception:  # noqa: BLE001 - un paquet abîmé ne casse pas le catalogue
        return None
    if not isinstance(info, dict):
        return None
    ident = info.get("CFBundleIdentifier")
    if not isinstance(ident, str) or not ident:
        return None
    if info.get("LSUIElement") in (True, "1", 1) or info.get("LSBackgroundOnly") in (True, "1", 1):
        return None  # une app d'arrière-plan (barre des menus, agent) : rien à ouvrir par la voix
    nom = nom_francais(app) or info.get("CFBundleDisplayName") or info.get("CFBundleName") or app.stem
    return ident, str(nom)


def _paquets(dossier: Path) -> Iterable[Path]:
    """Les .app d'un dossier et de ses sous-dossiers d'un niveau (« Utilities », « Microsoft Office »…)."""
    try:
        entrees = sorted(dossier.iterdir())
    except OSError:
        return
    for e in entrees:
        if e.suffix == ".app":
            yield e
        elif e.is_dir() and not e.name.startswith("."):
            try:
                yield from sorted(x for x in e.iterdir() if x.suffix == ".app")
            except OSError:
                continue


def apps_installees(maison: Path, executer_: Executer = executer, dossiers: list[Path] | None = None) -> list[Objet]:
    connues = apps_connues()
    bases = dossiers if dossiers is not None else racines(maison)
    chemins: list[Path] = []
    for d in bases:
        chemins.extend(_paquets(d))
    if dossiers is None and FINDER.exists():
        chemins.append(FINDER)
    code, sortie = executer_(["mdfind", REQUETE_MDFIND], 20)
    if code == 0:
        for ligne in sortie.splitlines():
            p = Path(ligne.strip())
            if p.suffix == ".app" and any(b in p.parents for b in bases) and ".app/" not in str(p.parent) + "/":
                chemins.append(p)
    vus: set[str] = set()
    objets: list[Objet] = []
    for chemin in chemins:
        if len(objets) >= APPS_MAX:
            break
        lu = lire_app(chemin)
        if lu is None or lu[0] in vus:
            continue
        vus.add(lu[0])
        objets.append(objet_app(lu[0], lu[1], str(chemin), connues))
    return objets


def raccourcis_installes(executer_: Executer = executer) -> list[Objet]:
    code, sortie = executer_(["shortcuts", "list"], 20)
    if code != 0:
        return []
    noms = [ligne.strip() for ligne in sortie.splitlines() if ligne.strip() and len(ligne.strip()) <= 80]
    return [Objet("raccourci", n, n, f"raccourci:{n}", (n.lower(),)) for n in dict.fromkeys(noms)]
