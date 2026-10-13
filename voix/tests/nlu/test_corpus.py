"""Le corpus de phrases (§9.1), avec les seuils de la mission.

- Jeu 1 (généré) : ≥ 1500 phrases, ≥ 300 hors catalogue ; intention ≥ 98 %, paramètres ≥ 96 % ; hors catalogue :
  100 % « pas compris », 0 action ; intentions sensibles : 100 % reconnues comme sensibles (donc confirmées).
- Jeux 2 à 8 (écrits à la main, chacun passé une seule fois à neuf avant de servir au réglage ; leurs premiers
  résultats, honnêtes, sont dans PROGRESS.md) : mêmes seuils, 0 action hors catalogue (un refus ou une négation
  n'est pas une action).
- Les jeux 7 et 8 sont « neufs » : aucune de leurs phrases n'existait dans les jeux d'avant. La clé de comparaison est
  stable (minuscules, sans accents ni ponctuation) ; au moment du passage, la vérification avait été faite sur le texte
  normalisé par la compréhension (plus strict : politesse retirée), voir PROGRESS.md.
"""

from __future__ import annotations

from datetime import datetime
from types import ModuleType

import pytest

from outils import (
    catalogue_reference as ref,
)
from outils import (
    corpus_phrases,
    corpus_phrases_2,
    corpus_phrases_3,
    corpus_phrases_4,
    corpus_phrases_5,
    corpus_phrases_6,
    corpus_phrases_7,
    corpus_phrases_8,
)
from outils.evaluation import Bilan, evaluer
from voix.nlu.approx import forme_normale
from voix.nlu.comprendre import Contexte

ECRITS = [corpus_phrases_2, corpus_phrases_3, corpus_phrases_4, corpus_phrases_5, corpus_phrases_6,
          corpus_phrases_7, corpus_phrases_8]  # fmt: skip


@pytest.fixture(scope="module")
def ctx() -> Contexte:
    return Contexte(ref.catalogue(), ref.commandes(), maintenant=lambda: datetime(2026, 10, 13, 9, 0))


def _bilan(module: ModuleType, ctx: Contexte) -> Bilan:
    return evaluer(module.generer() + module.hors_catalogue(), ctx)


def _seuils(b: Bilan) -> None:
    assert b.taux_intention >= 0.98, (b.resume(), b.echecs_intention[:20])
    assert b.taux_params >= 0.96, (b.resume(), b.echecs_params[:20])
    assert not b.actions_hors_catalogue, b.actions_hors_catalogue
    assert b.sensibles_confirmees == b.sensibles, b.resume()


def test_jeu_1_genere(ctx: Contexte) -> None:
    b = _bilan(corpus_phrases, ctx)
    assert b.n >= 1500 and b.hors_catalogue >= 300
    _seuils(b)
    assert b.hors_catalogue_justes == b.hors_catalogue, b.autres_hors_catalogue
    assert b.sensibles >= 50


@pytest.mark.parametrize("module", ECRITS, ids=[f"jeu {i}" for i in range(2, 9)])
def test_jeux_ecrits_a_la_main(ctx: Contexte, module: ModuleType) -> None:
    b = _bilan(module, ctx)
    assert b.n >= 300 and b.hors_catalogue >= 50
    _seuils(b)


def _textes(module: ModuleType) -> set[str]:
    return {forme_normale(c.phrase) for c in module.generer() + module.hors_catalogue()}


@pytest.mark.parametrize("rang", [7, 8])
def test_les_jeux_7_et_8_etaient_neufs(rang: int) -> None:
    """La mesure anti-triche porte sur ≥ 400 ordres jamais vus : aucune phrase d'un jeu antérieur."""
    tous = [corpus_phrases, *ECRITS]
    avant: set[str] = set().union(*(_textes(m) for m in tous[: rang - 1]))
    jeu = tous[rang - 1]
    ordres = [forme_normale(c.phrase) for c in jeu.generer()]
    assert len(ordres) >= 400 and len(set(ordres)) == len(ordres)
    assert not set(ordres) & avant
    assert not _textes(jeu) & avant
