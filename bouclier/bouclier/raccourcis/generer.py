"""Les deux raccourcis de l'iPhone (§8), générés en listes de propriétés `WFWorkflowActions`, avec `ActionExtension`
pour apparaître dans la feuille de partage. `install.sh` les signe sur le Mac (`shortcuts sign --mode anyone`) et
les dépose dans iCloud Drive/Bouclier : sur l'iPhone, Fichiers → Bouclier → toucher le raccourci → « Ajouter ».

« Arnaque ? » (texte, capture d'écran, lien, mail partagés) :
1. donne un nom unique à l'élément (« arnaque-<date>-<nombre> ») et l'enregistre dans `Bouclier/entree/` ;
2. regarde toutes les 3 secondes, 20 fois (60 s), si `Bouclier/reponses/<nom>.txt` est arrivé ;
3. affiche la réponse du Mac ; sans réponse, affiche les 5 réflexes de base (écrits dans le raccourci lui-même).

« Envoyer sans traces » (photos) : 100 % sur l'iPhone, sans le Mac. « Convertir l'image » en JPEG avec
« Conserver les métadonnées » désactivé, puis la feuille de partage.

Comme pour le Trieur (D-12), un chemin relatif « Bouclier/… » d'un raccourci désigne le dossier iCloud de l'app
Raccourcis (iCloud Drive/Shortcuts/Bouclier) : le Mac surveille ce dossier-là aussi et y répond.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from bouclier.arnaque.reponse import reflexes_de_base

ARNAQUE = "Arnaque ?"
SANS_TRACES = "Envoyer sans traces"
ATTENTE_S = 3
ESSAIS = 20
TYPES_ARNAQUE = ["WFStringContentItem", "WFRichTextContentItem", "WFImageContentItem", "WFURLContentItem",
                 "WFSafariWebPageContentItem", "WFGenericFileContentItem", "WFPDFContentItem",
                 "WFEmailAddressContentItem", "WFPhoneNumberContentItem", "WFArticleContentItem"]  # fmt: skip
TYPES_IMAGES = ["WFImageContentItem", "WFGenericFileContentItem"]


def _id(graine: str) -> str:
    """Des identifiants stables : le même raccourci donne toujours le même fichier."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"bouclier/{graine}")).upper()


def _entree() -> dict[str, Any]:
    return {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"}


def _sortie(action: str, nom: str) -> dict[str, Any]:
    return {"Value": {"OutputUUID": _id(action), "Type": "ActionOutput", "OutputName": nom},
            "WFSerializationType": "WFTextTokenAttachment"}  # fmt: skip


def _texte(morceaux: list[str | tuple[str, str]]) -> dict[str, Any]:
    """Un texte fait de morceaux fixes et de sorties d'actions ((action, nom de la sortie))."""
    chaine, pieces = "", {}
    for m in morceaux:
        if isinstance(m, tuple):
            pieces[f"{{{len(chaine)}, 1}}"] = {"OutputUUID": _id(m[0]), "Type": "ActionOutput", "OutputName": m[1]}
            chaine += "￼"
        else:
            chaine += m
    return {"Value": {"string": chaine, "attachmentsByRange": pieces}, "WFSerializationType": "WFTextTokenString"}


def _action(identifiant: str, graine: str | None, **parametres: Any) -> dict[str, Any]:
    if graine is not None:
        parametres = {"UUID": _id(graine), **parametres}
    return {
        "WFWorkflowActionIdentifier": f"is.workflow.actions.{identifiant}",
        "WFWorkflowActionParameters": parametres,
    }


def _enveloppe(actions: list[dict[str, Any]], glyphe: int, couleur: int, types: list[str]) -> dict[str, Any]:
    return {
        "WFWorkflowClientVersion": "2302.0.4",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": couleur, "WFWorkflowIconGlyphNumber": glyphe},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": types,
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowHasShortcutInputVariables": True,
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": actions,
    }


def texte_reflexes() -> str:
    lignes = ["Le Mac n'a pas répondu. Les 5 réflexes de base :"]
    lignes += [f"{i}. {r}" for i, r in enumerate(reflexes_de_base(), 1)]
    return "\n".join(lignes)


def arnaque() -> dict[str, Any]:
    nombre, nom, renomme, boucle, si = (
        "arnaque/nombre",
        "arnaque/nom",
        "arnaque/renommer",
        "arnaque/boucle",
        "arnaque/si",
    )
    lire, reflexes = "arnaque/lire", "arnaque/reflexes"
    format_date = {"Type": "WFDateFormatVariableAggrandizement", "WFDateFormatStyle": "Custom",
                   "WFDateFormat": "yyyyMMdd-HHmmss"}  # fmt: skip
    date = {"Type": "CurrentDate", "Aggrandizements": [format_date]}
    hasard = {"OutputUUID": _id(nombre), "Type": "ActionOutput", "OutputName": "Random Number"}
    texte_nom = {"Value": {"string": "arnaque-￼-￼", "attachmentsByRange": {"{8, 1}": date, "{10, 1}": hasard}},
                 "WFSerializationType": "WFTextTokenString"}  # fmt: skip
    actions = [
        _action("number.random", nombre, WFRandomNumberMinimum=1000, WFRandomNumberMaximum=9999),
        _action("gettext", nom, WFTextActionText=texte_nom),
        _action(
            "setitemname", renomme, WFInput=_entree(), WFName=_texte([(nom, "Text")]), WFDontIncludeFileExtension=False
        ),  # fmt: skip
        _action(
            "documentpicker.save",
            "arnaque/enregistrer",
            WFInput=_sortie(renomme, "Renamed Item"),
            WFAskWhereToSave=False,
            WFFileDestinationPath="Bouclier/entree/",
            WFSaveFileOverwrite=False,
        ),  # fmt: skip
        _action("repeat.count", None, GroupingIdentifier=_id(boucle), WFControlFlowMode=0, WFRepeatCount=ESSAIS),
        _action("delay", "arnaque/attendre", WFDelayTime=ATTENTE_S),
        _action(
            "documentpicker.open",
            lire,
            WFGetFilePath=_texte(["Bouclier/reponses/", (nom, "Text"), ".txt"]),
            WFShowFilePicker=False,
            WFFileErrorIfNotFound=False,
        ),  # fmt: skip
        _action(
            "conditional",
            None,
            GroupingIdentifier=_id(si),
            WFControlFlowMode=0,
            WFCondition=100,
            WFInput={"Type": "Variable", "Variable": _sortie(lire, "File")},
        ),  # fmt: skip
        _action("showresult", "arnaque/afficher", Text=_texte([(lire, "File")])),
        _action("exit", "arnaque/fin"),
        _action("conditional", None, GroupingIdentifier=_id(si), WFControlFlowMode=2),
        _action("repeat.count", None, GroupingIdentifier=_id(boucle), WFControlFlowMode=2),
        _action("gettext", reflexes, WFTextActionText=_texte([texte_reflexes()])),
        _action("showresult", "arnaque/afficher-reflexes", Text=_texte([(reflexes, "Text")])),
    ]
    return _enveloppe(actions, 59765, 4282601983, TYPES_ARNAQUE)


def sans_traces() -> dict[str, Any]:
    convertir = "sans-traces/convertir"
    actions = [
        _action(
            "image.convert",
            convertir,
            WFInput=_entree(),
            WFImageFormat="JPEG",
            WFImagePreserveMetadata=False,
            WFImageCompressionQuality=0.9,
        ),  # fmt: skip
        _action("share", "sans-traces/partager", WFInput=_sortie(convertir, "Converted Image")),
    ]
    return _enveloppe(actions, 59458, 4271458815, TYPES_IMAGES)


RACCOURCIS = {ARNAQUE: arnaque, SANS_TRACES: sans_traces}


def ecrire(dossier: Path) -> list[Path]:
    """Les raccourcis non signés (plist binaire, comme ceux de l'app Raccourcis)."""
    dossier.mkdir(parents=True, exist_ok=True)
    sortie = []
    for nom, fabrique in RACCOURCIS.items():
        chemin = dossier / f"{nom}.non-signé.shortcut"
        with chemin.open("wb") as f:
            plistlib.dump(fabrique(), f, fmt=plistlib.FMT_BINARY)
        sortie.append(chemin)
    return sortie


def signer(non_signe: Path, destination: Path) -> tuple[bool, str]:
    """`shortcuts sign --mode anyone` (sur le Mac, avec un compte iCloud). Remplace notre propre fichier."""
    if not shutil.which("shortcuts"):
        return False, "la commande « shortcuts » n'existe pas ici (macOS 12 ou plus)"
    temporaire = destination.with_name(f".{destination.name}.tmp")
    try:
        r = subprocess.run(["shortcuts", "sign", "--mode", "anyone", "--input", str(non_signe), "--output",
                            str(temporaire)], capture_output=True, text=True, timeout=120)  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if r.returncode != 0 or not temporaire.exists():
        return False, (r.stderr or r.stdout).strip()[:300] or "échec de la signature"
    temporaire.replace(destination)
    return True, ""


def plutil_lint(chemin: Path) -> tuple[bool, str]:
    """`plutil -lint` (Mac) ; ailleurs, relecture par plistlib."""
    if shutil.which("plutil"):
        r = subprocess.run(["plutil", "-lint", str(chemin)], capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    try:
        with chemin.open("rb") as f:
            plistlib.load(f)
        return True, f"{chemin}: OK (plistlib)"
    except (plistlib.InvalidFileException, ValueError, OSError) as e:
        return False, str(e)


def installes(sortie_shortcuts_list: str) -> dict[str, bool]:
    """Pour doctor : les raccourcis présents dans `shortcuts list`."""
    noms = {ligne.strip() for ligne in sortie_shortcuts_list.splitlines()}
    return {nom: nom in noms for nom in RACCOURCIS}
