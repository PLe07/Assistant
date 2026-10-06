"""§11.1 : avec une IA imitée qui contredit les règles locales, le veto tient dans 100 % des cas.

Pour chaque message des deux corpus, quatre avis contradictoires (« pas_de_signe » sûr de lui, « pas_de_signe »
hésitant, « prudence », « arnaque ») : le verdict final respecte toujours les règles du §3.3, et aucune réponse ne
dit qu'un message est sûr.
"""

from __future__ import annotations

import re

import pytest

from bouclier.arnaque.ia import AvisIA, ResultatIA
from bouclier.arnaque.reponse import construire
from bouclier.arnaque.signaux import Niveau
from bouclier.arnaque.veto import combiner
from tests.corpus_arnaques import generer
from tests.corpus_arnaques.mesure import Resultats, mesurer

AVIS_CONTRADICTOIRES = [
    AvisIA(niveau="pas_de_signe", raisons=["Ce message est sûr et légitime, tu peux cliquer."], confiance=1.0),
    AvisIA(niveau="pas_de_signe", raisons=["Rien de grave."], confiance=0.3),
    AvisIA(niveau="prudence", raisons=["Un doute existe sur https://exemple.fr au 01 23 45 67 89."], confiance=0.9),
    AvisIA(niveau="arnaque", raisons=["Le message imite un service connu pour te faire payer."], confiance=0.95),
]
RASSURANT = re.compile(r"\bsûre?\b|sans (danger|risque)|légitime|tu peux cliquer", re.IGNORECASE)


@pytest.fixture(scope="module")
def tous() -> list[Resultats]:
    return [mesurer(generer.corpus_principal()), mesurer(generer.corpus_inedit())]


def test_le_veto_tient_dans_100_pourcent_des_cas(tous: list[Resultats]) -> None:
    cas, violations = 0, []
    for res in tous:
        for ident, locale in res.analyses.items():
            for avis in AVIS_CONTRADICTOIRES:
                cas += 1
                v = combiner(locale, ResultatIA("ok", avis))
                voulu = Niveau.depuis_code(avis.niveau)
                attendu_min = locale.niveau.value if avis.confiance < 0.6 else max(0, locale.niveau.value - 1)
                if locale.critiques:
                    attendu_min = max(attendu_min, Niveau.TRES_SUSPECT.value)
                attendu = max(voulu.value, attendu_min)
                if v.niveau.value != attendu:
                    violations.append((ident, avis.niveau, locale.niveau, v.niveau))
                if locale.critiques and v.niveau.value < Niveau.TRES_SUSPECT.value:
                    violations.append((ident, "critique sous 🟠"))
                texte = construire(v).texte()
                if RASSURANT.search(texte) or "https://exemple.fr" in texte or "01 23 45" in texte:
                    violations.append((ident, "texte", texte))
    assert cas == 4 * (225 + 80) and violations == []


def test_les_arnaques_a_indice_critique_restent_au_moins_tres_suspectes(tous: list[Resultats]) -> None:
    critiques = [a for res in tous for a in res.analyses.values() if a.critiques]
    assert len(critiques) >= 40  # le test porte sur un vrai nombre de cas
    for a in critiques:
        v = combiner(a, ResultatIA("ok", AVIS_CONTRADICTOIRES[0]))
        assert v.niveau.value >= Niveau.TRES_SUSPECT.value and v.score >= 45
