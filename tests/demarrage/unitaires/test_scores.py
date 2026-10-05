import pytest

from modules.demarrage.analyse import gains, scores
from modules.demarrage.analyse.scores import Metriques
from modules.demarrage.db import Base
from modules.demarrage.modele import Declencheurs, Fiche

JOUR = 86400.0


def fiche(**k):
    return Fiche(id=k.pop("id", "f"), label=k.pop("label", "com.x"), source="agent_utilisateur", **k)


def m(**k):
    return {"cpu_s": 0.0, "rss_ko": 0, "puissance": None, "veille": False, **k}


@pytest.fixture
def base(tmp_path):
    b = Base(tmp_path / "d.db")
    yield b
    b.fermer()


def test_metriques_session_mediane_et_croisiere(base, reglages):
    t0 = 100 * JOUR
    # Deux sessions : 30 s puis 10 s pour « a » ; « b » n'apparaît qu'à la 2e (0 s à la 1re).
    for k, (cpu_a, cpu_b) in enumerate([(30.0, 0.0), (10.0, 4.0)]):
        connexion = t0 + k * JOUR
        base.enregistrer_session(connexion - 60, connexion, None, {"releves": 60})
        base.enregistrer_releve(
            connexion + 5, "session", 50.0, {"a": m(cpu_s=cpu_a / 2), **({"b": m(cpu_s=cpu_b)} if cpu_b else {})}
        )
        base.enregistrer_releve(connexion + 10, "session", 50.0, {"a": m(cpu_s=cpu_a / 2)})
        base.enregistrer_releve(
            connexion + 400, "session", 50.0, {"a": m(cpu_s=99.0)}
        )  # après les 5 min : hors fenêtre
    # Croisière : 3 relevés à 120 s d'écart, puis un trou (veille) de 2 h, puis un relevé.
    c = t0 + 2 * JOUR
    base.enregistrer_releve(c, "croisiere", 1.0, {"a": m(cpu_s=50.0, rss_ko=100 * 1024)})
    base.enregistrer_releve(
        c + 120, "croisiere", 1.0, {"a": m(cpu_s=6.0, rss_ko=300 * 1024, puissance=4.0, veille=True)}
    )
    base.enregistrer_releve(c + 240, "croisiere", 1.0, {"a": m(cpu_s=6.0, rss_ko=200 * 1024, puissance=2.0)})
    base.enregistrer_releve(c + 7440, "croisiere", 1.0, {"a": m(cpu_s=500.0, rss_ko=200 * 1024)})
    r = scores.metriques(base, reglages, c + 7500)
    assert r["a"].cpu_session_s == 20.0  # médiane de 30 et 10
    assert r["b"].cpu_session_s == 2.0  # médiane de 0 et 4
    assert r["a"].cpu_croisiere_pct == pytest.approx(100 * 12.0 / 240)  # le 1er relevé et l'après-trou exclus
    assert r["a"].memoire_mo == pytest.approx(200.0) and r["a"].energie == 3.0
    assert r["a"].veille == pytest.approx(1 / 10) and r["a"].releves == 10 and r["a"].mesure
    assert not Metriques().mesure


def test_metriques_fenetre_et_vide(base, reglages):
    assert scores.metriques(base, reglages, 1e9) == {}
    base.enregistrer_releve(1.0, "croisiere", 1.0, {"vieux": m(cpu_s=1.0)})
    assert "vieux" not in scores.metriques(base, reglages, 30 * JOUR)


def test_impact(reglages):
    s = reglages["scores"]
    assert scores.impact(fiche(), None, reglages) == 0.0
    plein = Metriques(cpu_session_s=999, cpu_croisiere_pct=999, memoire_mo=99999, energie=999, releves=1)
    assert scores.impact(fiche(), plein, reglages) == 100.0
    moitie = Metriques(cpu_session_s=s["references"]["cpu_session_s"] / 2, releves=1)
    assert scores.impact(fiche(), moitie, reglages) == pytest.approx(100 * s["poids"]["cpu_session"] / 2)
    veille = Metriques(veille=0.5, releves=1)
    assert scores.impact(fiche(), veille, reglages) == s["bonus_veille"]
    boucle = fiche(declencheurs=Declencheurs(garder_en_vie=True), details={"relances": 6, "dernier_code": 1})
    assert scores.impact(boucle, Metriques(), reglages) == s["bonus_boucle"]
    pas_boucle = fiche(declencheurs=Declencheurs(garder_en_vie=True), details={"relances": 600, "dernier_code": 0})
    assert scores.impact(pas_boucle, Metriques(), reglages) == 0.0
    assert scores.impact(fiche(), Metriques(cpu_session_s=-5, releves=1), reglages) == 0.0
    assert (
        scores.impact_estime("fort", reglages) == s["impact_estime"]["fort"]
        and scores.impact_estime("?", reglages) == 0
    )


def test_utilite(reglages):
    maintenant = 1000 * JOUR
    assert scores.utilite(fiche(est_apple=True), maintenant, reglages, None)[0] == "indispensable"
    assert scores.utilite(fiche(c_est_moi=True), maintenant, reglages, None)[0] == "indispensable"
    assert scores.utilite(fiche(derniere_utilisation_app=maintenant - 45 * JOUR), maintenant, reglages, None) == (
        "faible", "app pas ouverte depuis 45 jours")  # fmt: skip
    assert scores.utilite(fiche(derniere_utilisation_app=maintenant - 3 * JOUR), maintenant, reglages, None)[
        1
    ].endswith("3 jour(s)")
    assert (
        "moins d'un jour"
        in scores.utilite(fiche(derniere_utilisation_app=maintenant - 60), maintenant, reglages, None)[1]
    )
    assert scores.utilite(fiche(), maintenant, reglages, "garder")[0] == "forte"
    assert scores.utilite(fiche(), maintenant, reglages, "desactiver")[0] == "inconnue"


def test_gains():
    class E:
        def __init__(self, code, mem, cpu, drapeaux=()):
            self.verdict = type("V", (), {"code": code})()
            self.metriques = Metriques(memoire_mo=mem, cpu_session_s=cpu)
            self.drapeaux = list(drapeaux)
            self.fiche = fiche(id=f"{code}{mem}")

    elements = [
        E("inutile", 100.0, 10.0, ["empêche la veille"]),
        E("orphelin", None, None),
        E("utile", 900.0, 90.0),
        E("inutile", 50.25, 2.5),
    ]
    g = gains.calculer(elements)
    assert (g.memoire_mo, g.cpu_session_s, g.veilles, len(g.elements)) == (150.2, 12.5, 1, 3)
