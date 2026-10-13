"""Le démarrage sur le Mac (catalogue lu en lecture seule, modules trouvés par `which`) et les commandes
`voix comprendre`, `voix journal`, `voix oublier`."""

from __future__ import annotations

import plistlib
from datetime import datetime
from pathlib import Path

import pytest

from tests.faux_mac import FauxMac
from voix import cli, config, demarrage
from voix.actions.executeur import Executeur, ProgrammeRefuse
from voix.journal import Journal
from voix.nlu.comprendre import Choix, Comprehension
from voix.session import Session


def _app(dossier: Path, nom: str, bundle: str) -> None:
    contenu = dossier / f"{nom}.app" / "Contents"
    contenu.mkdir(parents=True)
    (contenu / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": bundle, "CFBundleName": nom}))


def _demarrer(mac: FauxMac) -> demarrage.Outils:
    _app(mac.maison / "Applications", "Notion", "notion.id")
    (mac.racine / "README.md").write_text("ambiance mode focus\nambiance mode code\n")
    chemins = config.Chemins(mac.maison)
    chemins.commandes.parent.mkdir(parents=True)
    chemins.commandes.write_text('[[alias]]\nnom = "la compta"\ncible = "~/Documents/Compta.numbers"\n')
    mac.regler(raccourcis=["Heure du café", "Mode lecture"])
    x = mac.outils().executeur
    return demarrage.outils(chemins, config.charger(chemins), mac.pont, x)


def test_le_demarrage_lit_le_mac_sans_rien_changer(mac: FauxMac) -> None:
    o = _demarrer(mac)
    genres = {(ob.genre, ob.nom) for ob in o.catalogue.objets}
    assert ("app", "Notion") in genres and ("raccourci", "Heure du café") in genres and ("alias", "la compta") in genres
    assert ("dossier", "Téléchargements") in genres and any(g == "site" for g, _ in genres)
    assert set(o.modules) == {"tableau", "ambiance", "quotidien", "bouclier"}
    assert o.modes_ambiance == {"code": "code", "focus": "focus"}
    assert {prog for prog, _ in mac.appels()} == {"mdfind", "shortcuts"}  # des lectures, rien d'autre
    assert [argv for prog, argv in mac.appels() if prog == "shortcuts"] == [["list"]]
    s = Session(o)
    mac.vider()
    s.entendre("ouvre Notion")
    s.entendre("lance le raccourci Heure du café")
    s.entendre("ouvre la compta")
    s.entendre("mode code")
    assert mac.appels() == [("open", ["-b", "notion.id"]), ("shortcuts", ["run", "Heure du café"]),
                            ("open", [str(mac.maison / "Documents" / "Compta.numbers")]),
                            ("ambiance", ["mode", "code"])]  # fmt: skip


def test_un_lecteur_refuse_ce_qui_n_est_pas_dans_la_liste(tmp_path: Path) -> None:
    lire = demarrage.lecteur(Executeur([str(tmp_path)], []))
    assert lire(["rm", "-rf", "/"], 1) == (127, "")
    assert lire(["mdfind", "x"], 1) == (127, "")  # absent : rien lancé
    with pytest.raises(ProgrammeRefuse):
        Executeur([str(tmp_path)]).lancer("rm", ["-rf", "/"])


@pytest.fixture
def maison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("VOIX_MAISON", str(tmp_path))
    monkeypatch.setattr(demarrage, "outils", _outils_reference)
    return tmp_path


def _outils_reference(chemins: config.Chemins, reglages: config.Reglages) -> demarrage.Outils:
    from outils import catalogue_reference as ref

    return demarrage.Outils(Executeur([], []), chemins, reglages, ref.catalogue(maison=chemins.maison),
                            ref.commandes(chemins.maison), modules={"ambiance": "/x/ambiance"})  # fmt: skip


@pytest.mark.parametrize(
    ("phrase", "code", "attendu"),
    [
        (["ouvre", "Notion"], 0, ["Compris : ", "[app.ouvrir]", "objet : Notion (app)"]),
        (["ferme", "tout"], 0, ["[app.fermer_tout]", "⚠️ action sensible"]),
        (["mets le volume à 30"], 0, ["[son.regler]", "niveau : 30"]),
        (["éteins le Mac"], 1, ["Refus : Je ne fais pas ça, par sécurité."]),
        (["n'ouvre pas Safari"], 1, ["Rien à faire"]),
        (["euh"], 1, ["Rien entendu."]),
        (["la soupe de ma grand-mère"], 1, ["Pas compris."]),
    ],
)
def test_cli_comprendre(
    maison: Path, capsys: pytest.CaptureFixture[str], phrase: list[str], code: int, attendu: list[str]
) -> None:
    assert cli.main(["comprendre", *phrase]) == code
    sortie = capsys.readouterr().out
    for morceau in attendu:
        assert morceau in sortie, sortie


def test_decrire_une_hesitation_et_des_suggestions() -> None:
    notes, notion = (Comprehension("compris", "app.ouvrir") for _ in range(2))
    c = Comprehension("ambigu", "app.ouvrir", choix=[Choix("Notes", notes), Choix("Notion", notion)],
                      raison="Notes ou Notion ?")  # fmt: skip
    assert cli.decrire(c) == ["Hésitation : Notes ou Notion ?", "  - Notes", "  - Notion"]
    c = Comprehension("pas_compris", suggestions=["ouvre Notion", "ouvre Notes"])
    assert cli.decrire(c) == ["Pas compris.", "  Essaie : « ouvre Notion » ; « ouvre Notes »"]


def test_cli_journal_et_oublier(maison: Path, capsys: pytest.CaptureFixture[str]) -> None:
    chemins = config.Chemins(maison)
    assert cli.main(["journal"]) == 0 and "Journal vide." in capsys.readouterr().out
    j = Journal(chemins.journal)
    j.ajouter("ouvre Notion", "app.ouvrir", "fait", "✓ Notion ouvert", datetime(2026, 10, 13, 9, 5))
    j.ajouter("appelle le 06 12 34 56 78", None, "incompris", "Je n'ai pas compris.", datetime(2026, 10, 13, 9, 6))
    assert cli.main(["journal"]) == 0
    sortie = capsys.readouterr().out
    assert "2026-10-13 09:05  « ouvre Notion » → fait : ✓ Notion ouvert" in sortie
    assert "[nombre]" in sortie and "06 12" not in sortie
    assert chemins.journal.stat().st_mode & 0o777 == 0o600
    assert cli.main(["oublier"]) == 0 and "Journal effacé." in capsys.readouterr().out
    assert not chemins.journal.exists()
    assert cli.main(["oublier"]) == 0 and "Journal déjà vide." in capsys.readouterr().out


def test_cli_journal_desactive(maison: Path, capsys: pytest.CaptureFixture[str]) -> None:
    chemins = config.Chemins(maison)
    chemins.preparer()
    chemins.reglages.write_text("[journal]\nactif = false\n")
    assert cli.main(["journal"]) == 0
    assert "Journal désactivé" in capsys.readouterr().out
