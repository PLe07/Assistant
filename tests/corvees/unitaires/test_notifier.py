"""La notification du soir : une par jour au plus, jamais de 23 h à 8 h, rien s'il n'y a rien de nouveau."""

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from modules.corvees import notifier
from tests.corvees.unitaires.test_ia import candidat

PARIS = ZoneInfo("Europe/Paris")


def ts(jour, h, m=0):
    return datetime(2026, 10, jour, h, m, tzinfo=PARIS).timestamp()


class Affiche:
    def __init__(self, reussit=True):
        self.vues = []
        self.reussit = reussit

    def __call__(self, titre, message):
        self.vues.append((titre, message))
        return self.reussit


@pytest.mark.parametrize(
    ("h", "m", "silence"),
    [(22, 59, False), (23, 0, True), (2, 0, True), (7, 59, True), (8, 0, False), (12, 0, False)],
)
def test_heures_de_silence(reglages, h, m, silence):
    assert notifier.en_silence(reglages, ts(5, h, m)) is silence


def test_silence_reglable(reglages):
    reglages["notifications"].update(silence_debut="12:00", silence_fin="14:00")
    assert notifier.en_silence(reglages, ts(5, 13)) and not notifier.en_silence(reglages, ts(5, 23, 30))
    reglages["notifications"].update(silence_debut="00:00", silence_fin="00:00")
    assert not notifier.en_silence(reglages, ts(5, 3))


def test_le_texte(reglages):
    cands = [candidat(1), candidat(2), candidat(3)]
    descriptions = {"sig1": {"gain_minutes_mois": 10}, "sig2": {"gain_minutes_mois": 999}}
    titre, message = notifier.texte(cands, descriptions)
    assert titre == "🔁 3 corvées repérées"
    assert message == "Environ 36 min/mois à récupérer. Tape « corvees rapport »."  # 10 + 12,9 (plafonné) + 12,9
    assert notifier.texte([candidat(1)], {})[0] == "🔁 1 corvée repérée"


def test_le_soir_elle_part_et_pas_deux_fois_le_meme_jour(base, reglages):
    affiche = Affiche()
    assert notifier.preparer(base, [candidat(1)], {}, ts(5, 21))
    assert notifier.tenter(base, reglages, ts(5, 21), afficher=affiche)
    assert len(affiche.vues) == 1 and base.lire("notification_en_attente") is None
    notifier.preparer(base, [candidat(1), candidat(2)], {}, ts(5, 22))  # du nouveau, mais déjà une ce jour
    assert not notifier.tenter(base, reglages, ts(5, 22, 30), afficher=affiche)
    assert notifier.tenter(base, reglages, ts(6, 9), afficher=affiche)  # le lendemain matin
    assert len(affiche.vues) == 2 and affiche.vues[1][0] == "🔁 2 corvées repérées"


def test_rien_de_nouveau_aucune_notification(base, reglages):
    affiche = Affiche()
    notifier.preparer(base, [candidat(1)], {}, ts(5, 21))
    notifier.tenter(base, reglages, ts(5, 21), afficher=affiche)
    assert notifier.preparer(base, [candidat(1)], {}, ts(6, 21)) is None  # la même corvée, déjà annoncée
    assert not notifier.tenter(base, reglages, ts(6, 21), afficher=affiche)
    assert notifier.preparer(base, [], {}, ts(7, 21)) is None
    assert len(affiche.vues) == 1


def test_analyse_au_reveil_la_nuit_elle_attend_le_matin(base, reglages):
    affiche = Affiche()
    notifier.preparer(base, [candidat(1)], {}, ts(6, 2))  # le Mac s'est réveillé à 2 h
    assert not notifier.tenter(base, reglages, ts(6, 2), afficher=affiche)
    assert not notifier.tenter(base, reglages, ts(6, 7, 59), afficher=affiche)
    assert notifier.tenter(base, reglages, ts(6, 8, 0), afficher=affiche)
    assert len(affiche.vues) == 1


def test_un_echec_est_retente_un_quart_d_heure_plus_tard(base, reglages):
    rate = Affiche(reussit=False)
    notifier.preparer(base, [candidat(1)], {}, ts(5, 21))
    assert not notifier.tenter(base, reglages, ts(5, 21), afficher=rate)
    assert not notifier.tenter(base, reglages, ts(5, 21, 10), afficher=rate)  # trop tôt
    assert len(rate.vues) == 1
    assert notifier.tenter(base, reglages, ts(5, 21, 15), afficher=Affiche())


def test_une_panne_d_affichage_ne_fait_rien_tomber(base, reglages):
    journal = []
    notifier.preparer(base, [candidat(1)], {}, ts(5, 21))

    def casse(titre, message):
        raise OSError("osascript absent")

    assert not notifier.tenter(base, reglages, ts(5, 21), afficher=casse, journal=journal.append)
    assert journal == ["Notification impossible : OSError : osascript absent"]
    assert base.lire("notification_en_attente")  # toujours en attente


def test_mode_test_vers_le_journal(base, reglages):
    reglages["notifications"]["vers_journal"] = True
    notifier.preparer(base, [candidat(1)], {}, ts(5, 21))
    assert notifier.tenter(base, reglages, ts(5, 21))
    fichier = notifier.config.dossier_donnees(reglages) / "notifications.log"
    assert "🔁 1 corvée repérée · Environ 13 min/mois" in fichier.read_text()
    assert oct(fichier.stat().st_mode)[-3:] == "600"


def test_par_les_notifications_de_l_assistant(base, reglages):
    notifier.preparer(base, [candidat(1)], {}, ts(5, 21))
    with mock.patch("core.notifications.notifier", return_value=(True, "")) as vrai:
        assert notifier.tenter(base, reglages, ts(5, 21))
    assert vrai.call_args.kwargs == {"module": "corvees"} and vrai.call_args.args[0] == "🔁 1 corvée repérée"


def test_memoire_bornee(base, reglages):
    with mock.patch.object(notifier, "MEMOIRE_MAX", 3):
        for jour in range(1, 6):
            notifier.preparer(base, [candidat(jour)], {}, ts(jour, 21))
            notifier.tenter(base, reglages, ts(jour, 21), afficher=Affiche())
    assert base.lire("notifiees") == ["sig3", "sig4", "sig5"]


def test_deux_fils_en_meme_temps_une_seule_notification(base, reglages, tmp_path):
    """Le démon (au battement) et la suite du soir (après l'analyse) peuvent tenter en même temps."""
    import threading
    import time

    from modules.corvees.db import Base

    notifier.preparer(base, [candidat(1)], {}, ts(5, 21))
    vues = []

    def lente(titre, message):
        time.sleep(0.2)
        vues.append(titre)
        return True

    def tenter():  # chaque fil a sa propre connexion, comme le démon et la suite
        b = Base(base.chemin, base.gardien)
        try:
            notifier.tenter(b, reglages, ts(5, 21), afficher=lente)
        finally:
            b.fermer()

    fils = [threading.Thread(target=tenter) for _ in range(2)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert len(vues) == 1
