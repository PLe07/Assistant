"""Les deux corpus, fabriqués une fois puis gardés dans tests/trieur/.cache-corpus (non versionné) : ils sont
refaits dès que le code du générateur change (empreinte de ses fichiers)."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.trieur.corpus.generer import Corpus, generer
from tests.trieur.corpus.generer2 import generer as generer2
from tests.trieur.corpus.modele import Verite

ICI = Path(__file__).resolve().parent
CACHE = ICI.parent / ".cache-corpus"
GENERATEUR = ["contenu.py", "donnees.py", "generer.py", "generer2.py", "modele.py", "rendu.py"]


def empreinte() -> str:
    h = hashlib.sha256()
    for nom in GENERATEUR:
        h.update((ICI / nom).read_bytes())
    return h.hexdigest()[:12]


def corpus_en_cache(nom: str, fabriquer: Callable[[Path], Corpus]) -> Corpus:
    dossier = CACHE / f"{nom}-{empreinte()}"
    if not (dossier / "verite.json").exists():
        for ancien in CACHE.glob(f"{nom}-*"):
            shutil.rmtree(ancien, ignore_errors=True)
        en_cours = CACHE / f"{nom}-en-cours"
        shutil.rmtree(en_cours, ignore_errors=True)
        fabriquer(en_cours)
        en_cours.rename(dossier)
    verites = [Verite(**v) for v in json.loads((dossier / "verite.json").read_text(encoding="utf-8"))]
    return Corpus(dossier, verites)


@pytest.fixture(scope="session")
def corpus1() -> Corpus:
    return corpus_en_cache("corpus1", generer)


@pytest.fixture(scope="session")
def corpus2() -> Corpus:
    return corpus_en_cache("corpus2", generer2)
