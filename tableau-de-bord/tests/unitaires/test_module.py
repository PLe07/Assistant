"""Le modèle commun : chemins d'une fiche, clé d'un problème, état publié."""

from __future__ import annotations

from pathlib import Path

from tableau.module import Attente, DefModule, EtatModule, Pastille, Probleme


def test_chemins_d_une_fiche(tmp_path: Path) -> None:
    d = DefModule(id="trieur", nom="Trieur", dossier_projet="~/Assistant")
    assert d.chemin(None, tmp_path) is None
    assert d.chemin("~", tmp_path) == tmp_path
    assert d.chemin("~/Assistant/logs", tmp_path) == tmp_path / "Assistant" / "logs"
    assert d.chemin("/var/log/x", tmp_path) == Path("/var/log/x")
    assert d.chemin("donnees/trieur", tmp_path) == tmp_path / "Assistant" / "donnees" / "trieur"
    seul = DefModule(id="x", nom="X")
    assert seul.chemin("relatif", tmp_path) == Path("relatif")


def test_cles_et_etat_publie() -> None:
    a = Attente(id="brief", genre="quotidienne", libelle="brief vers 7h15", heure="07:15")
    assert a.cle_preuve == "brief"
    assert Attente(id="x", genre="periodique", libelle="", preuve="gmail").cle_preuve == "gmail"
    p = Probleme("trieur", "file", "attention", "msg", "ok")
    assert p.cle == "trieur:file"
    assert Probleme("trieur", "attente", "attention", "m", "ok", sous_cle="brief").cle == "trieur:attente:brief"
    e = EtatModule(id="trieur", nom="Trieur", emoji="🗂", pastille=Pastille.JAUNE, phrase="2 choses", problemes=[p])
    d = e.en_dict()
    assert d["pastille"] == "jaune" and d["emoji_pastille"] == "🟡" and d["problemes"][0]["genre"] == "file"
