"""L'action rapide du Finder et les raccourcis de l'iPhone : fichiers valides, jamais par-dessus un autre."""

from __future__ import annotations

import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.trieur import raccourcis
from modules.trieur.entrees import finder


def test_action_rapide_du_finder(tmp_path):
    services = tmp_path / "Services"
    paquet = finder.installer(services, Path("/Users/moi/Assistant"), Path("/Users/moi/Assistant/.venv/bin/python"))
    assert paquet.name == "Trier avec l'assistant.workflow" and finder.est_a_nous(paquet)
    info = plistlib.loads((paquet / "Contents/Info.plist").read_bytes())
    service = info["NSServices"][0]
    assert service["NSMenuItem"]["default"] == "Trier avec l'assistant" and service["NSSendFileTypes"] == [
        "public.item"
    ]
    flux = plistlib.loads((paquet / "Contents/document.wflow").read_bytes())
    action = flux["actions"][0]["action"]
    script = action["ActionParameters"]["COMMAND_STRING"]
    assert action["ActionParameters"]["inputMethod"] == 1 and action["ActionParameters"]["shell"] == "/bin/zsh"
    assert 'trieur.py ajouter --source finder -- "$@"' in script and "cd /Users/moi/Assistant" in script
    assert flux["workflowMetaData"]["workflowTypeIdentifier"] == "com.apple.Automator.servicesMenu"
    # Réinstaller remplace sa propre version ; un paquet étranger du même nom n'est jamais touché.
    assert finder.installer(services, Path("/autre"), Path("/autre/python")) == paquet
    assert "cd /autre" in plistlib.loads((paquet / "Contents/document.wflow").read_bytes())["actions"][0]["action"][
        "ActionParameters"]["COMMAND_STRING"]  # fmt: skip
    assert finder.desinstaller(services) and not paquet.exists() and not finder.desinstaller(services)
    etranger = services / "Trier avec l'assistant.workflow" / "Contents"
    etranger.mkdir(parents=True)
    (etranger / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.quelquun.autre"}))
    with pytest.raises(FileExistsError):
        finder.installer(services, Path("/x"), Path("/x/python"))
    assert not finder.desinstaller(services) and (etranger / "Info.plist").exists()
    assert "'/chemin avec espace/python'" in finder.commande(Path("/p"), Path("/chemin avec espace/python"))


def test_raccourcis_generes(tmp_path):
    fichiers = raccourcis.ecrire(tmp_path)
    assert [f.name for f in fichiers] == ["Envoie au Mac.non-signé.shortcut", "Envoie au Mac + note.non-signé.shortcut"]
    envoi = plistlib.loads(fichiers[0].read_bytes())
    assert (
        envoi["WFWorkflowTypes"] == ["ActionExtension"]
        and "WFPDFContentItem" in envoi["WFWorkflowInputContentItemClasses"]
    )
    (action,) = envoi["WFWorkflowActions"]
    p = action["WFWorkflowActionParameters"]
    assert action["WFWorkflowActionIdentifier"] == "is.workflow.actions.documentpicker.save"
    assert (
        p["WFFileDestinationPath"] == "BoiteMac/"
        and p["WFSaveFileOverwrite"] is False
        and p["WFAskWhereToSave"] is False
    )
    note = plistlib.loads(fichiers[1].read_bytes())
    ids = [a["WFWorkflowActionIdentifier"].rsplit(".", 1)[-1] for a in note["WFWorkflowActions"]]
    assert ids == ["ask", "getitemname", "dictionary", "setitemname", "save", "save"]
    renommer = note["WFWorkflowActions"][3]["WFWorkflowActionParameters"]
    assert renommer["WFName"]["Value"]["string"] == "￼.meta.json"
    # La note est enregistrée AVANT le document ; les identifiants sont stables.
    assert note["WFWorkflowActions"][4]["WFWorkflowActionParameters"]["WFInput"]["Value"]["Type"] == "ActionOutput"
    assert note["WFWorkflowActions"][5]["WFWorkflowActionParameters"]["WFInput"]["Value"]["Type"] == "ExtensionInput"
    assert raccourcis.envoi_avec_note() == raccourcis.envoi_avec_note()
    assert "BoiteMac" in raccourcis.RECETTE and "6." in raccourcis.RECETTE


def test_signature(tmp_path, monkeypatch):
    (brouillon,) = raccourcis.ecrire(tmp_path)[:1]
    monkeypatch.setattr(raccourcis.shutil, "which", lambda _: None)
    assert raccourcis.signer(brouillon, tmp_path / "s.shortcut")[0] is False
    monkeypatch.setattr(raccourcis.shutil, "which", lambda _: "/usr/bin/shortcuts")
    appels = []

    def faux(cmd, **k):
        appels.append(cmd)
        Path(cmd[cmd.index("--output") + 1]).write_bytes(b"AEA1 signe")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(raccourcis.subprocess, "run", faux)
    assert raccourcis.signer(brouillon, tmp_path / "s.shortcut") == (True, "")
    assert appels[0][:4] == ["shortcuts", "sign", "--mode", "anyone"]
    assert raccourcis.signer(brouillon, tmp_path / "s.shortcut") == (
        False,
        "s.shortcut existe déjà : je n'y touche pas",
    )
    refus = SimpleNamespace(returncode=1, stdout="", stderr="pas connecté à iCloud")
    monkeypatch.setattr(raccourcis.subprocess, "run", lambda cmd, **k: refus)
    assert raccourcis.signer(brouillon, tmp_path / "t.shortcut") == (False, "pas connecté à iCloud")
    monkeypatch.setattr(raccourcis.subprocess, "run", lambda cmd, **k: (_ for _ in ()).throw(OSError("absent")))
    assert raccourcis.signer(brouillon, tmp_path / "u.shortcut") == (False, "absent")
