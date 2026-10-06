"""§8 · Les deux raccourcis de l'iPhone, dans la feuille de partage (« ActionExtension ») :
- « Envoie au Mac » : le fichier partagé (PDF, photo, capture, page web…) va dans iCloud Drive/BoiteMac ;
- « Envoie au Mac + note » : il demande d'abord une note (« garantie 3 ans »), écrite dans « <nom>.meta.json »
  AVANT le document (pour qu'elle soit là quand le Mac le voit).

Les fichiers .shortcut sont des listes de propriétés (plist) ; `trieur installer` les signe sur le Mac
(`shortcuts sign --mode anyone`) et les dépose dans la boîte iCloud : sur l'iPhone, Fichiers → BoiteMac → toucher
le raccourci pour l'ajouter. Si la signature échoue, la recette manuelle (6 étapes) est dans ACTIONS_HUMAINES.md.

Le format des dossiers iCloud dans un raccourci ne peut pas être vérifié sans Mac : le chemin relatif
« BoiteMac/ » enregistre dans iCloud Drive/Shortcuts/BoiteMac, que le Trieur surveille aussi (D-12).
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

ENVOI = "Envoie au Mac"
ENVOI_NOTE = "Envoie au Mac + note"
QUESTION = "Une note pour le Mac ? (ex. garantie 3 ans)"
TYPES_ACCEPTES = ["WFAppStoreAppContentItem", "WFArticleContentItem", "WFContactContentItem", "WFDateContentItem",
                  "WFEmailAddressContentItem", "WFGenericFileContentItem", "WFImageContentItem",
                  "WFiTunesProductContentItem", "WFLocationContentItem", "WFDCMapsLinkContentItem",
                  "WFAVAssetContentItem", "WFPDFContentItem", "WFPhoneNumberContentItem", "WFRichTextContentItem",
                  "WFSafariWebPageContentItem", "WFStringContentItem", "WFURLContentItem"]  # fmt: skip


def _id(graine: str) -> str:
    """Des identifiants stables (le même raccourci donne le même fichier)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"trieur/{graine}")).upper()


def _entree_du_partage() -> dict[str, Any]:
    return {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"}


def _sortie(action: str, nom: str) -> dict[str, Any]:
    return {"Value": {"OutputUUID": _id(action), "Type": "ActionOutput", "OutputName": nom},
            "WFSerializationType": "WFTextTokenAttachment"}  # fmt: skip


def _texte_avec(action: str, nom: str, avant: str = "", apres: str = "") -> dict[str, Any]:
    """Un texte qui contient la sortie d'une action : « avant<sortie>apres »."""
    position = len(avant)
    return {"Value": {"string": f"{avant}￼{apres}",
                      "attachmentsByRange": {f"{{{position}, 1}}": {"OutputUUID": _id(action), "Type": "ActionOutput",
                                                                     "OutputName": nom}}},
            "WFSerializationType": "WFTextTokenString"}  # fmt: skip


def _enregistrer(entree: dict[str, Any], graine: str) -> dict[str, Any]:
    parametres = {"UUID": _id(graine), "WFInput": entree, "WFAskWhereToSave": False,
                  "WFFileDestinationPath": "BoiteMac/", "WFSaveFileOverwrite": False}  # fmt: skip
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.documentpicker.save",
            "WFWorkflowActionParameters": parametres}  # fmt: skip


def _enveloppe(actions: list[dict[str, Any]], glyphe: int, couleur: int) -> dict[str, Any]:
    return {
        "WFWorkflowClientVersion": "2302.0.4",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": couleur, "WFWorkflowIconGlyphNumber": glyphe},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": TYPES_ACCEPTES,
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowHasShortcutInputVariables": True,
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": actions,
    }


def envoi() -> dict[str, Any]:
    """« Envoie au Mac » : une seule action, enregistrer l'entrée dans BoiteMac (sans question, sans écraser)."""
    return _enveloppe([_enregistrer(_entree_du_partage(), "envoi/enregistrer")], 59511, 4282601983)


def envoi_avec_note() -> dict[str, Any]:
    a = "note/demander"
    nom = "note/nom"
    dico = "note/dictionnaire"
    renomme = "note/renommer"
    actions = [
        {"WFWorkflowActionIdentifier": "is.workflow.actions.ask",
         "WFWorkflowActionParameters": {"UUID": _id(a), "WFAskActionPrompt": QUESTION, "WFInputType": "Text",
                                        "WFAskActionDefaultAnswer": ""}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.getitemname",
         "WFWorkflowActionParameters": {"UUID": _id(nom), "WFInput": _entree_du_partage()}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.dictionary",
         "WFWorkflowActionParameters": {"UUID": _id(dico), "WFItems": {"Value": {"WFDictionaryFieldValueItems": [
             {"WFItemType": 0, "WFKey": {"Value": {"string": "note", "attachmentsByRange": {}},
                                         "WFSerializationType": "WFTextTokenString"},
              "WFValue": _texte_avec(a, "Provided Input")}]}, "WFSerializationType": "WFDictionaryFieldValue"}}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.setitemname",
         "WFWorkflowActionParameters": {"UUID": _id(renomme), "WFInput": _sortie(dico, "Dictionary"),
                                        "WFName": _texte_avec(nom, "Name", apres=".meta.json"),
                                        "WFDontIncludeFileExtension": True}},
        _enregistrer(_sortie(renomme, "Renamed Item"), "note/enregistrer-note"),
        _enregistrer(_entree_du_partage(), "note/enregistrer-document"),
    ]  # fmt: skip
    return _enveloppe(actions, 59446, 4251333119)


def ecrire(dossier: Path) -> list[Path]:
    """Les deux raccourcis, non signés (format binaire, comme ceux de l'app Raccourcis)."""
    dossier.mkdir(parents=True, exist_ok=True)
    sortie = []
    for nom, contenu in ((ENVOI, envoi()), (ENVOI_NOTE, envoi_avec_note())):
        chemin = dossier / f"{nom}.non-signé.shortcut"
        with chemin.open("wb") as f:
            plistlib.dump(contenu, f, fmt=plistlib.FMT_BINARY)
        sortie.append(chemin)
    return sortie


def signer(non_signe: Path, destination: Path) -> tuple[bool, str]:
    """`shortcuts sign --mode anyone` (sur le Mac, avec iCloud) ; jamais par-dessus un fichier existant."""
    if not shutil.which("shortcuts"):
        return False, "la commande « shortcuts » n'existe pas ici (macOS 12 ou plus)"
    if destination.exists():
        return False, f"{destination.name} existe déjà : je n'y touche pas"
    try:
        r = subprocess.run(["shortcuts", "sign", "--mode", "anyone", "--input", str(non_signe), "--output",
                            str(destination)], capture_output=True, text=True, timeout=120)  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if r.returncode != 0 or not destination.exists():
        return False, (r.stderr or r.stdout).strip()[:300] or "échec de la signature"
    return True, ""


RECETTE = """Si les raccourcis ne s'importent pas, crée « Envoie au Mac » à la main sur l'iPhone (2 minutes) :
1. App Raccourcis → onglet Raccourcis → « + » en haut à droite.
2. Touche le nom en haut → Renommer → « Envoie au Mac ».
3. Touche le « i » (Détails) → active « Afficher dans la feuille de partage » → OK.
4. Ajoute l'action « Enregistrer le fichier » (recherche « Enregistrer »).
5. Dans cette action : touche « Entrée du raccourci » si besoin, désactive « Demander où enregistrer », choisis le
   dossier iCloud Drive › BoiteMac (crée-le s'il n'existe pas), laisse « Remplacer » désactivé.
6. Touche « OK ». Essai : dans Photos, Partager → « Envoie au Mac ».
(Version avec note : ajoute avant l'étape 4 « Demander une saisie » (texte), puis « Dictionnaire » avec la clé note,
« Renommer » en « <nom>.meta.json » et « Enregistrer le fichier » dans BoiteMac.)"""
