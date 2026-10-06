"""Le démon de bout en bout dans un bac à sable : boîte → rangé, note, notifications groupées, matin, statut."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from modules.trieur import config, daemon, traitement
from modules.trieur.notifications import Notifieur
from tests.trieur.outils import FACTURE, FauxOCR, FauxSysteme, pdf


class Horloge:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _demon(reglages, t: float):
    h = Horloge(t)
    faux = FauxSysteme()
    o = traitement.outils(reglages, systeme_=faux, moteur=FauxOCR(), ia=None)
    d = daemon.Demon(reglages, outils=o, horloge=h)
    envoyees: list[tuple[str, str]] = []
    d.notifieur = Notifieur(reglages, envoyer=lambda t_, m: envoyees.append((t_, m)), horloge=h)
    return d, h, envoyees, faux


def test_de_la_boite_au_classement(reglages):
    reglages["mode_test"] = False  # pour voir passer les notifications (imitées)
    d, h, envoyees, faux = _demon(reglages, datetime(2026, 10, 6, 8, 0).timestamp())
    d.demarrer()
    boite = config.chemin(reglages, "boite")
    (boite / "Scan 1.meta.json").write_text(json.dumps({"note": "garantie 3 ans"}))
    pdf(boite / "Scan 1.pdf", FACTURE)
    traites = 0
    for _ in range(4):
        traites += d.tour()
        h.t += 1
    assert traites == 1 and not (boite / "Scan 1.pdf").exists() and not (boite / "Scan 1.meta.json").exists()
    el = d.o.base.derniers(1)[0]
    assert el.etat == "classe" and el.note == "garantie 3 ans"
    fiche = d.o.coffre.fiches()[0]
    assert fiche.source == "note" and fiche.fin == date(2029, 10, 3)
    assert (boite / "Mon coffre.html").exists() and "Casque" in (boite / "Mon coffre.html").read_text()
    h.t += 10
    d.tour()
    assert envoyees == [("🗂 Rangé", f"{Path(el.destination).name} → 2026 · garantie jusqu'au 03/10/2029")]
    s = daemon.status(reglages, d.o.base, h())
    assert s["vivant"] and s["ranges"] == 1
    d.arreter()


def test_notifications_groupees_au_dela_de_trois(reglages):
    reglages["mode_test"] = False
    d, h, envoyees, _ = _demon(reglages, datetime(2026, 10, 6, 8, 0).timestamp())
    d.demarrer()
    a_trier = config.chemin(reglages, "a_trier")
    for i in range(5):
        pdf(a_trier / f"f{i}.pdf", FACTURE.replace("03/10/2026", f"0{i + 1}/09/2026"))
    for _ in range(4):
        d.tour()
        h.t += 1
    h.t += 10
    d.tour()
    assert envoyees == [("🗂 5 documents traités", "5 rangé(s)")]
    d.arreter()


def test_le_matin_les_garanties_qui_finissent(reglages):
    d, h, envoyees, _ = _demon(reglages, datetime(2026, 10, 6, 8, 0).timestamp())
    reglages["mode_test"] = False
    d.demarrer()
    achat = date(2026, 10, 6) + timedelta(days=30) - timedelta(days=730)  # légale 24 mois : fin dans 30 jours
    d.o.coffre.ajouter_a_la_main("Lave-linge", achat, mois=24)
    d.tour()
    assert envoyees == []  # avant 9 h
    h.t = datetime(2026, 10, 6, 9, 5).timestamp()
    d.tour()
    d.tour()  # une seule fois par jour
    assert envoyees == [("🛡 Garantie", "Lave-linge : fin dans 30 jours (05/11/2026)")]
    d.arreter()


def test_deplacement_a_la_main_suivi(reglages):
    d, h, _, _ = _demon(reglages, time.time())
    d.demarrer()
    el = traitement.traiter(
        d.o, d.o.base.ajouter(pdf(config.chemin(reglages, "a_trier") / "a.pdf", FACTURE), "a_trier")
    )
    ancien = Path(el.destination)
    nouveau = d.o.classes / "Devis/2026" / ancien.name
    nouveau.parent.mkdir(parents=True)
    ancien.rename(nouveau)
    d.demenagements.vus.append((ancien, nouveau))
    d.tour()
    assert d.o.base.element(el.id).type == "devis"
    d.demenagements.vus.append((Path("/nulle/part"), Path("/ailleurs")))
    d.tour()  # sans effet, sans erreur
    d.arreter()


def test_mode_test_et_boucle(reglages, monkeypatch, tmp_path):
    envoyees = []
    n = Notifieur(reglages, envoyer=lambda t, m: envoyees.append(t))
    n.envoyer("x", "y")
    assert envoyees == []  # mode test : le journal seulement
    # La boucle s'arrête quand le superviseur le demande, et relit ses réglages.
    from modules.trieur import config as cfg

    monkeypatch.setattr(cfg, "charger", lambda perso=None: (reglages, ["réglage inconnu : x"]))
    monkeypatch.setattr(traitement, "outils", lambda r, **k: traitement.Outils(
        r, __import__("modules.trieur.base", fromlist=["x"]).Base(tmp_path / "t.db"), FauxSysteme(), None))  # fmt: skip
    monkeypatch.setattr(daemon, "RELIRE_REGLAGES_S", 0.0)
    tours = iter([False, False, True])
    ctx = SimpleNamespace(attendre=lambda s: next(tours))
    daemon.boucle(ctx)
