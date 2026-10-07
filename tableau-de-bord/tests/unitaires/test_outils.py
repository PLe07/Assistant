"""La capture des échantillons réels : copies seulement, rien de personnel dans ce qui est gardé."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from outils import capturer_echantillons as capture
from tableau import caviardage


def test_capture_anonymise_et_ne_touche_pas_aux_originaux(tmp_path: Path) -> None:
    assistant = tmp_path / "Assistant"
    (assistant / "donnees" / "trieur").mkdir(parents=True)
    (assistant / "logs").mkdir()
    db = sqlite3.connect(assistant / "donnees" / "trieur" / "trieur.db", isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE elements (id INTEGER PRIMARY KEY, chemin TEXT, etat TEXT, ajoute REAL, emetteur TEXT, "
               "contenu BLOB)")  # fmt: skip
    db.execute("INSERT INTO elements VALUES (1, '/Users/jean/Documents/impots.pdf', 'classe', 1.5, 'Fnac', x'00')")
    db.execute("CREATE TABLE meta (cle TEXT PRIMARY KEY, valeur TEXT)")
    db.execute("INSERT INTO meta VALUES ('battement', '1791360000.5'), ('adresse', 'jean@example.org'), "
               "('mode', 'rapide')")  # fmt: skip
    db.execute("CREATE INDEX idx ON elements(etat)")
    journal = assistant / "logs" / "assistant.log"
    journal.write_text(
        "2026-10-07 10:00:00 ERROR   [trieur] /Users/jean/Documents/Relevé 2026.pdf : panne\n"
        + "".join(f"2026-10-07 10:00:{i % 60:02d} INFO    [trieur] ligne {i} jean@example.org\n" for i in range(600))
    )
    avant = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (assistant / "donnees" / "trieur").iterdir()}
    sortie = tmp_path / "sortie"
    assert (
        capture.main(["--assistant", str(assistant), "--maison", str(tmp_path / "vide"), "--sortie", str(sortie)]) == 0
    )
    apres = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (assistant / "donnees" / "trieur").iterdir()}
    assert apres == avant
    sql = (sortie / "trieur-trieur.sql").read_text()
    assert "CREATE TABLE elements" in sql and "CREATE INDEX idx" in sql
    assert "'classe'" in sql and "1791360000.5" in sql and "'rapide'" in sql
    assert "jean" not in sql and "impots" not in sql and "Fnac" not in sql
    texte = (sortie / "assistant-assistant.log").read_text()
    assert "ERROR   [trieur]" in texte, "la ligne d'erreur ancienne est gardée, espaces compris"
    assert "jean" not in texte and "Relevé" not in texte and "document.pdf" in texte
    assert not caviardage.contient_sensible(texte + sql)
    # Le SQL se rejoue tel quel.
    rejoue = sqlite3.connect(":memory:")
    rejoue.executescript(sql)
    assert rejoue.execute("SELECT etat FROM elements").fetchone()[0] == "classe"


def test_capture_tolere_une_source_illisible(tmp_path: Path, capsys) -> None:
    maison = tmp_path / "maison"
    support = maison / "Library" / "Application Support" / "Bouclier"
    support.mkdir(parents=True)
    (support / "bouclier.db").write_bytes(b"pas une base")
    ambiance = maison / "Library" / "Logs" / "Ambiance"
    ambiance.mkdir(parents=True)
    (ambiance / "ambiance.log").write_text("2026-10-07 10:00:00 INFO démarrée\n")
    assert capture.main(["--maison", str(maison), "--sortie", str(tmp_path / "s")]) == 0
    sortie = capsys.readouterr().out
    assert "illisible" in sortie and "ambiance" in sortie
    assert (tmp_path / "s" / "ambiance-ambiance.log").exists()


def test_valeurs_anonymisees() -> None:
    assert capture.anonymiser_valeur("etat", "en_attente") == "en_attente"
    assert capture.anonymiser_valeur("etat", "un texte libre très long avec des espaces et plus encore !!") == "[etat]"
    assert capture.anonymiser_valeur("nom", "Facture Fnac") == "[nom]"
    assert capture.anonymiser_valeur("x", 3) == 3 and capture.anonymiser_valeur("x", None) is None
    assert capture.anonymiser_valeur("x", b"\x00") is None
    assert capture.anonymiser_valeur("valeur", "12.5") == "12.5"
    assert capture.anonymiser_valeur("valeur", "court") == "court"
    assert capture.litteral("l'été") == "'l''été'" and capture.litteral(None) == "NULL" and capture.litteral(2) == "2"
