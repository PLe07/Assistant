"""Le juge principal (§9.1) : 5 graines jamais vues pendant le réglage, puis le 2e jeu de corvées.

Critères : rappel ≥ 90 % des corvées plantées dans le top 10, précision ≥ 80 % (au plus 2 fausses alertes),
la corvée refusée ne revient jamais, « Spotify seul » ne sort pas en tête, 0 élément exclu, 0 faux secret.
"""

import pytest

from tests.corvees.simulation.evaluation import evaluer

GRAINES = [101, 202, 303, 404, 505]


@pytest.mark.parametrize("graine", GRAINES)
def test_jeu_a(graine, tmp_path):
    r = evaluer(graine, tmp_path)
    assert r.rappel >= 0.9, f"manquées : {r.manquees}"
    assert r.precision >= 0.8, f"fausses alertes : {r.fausses}"
    assert not r.refusee_revenue, "la corvée refusée est revenue"
    assert not r.spotify_en_tete, "« ouvrir Spotify » (déjà instantané) est dans le top"
    assert r.fuites == [], f"fuites : {r.fuites}"
    assert r.messages_claude == 1  # les candidats sont bien partis chez Claude (imité) et ont été fouillés


@pytest.mark.parametrize("graine", GRAINES)
def test_jeu_b_ecrit_apres_le_reglage(graine, tmp_path):
    """Des corvées toutes différentes (autres applis, dossiers, horaires, sortes) : le moteur doit rester générique."""
    from tests.corvees.simulation.generateur import CORVEES_B

    r = evaluer(graine, tmp_path, corvees=CORVEES_B)
    assert r.rappel >= 0.9, f"manquées : {r.manquees}"
    assert r.precision >= 0.8, f"fausses alertes : {r.fausses}"
    assert not r.refusee_revenue and not r.spotify_en_tete and r.fuites == []
    assert r.messages_claude == 1
