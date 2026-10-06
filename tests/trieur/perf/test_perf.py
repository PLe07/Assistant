"""§9 · Budgets : PDF texte < 3 s, photo de ticket < 8 s ; démon au repos < 0,5 % de processeur, < 150 Mo.

Les temps sont mesurés avec le moteur d'OCR de la machine, sans cache (Vision sur le Mac ; RapidOCR ici, plus lent).
Le démon est mesuré dans un processus à part, avec un dossier Téléchargements de 400 fichiers.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from modules.trieur.classement import classer
from modules.trieur.extraction import extraire, ocr
from tests.trieur.corpus.juge import reglages_du_juge

PROJET = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def moteur():
    m = ocr.choisir()
    if m is None:
        pytest.fail("aucun moteur d'OCR : impossible de mesurer les photos")
    return m


def _duree(chemin: Path, moteur, travail: Path, reglages) -> float:
    debut = time.perf_counter()
    e = extraire(chemin, moteur, travail)
    classer(e.texte, reglages)
    return time.perf_counter() - debut


def test_temps_par_document(corpus1, moteur, tmp_path):
    reglages = reglages_du_juge(tmp_path / "bac")
    pdfs = [v for v in corpus1.verites if v.support == "pdf_texte" and v.type == "facture_achat"][:5]
    photos = [v for v in corpus1.verites if v.support == "photo_ticket"][:3]
    _duree(corpus1.dossier / photos[0].fichier, moteur, tmp_path / "chauffe", reglages)  # chargement du modèle
    temps_pdf = [_duree(corpus1.dossier / v.fichier, moteur, tmp_path / "t", reglages) for v in pdfs]
    temps_photo = [_duree(corpus1.dossier / v.fichier, moteur, tmp_path / "t", reglages) for v in photos]
    print(f"\nPDF texte : max {max(temps_pdf):.2f} s · photo de ticket : max {max(temps_photo):.2f} s ({moteur.nom})")
    assert max(temps_pdf) < 3.0
    assert max(temps_photo) < 8.0


def test_demon_au_repos(tmp_path):
    r = subprocess.run([sys.executable, "-m", "tests.trieur.perf.mesure_demon", str(tmp_path / "bac")], cwd=PROJET,
                       capture_output=True, text=True, timeout=300)  # fmt: skip
    assert r.returncode == 0, r.stderr[-2000:]
    m = json.loads(r.stdout.strip().splitlines()[-1])
    print(f"\ndémon : {m['cpu_par_tour_s'] * 1000:.1f} ms par tour de 2 s = {m['cpu_pct']:.3f} % de processeur ; "
          f"mémoire au repos {m['repos_mo']:.0f} Mo, pic {m['pic_mo']:.0f} Mo")  # fmt: skip
    assert m["ranges"] == 1
    assert m["cpu_pct"] < 0.5
    assert m["repos_mo"] < 150 and m["pic_mo"] < 150
