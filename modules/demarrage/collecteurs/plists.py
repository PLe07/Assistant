"""Lire un plist launchd sans jamais planter, et en tirer ce qu'il lance et quand.

Cas tordus : plist binaire ou XML, cassé, vide, qui n'est pas un dictionnaire, ProgramArguments vide, KeepAlive en
dictionnaire, BundleProgram relatif à l'app, programme qui est un interpréteur (sh, python…) lançant un script.
"""

from __future__ import annotations

import plistlib
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from modules.demarrage.fichiers import existe, localiser, resoudre
from modules.demarrage.modele import Declencheurs, Fiche, identifiant
from modules.demarrage.systeme import Systeme

TAILLE_MAX = 1_000_000  # un plist launchd fait quelques Ko ; au-delà, ce n'en est pas un

_INTERPRETES = re.compile(
    r"^(sh|bash|zsh|dash|ksh|csh|tcsh|fish|python[\d.]*|perl[\d.]*|ruby|node|osascript|env|nohup)$"
)
_SYSTEME = ("/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/", "/usr/libexec/", "/System/")


@dataclass
class Declaration:
    label: str | None
    programme: str | None  # le programme réellement lancé (le script pour un interpréteur)
    arguments: list[str] = field(default_factory=list)
    interprete: str | None = None
    repertoire: str | None = None  # WorkingDirectory : pour un programme au chemin relatif
    declencheurs: Declencheurs = field(default_factory=Declencheurs)
    desactive_plist: bool = False  # clé Disabled
    bundles_associes: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


def lire(chemin: Path) -> tuple[dict[str, Any] | None, str | None]:
    """(contenu, erreur) ; jamais d'exception."""
    try:
        if chemin.stat().st_size > TAILLE_MAX:
            return None, "fichier trop gros pour être un plist launchd"
        donnees = chemin.read_bytes()
    except OSError as e:
        return None, f"illisible ({e.strerror or e})"
    if not donnees.strip():
        return None, "fichier vide"
    try:
        contenu = plistlib.loads(donnees)
    except Exception:  # selon la version : InvalidFileException, ExpatError, ValueError…
        return None, "plist corrompu (illisible par launchd aussi)"
    if not isinstance(contenu, dict):
        return None, "plist inattendu (pas un dictionnaire)"
    return contenu, None


def _chaines(valeur: Any) -> list[str]:
    if isinstance(valeur, str):
        return [valeur]
    if isinstance(valeur, list):
        return [v for v in valeur if isinstance(v, str)]
    return []


def _declencheurs(c: dict[str, Any]) -> Declencheurs:
    garder = c.get("KeepAlive")
    conditions = sorted(str(k) for k in garder) if isinstance(garder, dict) else []
    calendrier = c.get("StartCalendarInterval")
    if isinstance(calendrier, dict):
        calendrier = [calendrier]
    intervalle = c.get("StartInterval")
    return Declencheurs(
        au_chargement=c.get("RunAtLoad") is True,
        garder_en_vie=garder is True or bool(conditions),
        garder_conditions=conditions,
        intervalle_s=intervalle if isinstance(intervalle, int) and not isinstance(intervalle, bool) and intervalle > 0
        else None,
        calendrier=[
            {str(k): int(v) for k, v in d.items() if isinstance(v, int) and not isinstance(v, bool)}
            for d in (calendrier if isinstance(calendrier, list) else [])
            if isinstance(d, dict)
        ],
        chemins_surveilles=_chaines(c.get("WatchPaths")) + _chaines(c.get("QueueDirectories")),
        au_montage=c.get("StartOnMount") is True,
    )  # fmt: skip


def est_systeme(chemin: str | None) -> bool:
    """Un programme du volume système de macOS (scellé, signé Apple)."""
    return bool(chemin) and str(chemin).startswith(_SYSTEME)


def app_contenant(chemin: str | None) -> str | None:
    """L'app la plus extérieure qui contient ce chemin (/Applications/X.app/Contents/… → /Applications/X.app)."""
    if not chemin:
        return None
    parties = PurePosixPath(chemin).parts
    for i, p in enumerate(parties):
        if p.endswith(".app") and i > 0:
            return str(PurePosixPath(*parties[: i + 1]))
    return None


def app_parente(systeme: Systeme, *chemins: str | None) -> tuple[str | None, str | None]:
    """(app parente, app d'aide) : l'app qui contient le programme est « parente » si elle est rangée avec les apps
    (/Applications, ~/Applications) ; ailleurs (~/Library, Application Support), c'est une app d'aide, dont la date
    de dernière ouverture ne dit rien de ton usage."""
    dossiers = ("/Applications/", f"{systeme.maison}/Applications/", "/System/Applications/")
    for chemin in chemins:
        app = app_contenant(chemin)
        if app:
            return (app, None) if app.startswith(dossiers) else (None, app)
    return None, None


def _script(interprete: str, args: list[str]) -> str | None:
    """Ce que lance vraiment un interpréteur : le script, ou la première commande de « sh -c "…" »."""
    nom = PurePosixPath(interprete).name
    reste = args[1:]
    if nom == "env":
        reste = [a for a in reste if "=" not in a or a.startswith("-")]
        reste = [a for a in reste if not a.startswith("-")]
        return reste[0] if reste else None
    if nom == "nohup":
        return reste[0] if reste else None
    i = 0
    while i < len(reste):
        a = reste[i]
        if a == "-c" and nom not in ("osascript",) and i + 1 < len(reste):
            try:
                mots = shlex.split(reste[i + 1])
            except ValueError:
                mots = reste[i + 1].split()
            mots = [m for m in mots if not re.match(r"^\w+=", m)]  # VAR=valeur devant la commande
            if mots and mots[0] == "exec":
                mots = mots[1:]
            return mots[0] if mots and mots[0] not in ("cd", "source", ".", "if", "for", "while") else None
        if a in ("-e", "-l") and nom in ("osascript", "perl", "ruby", "node"):
            return None  # du code en ligne, pas de fichier
        if a.startswith("-"):
            i += 1
            continue
        return a
    return None


def declaration(contenu: dict[str, Any], chemin_plist: str | None = None) -> Declaration:
    """Ce que dit le plist. chemin_plist sert à résoudre BundleProgram (relatif à l'app qui contient le plist)."""
    erreurs: list[str] = []
    label = contenu.get("Label") if isinstance(contenu.get("Label"), str) and contenu["Label"].strip() else None
    if label is None:
        erreurs.append("pas de Label")
    brut = contenu.get("ProgramArguments")  # launchd n'accepte qu'une liste
    args = [a for a in brut if isinstance(a, str)] if isinstance(brut, list) else []
    programme = contenu.get("Program") if isinstance(contenu.get("Program"), str) else None
    if programme is None and args:
        programme = args[0]
    if programme is None and isinstance(contenu.get("BundleProgram"), str):
        app = app_contenant(chemin_plist)
        programme = f"{app}/{contenu['BundleProgram']}" if app else contenu["BundleProgram"]
    if programme is None:
        erreurs.append("aucun programme (Program et ProgramArguments vides)")
    interprete = None
    if programme and _INTERPRETES.match(PurePosixPath(programme).name):
        script = _script(programme, args or [programme])
        if script:
            interprete, programme = programme, script
    if programme and PurePosixPath(programme).name == "open" and est_systeme(programme):
        app = next((a for a in args[1:] if a.endswith(".app") or a.endswith(".app/")), None)
        nom = args[args.index("-a") + 1] if "-a" in args and args.index("-a") + 1 < len(args) else None
        cible = app.rstrip("/") if app else (f"/Applications/{nom}.app" if nom and "/" not in nom else nom)
        if cible:
            interprete, programme = programme, cible
    return Declaration(
        label=label,
        programme=programme,
        arguments=args,
        interprete=interprete,
        repertoire=contenu.get("WorkingDirectory") if isinstance(contenu.get("WorkingDirectory"), str) else None,
        declencheurs=_declencheurs(contenu),
        desactive_plist=contenu.get("Disabled") is True,
        bundles_associes=_chaines(contenu.get("AssociatedBundleIdentifiers")),
        erreurs=erreurs,
    )


def fiche_depuis_plist(systeme: Systeme, chemin_plist: str, source: str) -> Fiche:
    """La fiche d'un plist ; un plist cassé donne quand même une fiche, avec son erreur."""
    reel = resoudre(systeme, chemin_plist)
    nom_fichier = PurePosixPath(chemin_plist).name.removesuffix(".plist")
    contenu: dict[str, Any] | None = None
    erreur: str | None = "lien cassé ou fichier disparu"
    if reel is not None:
        contenu, erreur = lire(systeme.chemin(reel))
    if contenu is None:
        return Fiche(
            id=identifiant(source, nom_fichier), label=nom_fichier, source=source, chemin_plist=chemin_plist,
            erreurs=[erreur or "illisible"],
        )  # fmt: skip
    d = declaration(contenu, reel)
    label = d.label or nom_fichier
    programme = localiser(systeme, d.programme, d.repertoire) if d.programme else None
    parente, aide = app_parente(systeme, programme or d.programme, reel)
    fiche = Fiche(
        id=identifiant(source, label),
        label=label,
        source=source,
        chemin_plist=chemin_plist,
        programme=programme or d.programme,
        arguments=d.arguments,
        interprete=d.interprete,
        programme_existe=existe(systeme, programme) if d.programme else None,
        app_parente=parente,
        bundles_associes=d.bundles_associes,
        declencheurs=d.declencheurs,
        desactive=True if d.desactive_plist else None,
        erreurs=d.erreurs,
    )
    if aide:
        fiche.details["app_aide"] = aide
    if reel != chemin_plist:
        fiche.details["lien_vers"] = reel
    if d.desactive_plist:
        fiche.details["cle_disabled"] = True
    return fiche


def fiches_du_dossier(systeme: Systeme, dossier: str, source: str) -> tuple[list[Fiche], str | None]:
    """Toutes les fiches d'un dossier de plists ; (fiches, erreur si le dossier est illisible)."""
    racine = systeme.chemin(dossier)
    try:
        noms = sorted(e.name for e in racine.iterdir() if e.name.endswith(".plist") and not e.name.startswith("._"))
    except FileNotFoundError:
        return [], None  # pas de dossier : rien ne s'y lance
    except OSError as e:
        return [], f"{dossier} illisible ({e.strerror or e})"
    return [fiche_depuis_plist(systeme, f"{dossier}/{nom}", source) for nom in noms], None
