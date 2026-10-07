"""Preuve que les sondes ne font que lire (§1.2, §1.3).

Pendant qu'un faux module tourne (il écrit son journal et sa base WAL), toutes les sondes passent sur ses dossiers.
Un crochet d'audit de Python voit **chaque** ouverture de fichier, connexion SQLite, suppression, renommage, création
de dossier, changement de droits ou de date : rien d'autre qu'une ouverture en lecture seule n'est permis chez lui.
Ensuite : empreintes et dates de tous ses fichiers identiques, aucun fichier en plus, et `lsof` ne montre aucun
fichier à lui resté ouvert par nous.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tableau.db import Base
from tableau.sondes import files_attente, logs, sqlite_copie, tailles

ECRITURE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
EVENEMENTS_INTERDITS = {
    "os.remove", "os.rename", "os.replace", "os.mkdir", "os.chmod", "os.chown", "os.utime", "os.truncate",
    "os.rmdir", "shutil.rmtree", "shutil.move", "shutil.copyfile", "os.link", "os.symlink", "sqlite3.connect",
}  # fmt: skip


class Espion:
    actif = False
    racine: str = ""
    vus: list[tuple[str, tuple[Any, ...]]] = []


def _crochet(evenement: str, args: tuple[Any, ...]) -> None:
    if not Espion.actif:
        return
    if evenement == "open" or evenement in EVENEMENTS_INTERDITS:
        chemins = [a for a in args if isinstance(a, (str, bytes, os.PathLike))]
        if any(str(os.fsdecode(c)).startswith(Espion.racine) for c in chemins):
            Espion.vus.append((evenement, args))


sys.addaudithook(_crochet)


def empreintes(dossier: Path) -> dict[str, tuple[str, int]]:
    return {
        str(p.relative_to(dossier)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in sorted(dossier.rglob("*"))
        if p.is_file()
    }


def test_toutes_les_sondes_ne_font_que_lire(tmp_path: Path, horloge: Any) -> None:
    module = tmp_path / "Assistant"
    (module / "logs").mkdir(parents=True)
    (module / "donnees" / "trieur").mkdir(parents=True)
    boite = tmp_path / "iCloud" / "BoiteMac"
    boite.mkdir(parents=True)
    (boite / "facture.pdf").write_text("x")
    (module / "logs" / "assistant.log").write_text("2026-10-07 10:00:00 ERROR   [trieur] panne\n" * 50)
    (module / "logs" / "assistant.log.1").write_text("2026-10-07 09:00:00 INFO    [trieur] vieux\n")
    base_module = module / "donnees" / "trieur" / "trieur.db"
    ecrivain = sqlite3.connect(base_module, isolation_level=None)
    ecrivain.execute("PRAGMA journal_mode=WAL")
    ecrivain.execute("CREATE TABLE depenses_ia (id INTEGER PRIMARY KEY, quand REAL, mois TEXT, cout_usd REAL)")
    ecrivain.execute("INSERT INTO depenses_ia (quand, mois, cout_usd) VALUES (1, '2026-10', 0.25)")
    avant = empreintes(module) | {f"boite/{k}": v for k, v in empreintes(boite).items()}
    # Notre base et nos copies sont ailleurs (comme sur le Mac : Application Support/TableauDeBord).
    nous = tmp_path / "TableauDeBord"
    base = Base(nous / "tableau.db")
    Espion.racine, Espion.vus, Espion.actif = str(tmp_path / "Assistant"), [], True
    try:
        lecteur = logs.LecteurJournaux(base, horloge)
        for _ in range(3):
            lecteur.nouveau_tour()
            logs.compter(base, "trieur", lecteur.nouvelles_lignes(module / "logs" / "assistant.log"), horloge())
            horloge.avancer(60)
        bases = sqlite_copie.LecteurBases(nous / "copies", intervalle_s=0, horloge=horloge)
        total = bases.lire(
            base_module, "couts", lambda db: db.execute("SELECT SUM(cout_usd) FROM depenses_ia").fetchone()[0]
        )
        assert total == pytest.approx(0.25)
        sqlite_copie.signature(base_module)
        Espion.racine = str(tmp_path)  # la boîte iCloud aussi
        files_attente.mesurer(boite, base, horloge())
        Espion.racine = str(tmp_path / "Assistant")
        assert tailles.taille([module / "donnees", module / "logs"]) > 0
    finally:
        Espion.actif = False
    ecrivain.close()
    interdits = [
        (e, a)
        for e, a in Espion.vus
        if e in EVENEMENTS_INTERDITS
        or (e == "open" and isinstance(a[1], str) and any(c in a[1] for c in "wax+"))
        or (e == "open" and a[1] is None and isinstance(a[2], int) and a[2] & ECRITURE)
    ]
    assert interdits == [], f"écriture ou ouverture interdite chez le module : {interdits}"
    assert any(e == "open" for e, _ in Espion.vus), "l'espion n'a rien vu : le test ne prouverait rien"
    # La base a été fermée par son module (checkpoint) : on compare ce qui ne dépend que de lui.
    apres = empreintes(module) | {f"boite/{k}": v for k, v in empreintes(boite).items()}
    for nom in ("logs/assistant.log", "logs/assistant.log.1", "boite/facture.pdf"):
        assert apres[nom] == avant[nom]
    assert set(apres) <= set(avant) | {"donnees/trieur/trieur.db"}, f"fichiers apparus : {set(apres) - set(avant)}"


def test_lsof_aucun_fichier_d_un_module_reste_ouvert(tmp_path: Path, horloge: Any) -> None:
    """Après chaque lecture, rien chez le module ne reste ouvert par nous (vérifié avec le vrai `lsof`)."""
    if subprocess.run(["which", "lsof"], capture_output=True).returncode != 0:
        pytest.skip("lsof absent")
    module = tmp_path / "module"
    module.mkdir()
    (module / "m.log").write_text("2026-10-07 10:00:00 ERROR x\n")
    db = sqlite3.connect(module / "m.db", isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE t (x)")
    base = Base(tmp_path / "nous" / "tableau.db")
    arret = threading.Event()

    def sonder() -> None:
        lecteur = logs.LecteurJournaux(base, horloge)
        bases = sqlite_copie.LecteurBases(tmp_path / "nous" / "copies", intervalle_s=0, horloge=horloge)
        while not arret.is_set():
            lecteur.nouveau_tour()
            lecteur.nouvelles_lignes(module / "m.log")
            bases.lire(module / "m.db", "n", lambda c: c.execute("SELECT COUNT(*) FROM t").fetchone()[0], forcer=True)
            files_attente.mesurer(module, base, horloge())
            time.sleep(0.05)

    t = threading.Thread(target=sonder)
    t.start()
    try:
        vus: list[str] = []
        for _ in range(5):
            time.sleep(0.3)
            sortie = subprocess.run(["lsof", "-p", str(os.getpid())], capture_output=True, text=True).stdout
            vus += [ligne for ligne in sortie.splitlines() if str(module) in ligne and "m.db" not in ligne]
    finally:
        arret.set()
        t.join()
    db.close()
    # La connexion de l'écrivain (ce test joue aussi le module) tient m.db ouvert : seul le reste compte.
    assert vus == [], f"fichiers du module ouverts par nous : {vus}"
    sortie = subprocess.run(["lsof", "-p", str(os.getpid())], capture_output=True, text=True).stdout
    assert str(module) not in sortie


def test_l_espion_verrait_une_ecriture(tmp_path: Path) -> None:
    """Le crochet d'audit voit bien ce qu'il doit interdire (sinon le premier test ne prouverait rien)."""
    module = tmp_path / "Assistant"
    module.mkdir()
    Espion.racine, Espion.vus, Espion.actif = str(module), [], True
    try:
        with open(module / "x.log", "a") as f:
            f.write("x")
        os.close(os.open(module / "y", os.O_WRONLY | os.O_CREAT, 0o600))
        sqlite3.connect(module / "m.db").close()
        os.utime(module / "y")
        os.remove(module / "y")
    finally:
        Espion.actif = False
    genres = [e for e, _ in Espion.vus]
    assert genres.count("open") >= 2 and {"sqlite3.connect", "os.utime", "os.remove"} <= set(genres)
