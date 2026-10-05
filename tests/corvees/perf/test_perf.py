"""§9.5 : 30 jours simulés, au moins 200 000 événements, analysés en moins de 10 secondes."""

import time

from modules.corvees import config
from modules.corvees.detection.moteur import analyser
from tests.corvees.simulation.generateur import generer


def test_trente_jours_200k_evenements_en_moins_de_10_secondes():
    reglages, _ = config.charger({})
    monde = generer(7, jours=30, densite=30)
    assert len(monde.evenements) >= 200_000
    debut = time.perf_counter()
    resultat = analyser(monde.evenements, reglages, maintenant=monde.fin, fin=monde.fin)
    duree = time.perf_counter() - debut
    print(f"\n{len(monde.evenements)} événements analysés en {duree:.1f} s ; {len(resultat)} corvées")
    assert duree < 10, f"{duree:.1f} s"
    assert resultat
