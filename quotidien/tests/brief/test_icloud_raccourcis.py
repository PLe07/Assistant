"""L'échange iPhone ↔ Mac par iCloud (une demande traitée une fois, réponse dans le même dossier, demande effacée)
et les deux raccourcis (« Mon frigo », « Envie de… ») : plists valides, 60 s d'attente, « Mac injoignable »."""

from __future__ import annotations

import os
import plistlib
import time
from pathlib import Path
from typing import Any

import pytest

from quotidien import config, icloud
from quotidien.db import Base as BaseDonnees
from quotidien.raccourcis import generer


@pytest.fixture
def db(maison: Path) -> BaseDonnees:
    icloud.preparer_dossiers()
    return BaseDonnees(config.chemin_base())


def _deposer(racine: Path, nom: str, contenu: bytes | str = "2 courgettes", age: float = 10) -> Path:
    f = racine / "entree" / nom
    f.write_bytes(contenu if isinstance(contenu, bytes) else contenu.encode("utf-8"))
    t = time.time() - age
    os.utime(f, (t, t))
    return f


def test_demandes_des_deux_dossiers_traitees_une_fois(db: BaseDonnees) -> None:
    vus: list[tuple[str, str, bool]] = []

    def frigo(d: icloud.Demande) -> str:
        vus.append((d.id, d.texte() if not d.image else "image", d.image))
        return "1. Poêlée de courgettes"

    icloud_drive, raccourcis = config.dossier_icloud(), config.dossier_icloud_raccourcis()
    _deposer(icloud_drive, "frigo-20261007-193000-4821.txt")
    _deposer(raccourcis, "frigo-20261007-193005-1111.jpg", b"\xff\xd8...")
    _deposer(raccourcis, "envie-20261007-193010-2222.txt", "mexicain")
    _deposer(icloud_drive, "frigo-20261007-193020-3333.txt", age=0.1)  # iCloud écrit encore
    _deposer(icloud_drive, "notes.txt")  # pas une demande
    _deposer(icloud_drive, "frigo-x.txt")  # identifiant trop court
    lien = icloud_drive / "entree" / "frigo-20261007-193030-4444.txt"
    lien.symlink_to(icloud_drive / "entree" / "notes.txt")
    envies: list[str] = []
    n = icloud.traiter(db, {"frigo": frigo, "envie": lambda d: envies.append(d.texte()) or "✅ Envie notée"})
    assert n == 3
    assert sorted(vus) == [("frigo-20261007-193000-4821", "2 courgettes", False),
                           ("frigo-20261007-193005-1111", "image", True)]  # fmt: skip
    assert envies == ["mexicain"]
    # La réponse est dans le même dossier racine que la demande ; la demande est effacée.
    assert (icloud_drive / "reponses" / "frigo-20261007-193000-4821.txt").read_text(encoding="utf-8") == (
        "1. Poêlée de courgettes\n"
    )
    assert (raccourcis / "reponses" / "frigo-20261007-193005-1111.txt").exists()
    assert (raccourcis / "reponses" / "envie-20261007-193010-2222.txt").read_text(encoding="utf-8").startswith("✅")
    assert not (icloud_drive / "entree" / "frigo-20261007-193000-4821.txt").exists()
    assert (icloud_drive / "entree" / "frigo-20261007-193020-3333.txt").exists()
    assert (icloud_drive / "entree" / "notes.txt").exists()
    # La même demande déposée une deuxième fois (iCloud qui resynchronise) : effacée sans être retraitée.
    _deposer(icloud_drive, "frigo-20261007-193000-4821.txt")
    ecrit = icloud_drive / "entree" / "frigo-20261007-193020-3333.txt"
    os.utime(ecrit, (time.time() - 10, time.time() - 10))  # iCloud a fini de l'écrire
    assert icloud.traiter(db, {"frigo": frigo, "envie": frigo}) == 1  # celle qui était en cours d'écriture
    assert len(vus) == 3 and not (icloud_drive / "entree" / "frigo-20261007-193000-4821.txt").exists()
    statuts = {r[0]: r[1] for r in db.lignes("SELECT id, statut FROM demandes")}
    assert set(statuts.values()) == {"ok"} and len(statuts) == 4


def test_demande_abimee_ou_trop_grosse(db: BaseDonnees) -> None:
    racine = config.dossier_icloud()

    def casse(d: icloud.Demande) -> str:
        raise ValueError("abîmée")

    _deposer(racine, "frigo-abimee-0001.txt")
    _deposer(racine, "frigo-enorme-0002.jpg", b"x" * (icloud.TAILLE_MAX + 1))
    assert icloud.traiter(db, {"frigo": casse, "envie": casse}) == 2
    assert "n'a pas réussi" in (racine / "reponses" / "frigo-abimee-0001.txt").read_text(encoding="utf-8")
    assert "trop gros" in (racine / "reponses" / "frigo-enorme-0002.txt").read_text(encoding="utf-8")
    assert {r[0]: r[1] for r in db.lignes("SELECT id, statut FROM demandes")}["frigo-abimee-0001"] == "erreur"


def test_menage_des_reponses(db: BaseDonnees) -> None:
    vieille = config.dossier_icloud() / "reponses" / "frigo-vieille-0001.txt"
    recente = config.dossier_icloud() / "reponses" / "frigo-recente-0002.txt"
    for f in (vieille, recente):
        f.write_text("x", encoding="utf-8")
    t = time.time() - 2 * 86400
    os.utime(vieille, (t, t))
    icloud.nettoyer(time.time())
    assert not vieille.exists() and recente.exists()
    assert icloud.en_attente() == []


def _ids(r: dict[str, Any]) -> list[str]:
    return [a["WFWorkflowActionIdentifier"].removeprefix("is.workflow.actions.") for a in r["WFWorkflowActions"]]


def _parametres(r: dict[str, Any], identifiant: str) -> list[dict[str, Any]]:
    return [a["WFWorkflowActionParameters"] for a in r["WFWorkflowActions"]
            if a["WFWorkflowActionIdentifier"] == f"is.workflow.actions.{identifiant}"]  # fmt: skip


@pytest.mark.parametrize(("fabrique", "prefixe"), [(generer.mon_frigo, "frigo"), (generer.envie, "envie")])
def test_raccourcis_deposent_attendent_60_s_et_disent_injoignable(fabrique: Any, prefixe: str) -> None:
    r = fabrique()
    ids = _ids(r)
    enregistrer = _parametres(r, "documentpicker.save")[0]
    assert enregistrer["WFFileDestinationPath"] == "Quotidien/entree/" and enregistrer["WFAskWhereToSave"] is False
    (boucle, _) = _parametres(r, "repeat.count")
    (attente,) = _parametres(r, "delay")
    assert boucle["WFRepeatCount"] * attente["WFDelayTime"] == 60 and attente["WFDelayTime"] == 3
    (lire,) = _parametres(r, "documentpicker.open")
    assert lire["WFGetFilePath"]["Value"]["string"] == "Quotidien/reponses/￼.txt"
    assert lire["WFFileErrorIfNotFound"] is False
    nom = _parametres(r, "gettext")[0]["WFTextActionText"]["Value"]
    assert nom["string"] == f"{prefixe}-￼-￼" and len(nom["attachmentsByRange"]) == 2
    dernier = _parametres(r, "showresult")[-1]["Text"]["Value"]["string"]
    assert dernier == generer.INJOIGNABLE == "Mac injoignable, réessaie plus tard."
    assert ids.count("conditional") == 2 and ids[-1] == "showresult"
    # Le nom produit correspond à ce que le Mac attend.
    exemple = f"{prefixe}-20261007-193000-4821.txt"
    assert icloud.NOM_DEMANDE.match(exemple)


def test_mon_frigo_photo_galerie_ou_texte() -> None:
    r = generer.mon_frigo()
    ids = _ids(r)
    assert ids[:8] == ["choosefrommenu", "choosefrommenu", "takephoto", "choosefrommenu", "selectphoto",
                       "choosefrommenu", "ask", "choosefrommenu"]  # fmt: skip
    menu = _parametres(r, "choosefrommenu")
    assert menu[0]["WFMenuItems"] == list(generer.CHOIX_FRIGO) and menu[-1]["WFControlFlowMode"] == 2
    assert [m.get("WFMenuItemTitle") for m in menu[1:4]] == list(generer.CHOIX_FRIGO)
    assert len({m["GroupingIdentifier"] for m in menu}) == 1
    renommer = _parametres(r, "setitemname")[0]
    assert renommer["WFInput"]["Value"]["OutputName"] == "Menu Result"


def test_ecrire_et_verifier(tmp_path: Path) -> None:
    fichiers = generer.ecrire(tmp_path)
    assert sorted(f.name for f in fichiers) == ["Envie de….non-signé.shortcut", "Mon frigo.non-signé.shortcut"]
    for f in fichiers:
        ok, message = generer.plutil_lint(f)
        assert ok, message
        with f.open("rb") as h:
            assert plistlib.load(h)["WFWorkflowActions"]
    assert generer.ecrire(tmp_path) == fichiers  # identiques à chaque fois (identifiants stables)
    (tmp_path / "abime.shortcut").write_bytes(b"pas une plist")
    assert not generer.plutil_lint(tmp_path / "abime.shortcut")[0]
