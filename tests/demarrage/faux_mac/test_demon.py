"""Le démon sur le faux Mac : ouverture de session, croisière, nouveaux éléments notifiés, récap, robustesse."""

import sqlite3
import threading
import time

import pytest

from modules.demarrage import daemon, travail
from modules.demarrage.db import Base
from modules.demarrage.notifier import Notifieur
from tests.demarrage.faux_mac.construire import CONNEXION, construire
from tests.demarrage.outils import plist, programme, signe_par


@pytest.fixture(autouse=True)
def paris(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


@pytest.fixture
def monde(tmp_path, reglages):
    faux = construire(tmp_path / "mac")
    faux.mac.repondre(["last", "-20", "utilisateur"], "utilisateur  console  Mon Oct  5 06:54   still logged in\n")
    base = travail.ouvrir_base(reglages)
    envoyees: list[tuple[str, str]] = []
    notifieur = Notifieur(base, reglages, lambda t, m: envoyees.append((t, m)) or True)
    demon = daemon.Demon(faux.mac, base, reglages, notifieur, rouvrir=lambda: travail.ouvrir_base(reglages))
    yield faux, demon, envoyees
    demon.base.fermer()


def test_demarrage_suit_l_ouverture_de_session(monde):
    faux, demon, _ = monde
    faux.a_l_instant(20)  # le superviseur lance le module 20 s après la connexion
    bilan = demon.demarrer()
    # Connexion : « last » dit 06:54 (à la minute), le plus ancien processus à toi précise la seconde (±1 s).
    assert (
        bilan["demarrage_s"] == pytest.approx(52.0, abs=1.5) and bilan["calme_s"] is not None and bilan["releves"] > 50
    )
    assert "/Applications/zoom.us.app" in bilan["apps_lancees"]  # S5 par déduction, au prochain scan
    assert faux.mac.horloge == pytest.approx(CONNEXION + 300)
    assert demon.base.session(faux.boot)["connexion"] == pytest.approx(CONNEXION, abs=1.5)  # affinée à la seconde
    assert demon.base.lire("battement") >= CONNEXION + 295  # vivant pendant les 5 minutes
    assert demon.demarrer() is None  # déjà suivie : pas deux fois
    assert travail.apps_de_la_derniere_session(demon.base) == bilan["apps_lancees"]


def test_demarrage_trop_tard(monde):
    faux, demon, _ = monde
    faux.a_l_instant(3600)
    details = demon.demarrer()
    assert "trop tard" in details["note"] and demon.base.session(faux.boot)["calme"] is None


def test_nouvel_element_notifie_une_fois(monde):
    faux, demon, envoyees = monde
    faux.a_l_instant(3600)  # 7 h 54 : encore les heures de silence
    demon.tour(faux.mac.maintenant())
    assert demon.inventaire is not None and envoyees == []  # premier scan : la référence, pas d'alerte
    faux.mac.attendre(120)
    demon.tour(faux.mac.maintenant())  # rien de neuf
    assert envoyees == [] and demon.base.lire("battement") == faux.mac.maintenant()
    prog = programme(faux.mac, "/Applications/zoom.us.app/Contents/MacOS/ZoomUpdaterBis")
    faux.mac.repondre_debut(
        ["codesign", "-dv", "--verbose=2", prog], "", erreur=signe_par("Zoom Video Communications, Inc.", "BJ4HAAB9B3")
    )
    import os

    plist(faux.mac, "/Users/utilisateur/Library/LaunchAgents/us.zoom.updater.bis.plist", Label="us.zoom.updater.bis",
          Program=prog, RunAtLoad=True)  # fmt: skip
    dossier = faux.mac.chemin("/Users/utilisateur/Library/LaunchAgents")
    os.utime(dossier, ns=(dossier.stat().st_mtime_ns + 10**9, dossier.stat().st_mtime_ns + 10**9))
    faux.mac.attendre(120)
    demon.tour(faux.mac.maintenant())  # le dossier a changé : nouveau scan tout de suite
    assert envoyees == [] and demon.base.lire("en_attente")["elements"] == [
        "Mise à jour de Zoom (Zoom Video Communications, Inc.)"
    ]
    faux.a_l_instant(3600 + 3 * 3600)  # 10 h 54
    demon.tour(faux.mac.maintenant())
    assert envoyees == [
        (
            "Nettoyeur de démarrage",
            "⚠️ Nouveau programme au démarrage : Mise à jour de Zoom (Zoom Video Communications, Inc.)",
        )
    ]


def test_croisiere_energie_purge_recap(monde, reglages):
    faux, demon, envoyees = monde
    faux.a_l_instant(4 * 3600)  # 10 h 54
    t0 = faux.mac.maintenant()
    assert demon.base.lire("dernier_recap") == faux.boot  # posé au lancement : pas de récap le premier jour
    demon.base.ecrire("dernier_recap", t0 - 8 * 86400)  # une semaine plus tard…
    for _ in range(12):
        demon.tour(faux.mac.maintenant())
        faux.mac.attendre(120)
    releves = demon.base.mesures(t0, faux.mac.maintenant(), modes=("croisiere",))
    energie = {ts for ts, *_, p, _ in releves if p is not None}
    assert len(energie) == 3  # toutes les 10 min
    assert demon.base.lire("derniere_purge") == t0
    zsh = demon.base.zsh()  # mesuré avec le récap ; ce faux Mac n'a pas de zsh qui réponde : l'erreur est notée
    assert len(zsh) == 1 and zsh[0]["mediane_ms"] is None and "zsh" in zsh[0]["erreur"]
    lourds = [m for m in envoyees if m[1].startswith("💤")]
    assert lourds and "te coûte" in lourds[0][1]  # le récap hebdomadaire (Docker, Adobe… pas utilisés)
    assert demon.base.lire("dernier_recap") == t0


def test_base_corrompue_en_route(monde, reglages):
    faux, demon, _ = monde
    faux.a_l_instant(4 * 3600)
    demon.tour(faux.mac.maintenant())
    vieille = demon.base

    def casse(*a, **k):
        raise sqlite3.DatabaseError("database disk image is malformed")

    vieille.ecrire = casse  # type: ignore[method-assign]
    assert demon.tour_protege(faux.mac.maintenant()) is False
    assert demon.base is not vieille and demon.notifieur.base is demon.base and demon.echantillonneur.base is demon.base
    assert demon.tour_protege(faux.mac.maintenant()) is True


def test_tour_en_panne_ne_tue_pas(monde, monkeypatch):
    faux, demon, _ = monde
    monkeypatch.setattr(demon, "tour", lambda m: 1 / 0)
    assert demon.tour_protege(1.0) is False
    from modules.demarrage.db import DisquePlein

    def plein(m):
        raise DisquePlein("full")

    monkeypatch.setattr(demon, "tour", plein)
    assert demon.tour_protege(1.0) is False


def test_tourner_et_s_arreter(monde, monkeypatch):
    faux, demon, _ = monde
    faux.a_l_instant(3600)
    tours = []
    monkeypatch.setattr(demon, "tour_protege", lambda m: tours.append(m) or True)
    reponses = iter([False, False, True])
    demon.tourner(lambda s: next(reponses))
    assert len(tours) == 3
    demon.arret = lambda: True
    demon.tourner(lambda s: pytest.fail("ne doit pas attendre"))


def test_boucle_du_superviseur(tmp_path, reglages, monkeypatch):
    faux = construire(tmp_path / "mac")
    faux.a_l_instant(3600)
    from modules.demarrage import config

    monkeypatch.setattr(config, "charger", lambda perso=None: (reglages, ["modules.demarrage.x : réglage inconnu"]))
    monkeypatch.setattr(daemon, "Mac", lambda: faux.mac)

    class Ctx:
        arret = threading.Event()
        avertis: list[str] = []

        class log:  # noqa: N801
            @staticmethod
            def warning(m):
                Ctx.avertis.append(m)

        @staticmethod
        def attendre(s):
            return True

    daemon.boucle(Ctx)
    assert Ctx.avertis and travail.ouvrir_base(reglages).lire("battement") is not None
    statut = daemon.status(Base(travail.dossier(reglages) / "demarrage.db"), faux.mac.maintenant())
    assert statut["vivant"] and statut["dernier_scan"] is not None
