"""§9.2, 2e faux Mac : tiré au hasard, 5 graines. Mêmes critères que le faux Mac n° 1."""

import pytest

from tests.demarrage.faux_mac.aleatoire import construire_aleatoire
from tests.demarrage.faux_mac.juge import diagnostiquer, juger

GRAINES = [3, 17, 42, 1789, 20261005]


@pytest.mark.parametrize("graine", GRAINES)
def test_faux_mac_aleatoire(tmp_path, reglages, graine):
    faux = construire_aleatoire(tmp_path / "mac", graine)
    bilan = diagnostiquer(faux, tmp_path, reglages)
    j = juger(faux, bilan)
    plantes = sum(1 for a in faux.verite.values() if a.verdict != "apple")
    apple = sum(1 for a in faux.verite.values() if a.verdict == "apple")
    bons = sum(1 for _, attendu, obtenu, *_ in j.lignes if attendu == obtenu)
    print(f"\n   graine {graine} : {bons}/{len(j.lignes)} verdicts justes ({plantes} plantés, {apple} Apple)")
    assert j.reussi, "\n".join(j.erreurs)
    assert apple >= 15
