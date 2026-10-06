"""Les critères du corpus (§10.1), sans Claude : le classement local seul.

Corpus 1 (celui du réglage) : type ≥ 95 % (PDF texte) et ≥ 85 % (scans, photos), date ≥ 95 %, montant ≥ 90 %,
fin de garantie 100 %, aucune fausse garantie, tous les pièges bien aiguillés.
Corpus 2 (écrit après le réglage, jamais vu) : les mêmes seuils, 10 points plus bas ; toujours aucune fausse garantie.
"""

from __future__ import annotations

import pytest

from tests.trieur.corpus.juge import juger, moteur_des_tests

SEUILS = {"type_texte": 95.0, "type_image": 85.0, "date": 95.0, "montant": 90.0, "garantie": 100.0}


def _verifier(bilan, seuils: dict[str, float]) -> None:
    print("\n" + bilan.tableau())
    rates = {k: round(bilan.taux(k), 1) for k, s in seuils.items() if bilan.taux(k) < s}
    assert not rates, f"sous le seuil : {rates}\n" + "\n".join(sorted(bilan.erreurs))
    assert bilan.total["fausse_garantie"] == 0, "\n".join(e for e in bilan.erreurs if "fausse" in e)


@pytest.fixture(scope="module")
def moteur():
    m = moteur_des_tests()
    if m is None:
        pytest.fail("aucun moteur d'OCR ici (ni Vision, ni tesseract, ni RapidOCR) : les scans ne peuvent être mesurés")
    return m


def test_corpus_principal(corpus1, moteur, tmp_path):
    bilan = juger(corpus1.dossier, moteur, tmp_path)
    _verifier(bilan, SEUILS)
    assert bilan.taux("pieges") == 100.0, "\n".join(e for e in bilan.erreurs if e.startswith("pieges"))


def test_second_corpus_inedit(corpus2, moteur, tmp_path):
    bilan = juger(corpus2.dossier, moteur, tmp_path)
    _verifier(bilan, {k: v - 10 for k, v in SEUILS.items()})
