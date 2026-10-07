"""La base (chmod 600, base corrompue mise de côté), le journal caviardé, le caviardage."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from quotidien import caviardage, config, journal
from quotidien.db import Base


def test_base_creee_en_600(tmp_path: Path) -> None:
    b = Base(tmp_path / "s" / "q.db")
    assert stat.S_IMODE((tmp_path / "s" / "q.db").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "s").stat().st_mode) == 0o700
    b.ecrire_meta("a", "1")
    b.ecrire_meta("a", "2")
    assert b.lire_meta("a") == "2" and b.lire_meta("absent", "x") == "x"
    b.ecrire_json("j", {"z": [1, "é"]})
    assert b.lire_json("j") == {"z": [1, "é"]} and b.lire_json("absent") is None
    b.ecrire_meta("casse", "{pas du json")
    assert b.lire_json("casse") is None
    b.fermer()


def test_base_droits_corriges(tmp_path: Path) -> None:
    Base(tmp_path / "q.db").fermer()
    (tmp_path / "q.db").chmod(0o644)
    Base(tmp_path / "q.db").fermer()
    assert stat.S_IMODE((tmp_path / "q.db").stat().st_mode) == 0o600


def test_base_corrompue_mise_de_cote(tmp_path: Path) -> None:
    chemin = tmp_path / "q.db"
    chemin.write_bytes(b"ceci n'est pas une base SQLite" * 100)
    b = Base(chemin)
    assert b.corrompue_mise_de_cote is not None and b.corrompue_mise_de_cote.exists()
    b.ecrire_meta("ok", "1")
    assert b.lire_meta("ok") == "1"
    assert stat.S_IMODE(chemin.stat().st_mode) == 0o600


def test_transaction_annulee(tmp_path: Path) -> None:
    b = Base(tmp_path / "q.db")
    with pytest.raises(RuntimeError):
        with b.transaction() as cx:
            cx.execute("INSERT INTO meta(cle, valeur) VALUES ('x', 'y')")
            raise RuntimeError("non")
    assert b.lire_meta("x") is None
    assert b.lignes("SELECT COUNT(*) AS n FROM meta")[0]["n"] == 0


@pytest.mark.parametrize(
    "texte,absent",
    [
        ("appelle-moi au 06 12 34 56 78 stp", "06 12 34 56 78"),
        ("mon numéro +33 6 12 34 56 78", "6 12 34 56 78"),
        ("écris à lea.dupont@gmail.com", "lea.dupont@gmail.com"),
        ("elle habite 12 rue des Lilas, à côté", "rue des Lilas"),
        ("33000 Bordeaux", "33000"),
        ("FR76 3000 6000 0112 3456 7890 189", "3000 6000"),
        ("carte 4970 1012 3456 7890", "4970 1012"),
        ("voir https://exemple.fr/x", "exemple.fr"),
    ],
)
def test_caviarder(texte: str, absent: str) -> None:
    assert absent not in caviardage.caviarder(texte)


def test_caviarder_laisse_le_texte_ordinaire() -> None:
    t = "Souvenir : voyage à Lisbonne en 2023, adore le foot (18 ans)"
    assert caviardage.caviarder(t) == t
    assert caviardage.caviarder("") == ""


def test_noms_retires() -> None:
    t = caviardage.noms_retires("Léa Martin-Durand adore les MARTIN-DURAND et 06 11 22 33 44", ["Martin-Durand", ""])
    assert "Martin-Durand" not in t and "MARTIN" not in t and "06 11" not in t
    assert t.startswith("Léa [nom]")


def test_journal_caviarde(maison: Path) -> None:
    journal.log().info("contact 06 12 34 56 78 et lea@exemple.fr")
    journal.log().info("deuxième appel, même journal")
    contenu = (config.dossier_logs() / "quotidien.log").read_text(encoding="utf-8")
    assert "06 12" not in contenu and "lea@exemple.fr" not in contenu and "[téléphone]" in contenu
    assert stat.S_IMODE(config.dossier_logs().stat().st_mode) == 0o700


def test_journal_sans_dossier_possible(maison: Path) -> None:
    (maison / "Library").write_text("un fichier à la place du dossier")
    journal.oublier()
    journal.log().info("rien ne casse")
