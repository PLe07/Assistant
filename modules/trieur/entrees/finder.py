"""E3 · L'action rapide du Finder « Trier avec l'assistant » (clic droit sur des fichiers → Actions rapides).

C'est un petit paquet Automator (~/Library/Services/Trier avec l'assistant.workflow) qui lance
`trieur.py ajouter --source finder <fichiers>` avec le Python de l'Assistant. Il est écrit par
`trieur installer`, jamais par-dessus un fichier existant qui ne serait pas le sien.
"""

from __future__ import annotations

import plistlib
import shlex
import shutil
from pathlib import Path
from typing import Any

NOM = "Trier avec l'assistant"
MARQUE = "fr.assistant.trieur"


def commande(projet: Path, python: Path) -> str:
    """Le script zsh de l'action : les fichiers arrivent en arguments ($@)."""
    return (f"cd {shlex.quote(str(projet))} || exit 1\n"
            f"{shlex.quote(str(python))} trieur.py ajouter --source finder -- \"$@\" "
            f">> {shlex.quote(str(projet / 'logs' / 'trieur-finder.log'))} 2>&1\n")  # fmt: skip


def info_plist() -> dict[str, Any]:
    return {
        "CFBundleIdentifier": MARQUE + ".finder",
        "CFBundleName": NOM,
        "NSServices": [
            {
                "NSMenuItem": {"default": NOM},
                "NSMessage": "runWorkflowAsService",
                "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
                "NSSendFileTypes": ["public.item"],
            }
        ],
    }


def document_wflow(script: str) -> dict[str, Any]:
    """Le flux Automator : une seule action « Exécuter un script shell », entrée en arguments, zsh."""
    action = {
        "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.path"]},
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
            "COMMAND_STRING": script,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 1,
            "shell": "/bin/zsh",
            "source": "",
        },  # fmt: skip
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": "6A1C8C59-3E1B-4B5E-9D6E-2C4E0B6E7A11",
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": "0F4E6B1D-8C2A-4E0F-B7A3-5D9C1E2F3A44",
        "UUID": "C3D2B1A0-9F8E-4D7C-A6B5-4E3D2C1B0A99",
        "UnlocalizedApplications": ["Automator"],
        "arguments": {},
        "isViewVisible": 1,
        "location": "309.000000:253.000000",
        "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
    }
    return {
        "AMApplicationBuild": "523",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{"action": action, "isViewVisible": 1}],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {},
            "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def est_a_nous(paquet: Path) -> bool:
    try:
        with (paquet / "Contents" / "Info.plist").open("rb") as f:
            return str(plistlib.load(f).get("CFBundleIdentifier", "")).startswith(MARQUE)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return False


def installer(services: Path, projet: Path, python: Path) -> Path:
    """Écrit l'action dans « services » (~/Library/Services). Une ancienne version du Trieur est remplacée ;
    un paquet du même nom qui n'est pas le sien n'est jamais touché."""
    paquet = services / f"{NOM}.workflow"
    if paquet.exists():
        if not est_a_nous(paquet):
            raise FileExistsError(f"{paquet} existe déjà et n'est pas l'action du Trieur : je n'y touche pas")
        shutil.rmtree(paquet)
    contenu = paquet / "Contents"
    contenu.mkdir(parents=True)
    with (contenu / "Info.plist").open("wb") as f:
        plistlib.dump(info_plist(), f)
    with (contenu / "document.wflow").open("wb") as f:
        plistlib.dump(document_wflow(commande(projet, python)), f)
    return paquet


def desinstaller(services: Path) -> bool:
    paquet = services / f"{NOM}.workflow"
    if paquet.exists() and est_a_nous(paquet):
        shutil.rmtree(paquet)
        return True
    return False
