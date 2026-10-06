"""§8 et §3.1 : les raccourcis iPhone (plists valides, partage, 60 s d'attente, 5 réflexes embarqués, sans traces
100 % local), les actions rapides du Mac, l'entrée iCloud et la réponse au raccourci."""

from __future__ import annotations

import datetime as dt
import io
import os
import plistlib
from collections.abc import Sequence
from pathlib import Path

import pytest

from bouclier import cli, config, db
from bouclier.arnaque import analyse
from bouclier.arnaque.reponse import reflexes_de_base
from bouclier.entree_icloud import BoiteEntree, dossier_reponses, identifiant
from bouclier.notifier import Notifieur
from bouclier.raccourcis import actions_rapides, generer
from bouclier.systeme import Resultat, Systeme

Boite = tuple[BoiteEntree, analyse.Outils, Notifieur, "Mac", list[float]]
SMS = "Colissimo : votre colis est en attente. Payez 1,99 € : https://colissimo-suivi-frais.top/p"


def _ids(raccourci: dict[str, object]) -> list[str]:
    return [a["WFWorkflowActionIdentifier"] for a in raccourci["WFWorkflowActions"]]  # type: ignore[index, union-attr]


def test_raccourci_arnaque() -> None:
    r = generer.arnaque()
    assert r["WFWorkflowTypes"] == ["ActionExtension"]
    assert {"WFStringContentItem", "WFImageContentItem", "WFURLContentItem"} <= set(
        r["WFWorkflowInputContentItemClasses"]
    )
    ids = _ids(r)
    assert ids[:4] == ["is.workflow.actions.number.random", "is.workflow.actions.gettext",
                       "is.workflow.actions.setitemname", "is.workflow.actions.documentpicker.save"]  # fmt: skip
    actions = r["WFWorkflowActions"]
    enregistrer = actions[3]["WFWorkflowActionParameters"]  # type: ignore[index]
    assert enregistrer["WFFileDestinationPath"] == "Bouclier/entree/" and enregistrer["WFAskWhereToSave"] is False
    boucle = actions[4]["WFWorkflowActionParameters"]  # type: ignore[index]
    attente = actions[5]["WFWorkflowActionParameters"]  # type: ignore[index]
    assert boucle["WFRepeatCount"] * attente["WFDelayTime"] == 60 and attente["WFDelayTime"] == 3
    lire = actions[6]["WFWorkflowActionParameters"]  # type: ignore[index]
    assert (
        lire["WFGetFilePath"]["Value"]["string"] == "Bouclier/reponses/￼.txt" and lire["WFFileErrorIfNotFound"] is False
    )
    assert ids.count("is.workflow.actions.repeat.count") == 2 and ids.count("is.workflow.actions.conditional") == 2
    texte = actions[-2]["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["string"]  # type: ignore[index]
    assert all(reflexe in texte for reflexe in reflexes_de_base()) and len(reflexes_de_base()) == 5
    nom = actions[1]["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]  # type: ignore[index]
    assert nom["string"].startswith("arnaque-") and set(nom["attachmentsByRange"]) == {"{8, 1}", "{10, 1}"}


def test_raccourci_sans_traces_100_pourcent_local() -> None:
    r = generer.sans_traces()
    assert _ids(r) == ["is.workflow.actions.image.convert", "is.workflow.actions.share"]
    convertir = r["WFWorkflowActions"][0]["WFWorkflowActionParameters"]  # type: ignore[index]
    assert convertir["WFImageFormat"] == "JPEG" and convertir["WFImagePreserveMetadata"] is False
    assert "Bouclier" not in repr(r)  # rien ne part vers le Mac


def test_ecrire_lint_et_signer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fichiers = generer.ecrire(tmp_path)
    assert [f.name for f in fichiers] == ["Arnaque ?.non-signé.shortcut", "Envoyer sans traces.non-signé.shortcut"]
    for f in fichiers:
        assert f.read_bytes()[:8] == b"bplist00" and generer.plutil_lint(f)[0]
        with f.open("rb") as entree:
            assert plistlib.load(entree)["WFWorkflowActions"]
    (tmp_path / "abime.shortcut").write_bytes(b"pas un plist")
    monkeypatch.setattr(generer.shutil, "which", lambda nom: None)
    assert not generer.plutil_lint(tmp_path / "abime.shortcut")[0]
    ok, message = generer.signer(fichiers[0], tmp_path / "Arnaque ?.shortcut")
    assert not ok and "shortcuts" in message
    assert generer.installes("Envoie au Mac\nArnaque ?\n") == {"Arnaque ?": True, "Envoyer sans traces": False}


def test_signer_avec_la_commande_shortcuts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    faux = tmp_path / "shortcuts"
    faux.write_text('#!/bin/sh\nentree=""; sortie=""\nwhile [ "$#" -gt 0 ]; do case "$1" in --input) entree="$2";;'
                    ' --output) sortie="$2";; esac; shift; done\ncp "$entree" "$sortie"\n')  # fmt: skip
    faux.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    [arnaque, _] = generer.ecrire(tmp_path / "non-signes")
    destination = tmp_path / "Arnaque ?.shortcut"
    assert generer.signer(arnaque, destination) == (True, "")
    assert destination.read_bytes() == arnaque.read_bytes() and generer.signer(arnaque, destination)[0]


def test_actions_rapides(tmp_path: Path) -> None:
    services = tmp_path / "Services"
    etranger = services / "Nettoyer les métadonnées.workflow" / "Contents"
    etranger.mkdir(parents=True)
    with (etranger / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleIdentifier": "com.quelquun.autre"}, f)
    lanceur = Path("/Users/moi/Projets/bouclier/.venv/bin/bouclier")
    resultats = dict(actions_rapides.installer(services, lanceur))
    assert (
        resultats["Est-ce une arnaque"] == "installée"
        and "n'est pas à Bouclier" in resultats["Nettoyer les métadonnées"]
    )
    texte = services / "Est-ce une arnaque (texte).workflow" / "Contents"
    with (texte / "Info.plist").open("rb") as f:
        info = plistlib.load(f)
    assert info["NSServices"][0]["NSSendTypes"] == ["public.utf8-plain-text"]
    with (texte / "document.wflow").open("rb") as f:
        flux = plistlib.load(f)
    parametres = flux["actions"][0]["action"]["ActionParameters"]
    assert parametres["inputMethod"] == 0 and parametres["COMMAND_STRING"] == f"{lanceur} verifier --fenetre --stdin\n"
    with (services / "Est-ce une arnaque.workflow" / "Contents" / "document.wflow").open("rb") as f:
        assert plistlib.load(f)["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"].endswith('-- "$@"\n')
    assert actions_rapides.etat(services) == {"Est-ce une arnaque": True, "Est-ce une arnaque (texte)": True,
                                               "Nettoyer les métadonnées": False}  # fmt: skip
    assert actions_rapides.installer(services, lanceur)[0] == ("Est-ce une arnaque", "installée")  # relançable
    assert sorted(actions_rapides.desinstaller(services)) == ["Est-ce une arnaque", "Est-ce une arnaque (texte)"]
    assert (etranger / "Info.plist").exists()


# --- L'entrée iCloud -----------------------------------------------------------------------------------------------


class Mac:
    def __init__(self) -> None:
        self.appels: list[list[str]] = []

    def executer(self, args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        self.appels.append(list(args))
        return Resultat(0, "")


@pytest.fixture
def boite(maison: Path) -> Boite:
    c = config.chemins()
    base = db.ouvrir(c.base)
    mac = Mac()
    systeme = Systeme(mac.executer, mac=True)
    t = [dt.datetime(2026, 10, 6, 2, 0).timestamp()]  # en pleine nuit : une réponse à ta demande part quand même
    notifieur = Notifieur(base, systeme, config.charger(), horloge=lambda: t[0])
    return (
        BoiteEntree(c, base, systeme, horloge=lambda: t[0]),
        analyse.Outils(config.charger(), base),
        notifieur,
        mac,
        t,
    )


def test_entree_icloud_et_reponse(boite: Boite) -> None:
    b, outils, notifieur, mac, _ = boite
    c = config.chemins()
    for entree in c.entrees():
        entree.mkdir(parents=True)
    fichier = c.icloud_raccourcis / "entree" / "arnaque-20261006-020000-4242.txt"
    fichier.write_text(SMS, encoding="utf-8")
    assert b.prets() == []  # première vue : on attend que la taille ne bouge plus
    [pret] = b.prets()
    t = b.traiter(pret, outils, notifieur)
    assert t.reponse == c.icloud_raccourcis / "reponses" / "arnaque-20261006-020000-4242.txt"
    reponse = t.reponse.read_text(encoding="utf-8")
    assert reponse.startswith("🔴 Arnaque très probable — faux message « Colissimo »") and "33700" in reponse
    assert any(a[0] == "osascript" for a in mac.appels)  # notification même la nuit : c'est ta demande
    assert b.prets() == [] and fichier.exists()  # traité une seule fois, l'entrée n'est pas touchée
    assert [p.name for p in (c.icloud_raccourcis / "reponses").iterdir()] == ["arnaque-20261006-020000-4242.txt"]


def test_entree_fantome_icloud_et_illisible(
    boite: Boite,
) -> None:
    b, outils, notifieur, mac, t = boite
    c = config.chemins()
    entree = c.icloud / "entree"
    entree.mkdir(parents=True)
    (entree / ".arnaque-1.png.icloud").write_bytes(b"placeholder")
    assert b.prets() == [] and b.prets() == []
    demandes = [a for a in mac.appels if a[:2] == ["brctl", "download"]]
    assert len(demandes) == 1 and demandes[0][2].endswith("entree/arnaque-1.png")
    t[0] += 121
    b.prets()
    assert len([a for a in mac.appels if a[:2] == ["brctl", "download"]]) == 2
    capture = entree / "arnaque-2.png"
    capture.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    b.prets()
    [pret] = b.prets()
    resultat = b.traiter(pret, outils, notifieur)  # pas de lecture d'image ici : réponse claire
    assert resultat.titre == "illisible" and "Je n'ai pas pu lire" in resultat.reponse.read_text(encoding="utf-8")
    assert resultat.reponse.parent == c.icloud / "reponses"


def test_purge_des_copies_de_plus_de_30_jours(
    boite: Boite,
) -> None:
    b, _, _, _, t = boite
    c = config.chemins()
    vieux, recent = c.icloud / "entree" / "vieux.txt", c.icloud / "reponses" / "recent.txt"
    for f in (vieux, recent):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
    os.utime(vieux, (t[0] - 31 * 86400, t[0] - 31 * 86400))
    os.utime(recent, (t[0] - 86400, t[0] - 86400))
    assert b.purger() == 1 and not vieux.exists() and recent.exists()


def test_identifiants() -> None:
    assert identifiant(Path("/x/entree/arnaque-1-2.txt")) == "arnaque-1-2"
    assert identifiant(Path("/x/entree/arnaque-1-2")) == "arnaque-1-2"
    assert dossier_reponses(Path("/i/Bouclier/entree/a.txt")) == Path("/i/Bouclier/reponses")


def test_cli_fenetre_stdin_et_plusieurs_fichiers(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                 monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    mac = Mac()
    systeme = Systeme(mac.executer, mac=True)
    monkeypatch.setattr("sys.stdin", io.StringIO(SMS))
    assert cli.main(["verifier", "--stdin", "--fenetre"], systeme) == 0
    assert "Colissimo" in capsys.readouterr().out
    fenetres = [a for a in mac.appels if a[0] == "osascript" and any("display dialog" in x for x in a)]
    assert fenetres and "Arnaque très probable" in fenetres[-1][-1]
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text(SMS, encoding="utf-8")
    b.write_text("Salut, on mange ensemble demain ?", encoding="utf-8")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    assert cli.main(["verifier", str(a), str(b)], systeme) == 0
    sortie = capsys.readouterr().out
    assert "🔴" in sortie and "⚪" in sortie
