"""La suite de l'analyse du soir : descriptions puis propositions, dans un fil à part, sans jamais faire tomber."""

import types
from unittest import mock

from modules.corvees import propositions, suite
from tests.corvees.unitaires.test_ia import SOIR, FauxClaude, candidat, tout_decrire


def test_traiter_decrit_et_ecrit_chaque_proposition(reglages):
    journal = []
    cands = [candidat(1), candidat(2, tokens=["clip:Safari→Numbers"], type="pont")]
    descriptions = suite.traiter(reglages, cands, SOIR, journal.append, demander=FauxClaude(tout_decrire))
    assert set(descriptions) == {"sig1", "sig2"}
    for c in cands:
        assert (propositions.racine(reglages) / c["id"] / "README.md").exists()
    assert propositions.lire(reglages, "id0001")["description"]["source"] == "claude"


def test_le_fil_ne_fait_jamais_tomber_le_demon(reglages):
    journal = []
    demon = types.SimpleNamespace(reglages=reglages, journal=journal.append)
    with mock.patch.object(suite, "traiter", side_effect=RuntimeError("panne")):
        suite.apres_analyse(demon, [candidat(1)], SOIR)
        suite.attendre(5)
    assert journal == ["Suite de l'analyse : RuntimeError : panne"]


def test_un_seul_fil_a_la_fois(reglages):
    journal = []
    demon = types.SimpleNamespace(reglages=reglages, journal=journal.append)
    import threading

    libre = threading.Event()
    with mock.patch.object(suite, "traiter", side_effect=lambda *a, **k: libre.wait(5)):
        suite.apres_analyse(demon, [], SOIR)
        suite.apres_analyse(demon, [], SOIR)
        libre.set()
        suite.attendre(5)
    assert journal == ["Suite de l'analyse précédente encore en cours : celle-ci attendra demain"]


def test_le_fil_normal_passe_par_traiter(reglages):
    vu = []
    demon = types.SimpleNamespace(reglages=reglages, journal=vu.append)
    with mock.patch.object(suite, "traiter", side_effect=lambda r, c, m, j: vu.append((len(c), m))):
        suite.apres_analyse(demon, [candidat(1)], SOIR)
        suite.attendre(5)
    assert vu == [(1, SOIR)]


def test_traiter_ecrit_le_rapport_et_prevoit_la_notification(reglages):
    from modules.corvees import rapport
    from modules.corvees.daemon import ouvrir

    vues = []
    suite.traiter(
        reglages,
        [candidat(1)],
        SOIR,
        lambda m: None,
        demander=FauxClaude(tout_decrire),
        afficher=lambda titre, message: vues.append(titre) or True,
    )
    assert rapport.chemin(reglages).exists() and vues == ["🔁 1 corvée repérée"]
    suite.traiter(reglages, [candidat(2)], SOIR + 60, lambda m: None, demander=FauxClaude(), prevenir=False)
    base = ouvrir(reglages)
    assert base.lire("notification_en_attente") is None  # prevenir=False : rien de préparé
    base.fermer()


def test_une_purge_pendant_la_suite_ne_laisse_rien_derriere(reglages):
    """La suite du soir tourne dans un fil ; si tu purges pendant ce temps, elle n'écrit plus rien."""
    from modules.corvees import daemon, propositions, rapport

    journal = []

    def decrire_puis_purge(base, candidats, *a, **k):
        daemon.effacer_donnees(reglages)  # la purge arrive pendant l'appel à Claude
        return {c["signature"]: {"titre_court": "x"} for c in candidats}

    with mock.patch.object(suite.ia, "decrire", side_effect=decrire_puis_purge):
        assert suite.traiter(reglages, [candidat(1)], SOIR, journal.append) == {}
    assert not propositions.racine(reglages).exists() and not rapport.chemin(reglages).exists()
    assert any("purge" in m for m in journal)
