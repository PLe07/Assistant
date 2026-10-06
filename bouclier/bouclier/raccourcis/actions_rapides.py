"""Les entrées du Mac (§3.1, §6) : des paquets Automator dans ~/Library/Services.

- « Est-ce une arnaque ? » : action rapide du Finder sur un fichier (.eml, capture d'écran, .txt) ;
- « Est-ce une arnaque ? » sur du **texte sélectionné** (menu Services de n'importe quelle app) ;
- « Nettoyer les métadonnées » : action rapide du Finder sur des photos, PDF, documents.

Chacune lance la commande `bouclier` du projet et montre le résultat dans une fenêtre. Même structure que l'action
du Trieur (éprouvée sur ce Mac), avec notre propre identifiant : un paquet du même nom qui n'est pas à nous n'est
jamais touché.
"""

from __future__ import annotations

import plistlib
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MARQUE = "fr.bouclier"


@dataclass(frozen=True)
class Action:
    fichier: str  # nom du paquet dans ~/Library/Services
    menu: str  # ce qui s'affiche dans le menu
    texte: bool  # True : texte sélectionné ; False : fichiers du Finder
    arguments: str  # sous-commande de bouclier

    @property
    def identifiant(self) -> str:
        return f"{MARQUE}.{self.fichier.lower().replace(' ', '-').replace('?', '').replace('é', 'e')}"


ACTIONS = (
    Action("Est-ce une arnaque", "Est-ce une arnaque ?", False, "verifier --fenetre --"),
    Action("Est-ce une arnaque (texte)", "Est-ce une arnaque ?", True, "verifier --fenetre --stdin"),
    Action("Nettoyer les métadonnées", "Nettoyer les métadonnées", False, "nettoyer --fenetre --"),
)


def script(action: Action, lanceur: Path) -> str:
    entree = "" if action.texte else ' "$@"'
    return f"{shlex.quote(str(lanceur))} {action.arguments}{entree}\n"


def info_plist(action: Action) -> dict[str, Any]:
    service: dict[str, Any] = {"NSMenuItem": {"default": action.menu}, "NSMessage": "runWorkflowAsService"}
    if action.texte:
        service["NSSendTypes"] = ["public.utf8-plain-text"]
    else:
        service["NSRequiredContext"] = {"NSApplicationIdentifier": "com.apple.finder"}
        service["NSSendFileTypes"] = ["public.item"]
    return {"CFBundleIdentifier": action.identifiant, "CFBundleName": action.menu, "NSServices": [service]}


def document_wflow(action: Action, commande: str) -> dict[str, Any]:
    type_entree = "com.apple.Automator.text" if action.texte else "com.apple.Automator.fileSystemObject"
    acceptes = "com.apple.cocoa.string" if action.texte else "com.apple.cocoa.path"
    a = {
        "AMAccepts": {"Container": "List", "Optional": True, "Types": [acceptes]},
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {
            "COMMAND_STRING": {},
            "CheckedForUserDefaultShell": {},
            "inputMethod": {},
            "shell": {},
            "source": {},
        },  # fmt: skip
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {
            "COMMAND_STRING": commande,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 0 if action.texte else 1,
            "shell": "/bin/zsh",
            "source": "",
        },  # fmt: skip
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": "5B0E3B7A-6C1D-4F2E-8A9B-1C2D3E4F5A61",
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": "7C2F4D9B-8E3A-4B1C-9D0E-2F3A4B5C6D72",
        "UUID": "9E4A6F1C-0B2D-4C3E-8F5A-6B7C8D9E0F83",
        "UnlocalizedApplications": ["Automator"],
        "arguments": {},
        "isViewVisible": 1,
        "location": "309.000000:253.000000",
        "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
    }
    meta: dict[str, Any] = {
        "applicationBundleIDsByPath": {},
        "applicationPaths": [],
        "inputTypeIdentifier": type_entree,
        "outputTypeIdentifier": "com.apple.Automator.nothing",
        "presentationMode": 11 if action.texte else 15,
        "processesInput": False,
        "serviceInputTypeIdentifier": type_entree,
        "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
        "serviceProcessesInput": False,
        "systemImageName": "NSActionTemplate",
        "useAutomaticInputType": False,
        "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
    }
    if not action.texte:
        meta["serviceApplicationBundleID"] = "com.apple.finder"
        meta["serviceApplicationPath"] = "/System/Library/CoreServices/Finder.app"
    return {"AMApplicationBuild": "523", "AMApplicationVersion": "2.10", "AMDocumentVersion": "2",
            "actions": [{"action": a, "isViewVisible": 1}], "connectors": {}, "workflowMetaData": meta}  # fmt: skip


def est_a_nous(paquet: Path) -> bool:
    try:
        with (paquet / "Contents" / "Info.plist").open("rb") as f:
            return str(plistlib.load(f).get("CFBundleIdentifier", "")).startswith(MARQUE + ".")
    except (OSError, plistlib.InvalidFileException, ValueError):
        return False


def installer(services: Path, lanceur: Path) -> list[tuple[str, str]]:
    """[(nom, résultat)] ; une ancienne version de Bouclier est remplacée, un paquet étranger jamais touché."""
    resultats = []
    services.mkdir(parents=True, exist_ok=True)
    for action in ACTIONS:
        paquet = services / f"{action.fichier}.workflow"
        if paquet.exists() and not est_a_nous(paquet):
            resultats.append((action.fichier, "existe déjà et n'est pas à Bouclier : je n'y touche pas"))
            continue
        if paquet.exists():
            shutil.rmtree(paquet)
        contenu = paquet / "Contents"
        contenu.mkdir(parents=True)
        with (contenu / "Info.plist").open("wb") as f:
            plistlib.dump(info_plist(action), f)
        with (contenu / "document.wflow").open("wb") as f:
            plistlib.dump(document_wflow(action, script(action, lanceur)), f)
        resultats.append((action.fichier, "installée"))
    return resultats


def desinstaller(services: Path) -> list[str]:
    retires = []
    for action in ACTIONS:
        paquet = services / f"{action.fichier}.workflow"
        if paquet.exists() and est_a_nous(paquet):
            shutil.rmtree(paquet)
            retires.append(action.fichier)
    return retires


def etat(services: Path) -> dict[str, bool]:
    return {a.fichier: est_a_nous(services / f"{a.fichier}.workflow") for a in ACTIONS}
