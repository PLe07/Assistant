from datetime import datetime
from zoneinfo import ZoneInfo

from modules.corvees import normalize as n

PARIS = ZoneInfo("Europe/Paris")


def ts(*args):
    return datetime(*args, tzinfo=PARIS).timestamp()


def test_jour_et_minute_a_paris():
    t = ts(2026, 10, 3, 8, 30)
    assert n.jour_de(t) == "2026-10-03" and n.minute_du_jour(t) == 8 * 60 + 30
    assert n.jour_semaine(t) == 5 and n.mois_de(t) == "2026-10" and n.semaine(t) == "2026-S40"


def test_minuit_juste_les_jours_de_changement_d_heure():
    # 29 mars 2026 : passage à l'heure d'été (journée de 23 h) ; 25 octobre 2026 : retour (25 h)
    for jour in ((2026, 3, 29), (2026, 10, 25)):
        midi = ts(*jour, 12, 0)
        assert n.debut_du_jour(midi) == ts(*jour, 0, 0)
        assert n.jour_de(n.debut_du_jour(midi)) == "-".join(f"{x:02d}" for x in jour)
    assert ts(2026, 3, 30, 0, 0) - n.debut_du_jour(ts(2026, 3, 29, 12)) == 23 * 3600
    assert ts(2026, 10, 26, 0, 0) - n.debut_du_jour(ts(2026, 10, 25, 12)) == 25 * 3600


def test_la_meme_heure_locale_avant_et_apres_le_changement():
    avant, apres = ts(2026, 10, 24, 8, 30), ts(2026, 10, 26, 8, 30)
    assert n.minute_du_jour(avant) == n.minute_du_jour(apres) == 510
    assert apres - avant == 49 * 3600  # 2 jours + l'heure rendue


def test_instant_du_jour_et_veille():
    t = ts(2026, 10, 25, 23, 0)
    assert n.instant_du_jour(t, "21:00") == ts(2026, 10, 25, 21, 0)
    assert n.jour_de(n.veille(t)) == "2026-10-24"
