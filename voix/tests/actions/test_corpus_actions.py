"""Les corpus de phrases, exécutés pour de bon sur le faux Mac : un échantillon de chaque intention de chaque jeu.
Aucune exception, aucun paramètre refusé, chaque appel d'une forme permise, et 100 % des actions sensibles passent
par « Tu confirmes ? » avant le moindre appel. Les phrases hors catalogue ne lancent rien."""

from __future__ import annotations

from collections import defaultdict
from types import ModuleType

import pytest

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
from outils.corpus_phrases import Cas
from tests.faux_mac import FauxMac
from tests.securite.appels import appel_conforme
from voix.actions.executeur import MODULES
from voix.nlu.intentions import SENSIBLES
from voix.session import Session

JEUX = [corpus_phrases, corpus_phrases_2, corpus_phrases_3, corpus_phrases_4, corpus_phrases_5, corpus_phrases_6,
        corpus_phrases_7, corpus_phrases_8]  # fmt: skip


def _echantillon(module: ModuleType, par_intention: int) -> list[Cas]:
    vus: dict[str | None, int] = defaultdict(int)
    garde = []
    for c in module.generer():
        if vus[c.intention] < (par_intention if c.intention not in SENSIBLES else 50):
            vus[c.intention] += 1
            garde.append(c)
    return garde


@pytest.mark.parametrize("module", JEUX, ids=[f"jeu {i}" for i in range(1, 9)])
def test_le_corpus_s_execute_proprement(mac: FauxMac, module: ModuleType) -> None:
    maison = mac.maison.resolve()
    mac.regler(mdfind=[str(maison / "Documents" / "Compta.numbers")])
    o = mac.outils(modules=dict.fromkeys(MODULES, ""))
    sensibles = 0
    for cas in _echantillon(module, 2 if module is corpus_phrases else 1):
        s = Session(o)
        if cas.intention in ("fichier.ouvrir_resultat", "fichier.reveler_resultat"):
            s.entendre("cherche compta")  # des résultats pour « ouvre le 2 »
        mac.vider()
        r = s.entendre(cas.phrase)
        assert "Paramètre invalide" not in r.texte, (cas.phrase, r)
        if cas.intention in SENSIBLES:
            sensibles += 1
            assert r.statut == "question", (cas.phrase, r)
            assert mac.appels() == [] and mac.pont.ordres == [], cas.phrase
            r = s.entendre("oui")
        for prog, argv in mac.appels():
            assert appel_conforme(prog, argv, maison), (cas.phrase, prog, argv)
    assert sensibles >= 4


def test_hors_catalogue_ne_lance_rien(mac: FauxMac) -> None:
    o = mac.outils(modules=dict.fromkeys(MODULES, ""))
    for module in JEUX:
        for cas in module.hors_catalogue()[:40]:
            s = Session(o)
            s.entendre(cas.phrase)
            s.entendre("oui")
    assert mac.appels() == [] and mac.pont.ordres == []
