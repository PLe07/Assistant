"""Les deux raccourcis de l'iPhone (§8), générés en listes de propriétés `WFWorkflowActions`. `install.sh` les signe
sur le Mac (`shortcuts sign --mode anyone`), les vérifie (`plutil -lint`) et les dépose dans iCloud Drive/Quotidien :
sur l'iPhone, Fichiers → Quotidien → toucher le raccourci → « Ajouter le raccourci ».

« Mon frigo » :
1. un menu : « 📷 Prendre une photo », « 🖼️ Choisir une photo », « ✍️ Écrire ou dicter » ;
2. l'élément reçoit un nom unique (« frigo-<date>-<nombre> ») et va dans `Quotidien/entree/` ;
3. toutes les 3 secondes, 20 fois (60 s), le raccourci regarde si `Quotidien/reponses/<nom>.txt` est arrivé ;
4. il affiche les 3 recettes ; sans réponse : « Mac injoignable, réessaie plus tard ».

« Envie de… » : « Envie de quoi ? » (écrit ou dicté) → `Quotidien/entree/envie-<…>.txt` → la réponse du Mac.

Un chemin relatif « Quotidien/… » d'un raccourci désigne le dossier iCloud de l'app Raccourcis
(iCloud Drive/Shortcuts/Quotidien, leçon du Trieur) : le Mac surveille ce dossier-là aussi et y répond.
Aucun raccourci n'envoie quoi que ce soit à quelqu'un : ils déposent un fichier et lisent une réponse.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

MON_FRIGO = "Mon frigo"
ENVIE = "Envie de…"
ATTENTE_S = 3
ESSAIS = 20
INJOIGNABLE = "Mac injoignable, réessaie plus tard."
CHOIX_FRIGO = ("📷 Prendre une photo", "🖼️ Choisir une photo", "✍️ Écrire ou dicter")


def _id(graine: str) -> str:
    """Des identifiants stables : le même raccourci donne toujours le même fichier."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"quotidien/{graine}")).upper()


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


def _enveloppe(actions: list[dict[str, Any]], glyphe: int, couleur: int) -> dict[str, Any]:
    return {
        "WFWorkflowClientVersion": "2302.0.4",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": couleur, "WFWorkflowIconGlyphNumber": glyphe},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": ["NCWidget", "WatchKit"],
        "WFWorkflowInputContentItemClasses": [],
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowHasShortcutInputVariables": False,
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": actions,
    }


def _deposer_et_attendre(prefixe: str, entree: dict[str, Any]) -> list[dict[str, Any]]:
    """Nommer l'élément, l'enregistrer dans Quotidien/entree/, attendre 60 s la réponse, l'afficher."""
    nombre, nom, renomme, boucle, si, lire = (f"{prefixe}/{x}" for x in ("nombre", "nom", "renommer", "boucle", "si",
                                                                         "lire"))  # fmt: skip
    format_date = {"Type": "WFDateFormatVariableAggrandizement", "WFDateFormatStyle": "Custom",
                   "WFDateFormat": "yyyyMMdd-HHmmss"}  # fmt: skip
    date = {"Type": "CurrentDate", "Aggrandizements": [format_date]}
    hasard = {"OutputUUID": _id(nombre), "Type": "ActionOutput", "OutputName": "Random Number"}
    debut = len(prefixe) + 1
    texte_nom = {"Value": {"string": f"{prefixe}-￼-￼",
                           "attachmentsByRange": {f"{{{debut}, 1}}": date, f"{{{debut + 2}, 1}}": hasard}},
                 "WFSerializationType": "WFTextTokenString"}  # fmt: skip
    return [
        _action("number.random", nombre, WFRandomNumberMinimum=1000, WFRandomNumberMaximum=9999),
        _action("gettext", nom, WFTextActionText=texte_nom),
        _action(
            "setitemname", renomme, WFInput=entree, WFName=_texte([(nom, "Text")]), WFDontIncludeFileExtension=False
        ),  # fmt: skip
        _action(
            "documentpicker.save",
            f"{prefixe}/enregistrer",
            WFInput=_sortie(renomme, "Renamed Item"),
            WFAskWhereToSave=False,
            WFFileDestinationPath="Quotidien/entree/",
            WFSaveFileOverwrite=False,
        ),  # fmt: skip
        _action("repeat.count", None, GroupingIdentifier=_id(boucle), WFControlFlowMode=0, WFRepeatCount=ESSAIS),
        _action("delay", f"{prefixe}/attendre", WFDelayTime=ATTENTE_S),
        _action(
            "documentpicker.open",
            lire,
            WFGetFilePath=_texte(["Quotidien/reponses/", (nom, "Text"), ".txt"]),
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
        _action("showresult", f"{prefixe}/afficher", Text=_texte([(lire, "File")])),
        _action("exit", f"{prefixe}/fin"),
        _action("conditional", None, GroupingIdentifier=_id(si), WFControlFlowMode=2),
        _action("repeat.count", None, GroupingIdentifier=_id(boucle), WFControlFlowMode=2),
        _action("showresult", f"{prefixe}/injoignable", Text=_texte([INJOIGNABLE])),
    ]


def mon_frigo() -> dict[str, Any]:
    menu, photo, galerie, ecrire = "frigo/menu", "frigo/photo", "frigo/galerie", "frigo/ecrire"
    actions = [
        _action(
            "choosefrommenu",
            None,
            GroupingIdentifier=_id(menu),
            WFControlFlowMode=0,
            WFMenuPrompt="Ton frigo :",
            WFMenuItems=list(CHOIX_FRIGO),
        ),  # fmt: skip
        _action(
            "choosefrommenu", None, GroupingIdentifier=_id(menu), WFControlFlowMode=1, WFMenuItemTitle=CHOIX_FRIGO[0]
        ),  # fmt: skip
        _action("takephoto", photo, WFCameraCaptureShowPreview=True),
        _action(
            "choosefrommenu", None, GroupingIdentifier=_id(menu), WFControlFlowMode=1, WFMenuItemTitle=CHOIX_FRIGO[1]
        ),  # fmt: skip
        _action("selectphoto", galerie, WFSelectMultiplePhotos=False),
        _action(
            "choosefrommenu", None, GroupingIdentifier=_id(menu), WFControlFlowMode=1, WFMenuItemTitle=CHOIX_FRIGO[2]
        ),  # fmt: skip
        _action(
            "ask",
            ecrire,
            WFAskActionPrompt="Qu'as-tu dans ton frigo ? (ex. 2 courgettes, feta, un reste de riz)",
            WFInputType="Text",
        ),  # fmt: skip
        _action("choosefrommenu", menu, GroupingIdentifier=_id(menu), WFControlFlowMode=2),
    ]
    actions += _deposer_et_attendre("frigo", _sortie(menu, "Menu Result"))
    return _enveloppe(actions, 59511, 4251333119)


def envie() -> dict[str, Any]:
    question = "envie/question"
    invite = "Envie de quoi pour le prochain menu ? (ex. mexicain et léger)"
    actions = [_action("ask", question, WFAskActionPrompt=invite, WFInputType="Text")]
    actions += _deposer_et_attendre("envie", _sortie(question, "Provided Input"))
    return _enveloppe(actions, 59446, 4292093695)


RACCOURCIS = {MON_FRIGO: mon_frigo, ENVIE: envie}


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


def signer(non_signe: Path, destination: Path) -> tuple[bool, str]:  # pragma: no cover - sur le Mac (testé imité)
    """`shortcuts sign --mode anyone` (sur le Mac, avec un compte iCloud). Remplace seulement notre propre fichier."""
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
    if shutil.which("plutil"):  # pragma: no cover - sur le Mac
        r = subprocess.run(["plutil", "-lint", str(chemin)], capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    try:
        with chemin.open("rb") as f:
            plistlib.load(f)
        return True, f"{chemin}: OK (plistlib)"
    except (plistlib.InvalidFileException, ValueError, OSError) as e:
        return False, str(e)
