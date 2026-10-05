"""Le démon : écritures groupées, sessions, capteurs qui plantent, pause, battement, purge, analyse du soir."""

import sqlite3
import threading
import types
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from modules.corvees import config, daemon
from modules.corvees.capteurs.base import Capteur
from modules.corvees.db import DisquePlein, Evenement

PARIS = ZoneInfo("Europe/Paris")


def ts(jour, h, m=0):
    return datetime(2026, 10, jour, h, m, tzinfo=PARIS).timestamp()


class Bavard(Capteur):
    """Un capteur imité : émet ce qu'on lui donne, ou plante sur demande."""

    nom = "bavard"
    intervalle = 1.0

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.a_emettre: list[tuple[str, str]] = []
        self.plante = 0
        self.demarrages = self.arrets = self.releves = 0

    def demarrer(self):
        self.demarrages += 1

    def arreter(self):
        self.arrets += 1

    def relever(self, maintenant):
        self.releves += 1
        if self.plante:
            self.plante -= 1
            raise RuntimeError("panne imitée")
        for kind, token in self.a_emettre:
            self.emettre(maintenant, kind, token)
        self.a_emettre = []


@pytest.fixture
def demon(tmp_path):
    reglages, _ = config.charger({"dossier": str(tmp_path / "d"), "analyse": {"heure": "21:00"}})
    messages = []
    d = daemon.Demon(reglages, natif=None, journal=messages.append, capteurs=[])
    bavard = Bavard(reglages, d.recevoir, d.base)
    d.capteurs = [bavard]
    d.demarrer_capteurs()
    d.messages = messages
    d.bavard = bavard
    yield d
    d.base.fermer()


def test_ecrit_par_paquets_toutes_les_30_secondes(demon):
    t = ts(5, 10)
    demon.base.ecrire("derniere_analyse", t)  # pas d'analyse pendant ce test
    demon.bavard.a_emettre = [("app", "app:Numbers")]
    demon.tour(t)  # vidage au premier tour (rien n'était encore écrit)
    demon.bavard.a_emettre = [("app", "app:Mail")]
    demon.tour(t + 2)
    assert demon.base.compter() == 1 and len(demon.tampon) == 1
    demon.tour(t + 31)
    assert demon.base.compter() == 2 and demon.tampon == []


def test_sessions_numerotees(demon):
    for t, kind in ((100, "app"), (200, "app"), (2000, "app"), (2001, "inactif"), (2002, "app")):
        demon.recevoir(Evenement(t, "x", kind, f"{kind}:a"))
    assert [e.session_id for e in demon.tampon] == [0, 0, 1, 2, 2]
    demon.vider(3000)
    assert demon.base.lire("session") == 2


def test_un_capteur_qui_plante_est_relance_avec_un_delai_croissant(demon):
    t = ts(5, 10)
    demon.base.ecrire("derniere_analyse", t)
    demon.bavard.plante = 2
    demon.tour(t)
    assert demon.bavard.statut == "dégradé" and "nouvel essai dans 2 s" in demon.bavard.detail
    demon.tour(t + 1)  # trop tôt : pas de nouvel essai
    assert demon.bavard.releves == 1
    demon.tour(t + 2.5)
    assert demon.bavard.releves == 2 and "nouvel essai dans 4 s" in demon.bavard.detail
    demon.tour(t + 7)
    assert demon.bavard.releves == 3 and demon.bavard.erreurs == 0 and demon.bavard.demarrages >= 2
    assert any("relancé" in m for m in demon.messages)


def test_un_capteur_qui_ne_demarre_pas(demon):
    demon.bavard.demarrer = mock.Mock(side_effect=OSError("non"))
    demon.demarrer_capteurs()
    assert demon.bavard.statut == "dégradé" and "démarrage impossible" in demon.bavard.detail
    demon.bavard.arreter = mock.Mock(side_effect=OSError("non"))
    demon.arreter_capteurs()
    assert any("Arrêt du capteur" in m for m in demon.messages)


def test_capteur_desactive_jamais_releve(demon):
    demon.bavard.desactiver("pas sur un Mac")
    demon.relever(ts(5, 10))
    assert demon.bavard.releves == 0


def test_pause_coupe_tout_tout_de_suite_puis_reprise(demon):
    t = ts(5, 10)
    demon.base.ecrire("derniere_analyse", t)
    demon.tour(t)
    demon.base.ecrire("pause", {"jusqua": t + 3600})
    demon.bavard.a_emettre = [("app", "app:X")]
    demon.tour(t + 1)
    assert demon.en_pause and demon.bavard.arrets == 1 and demon.bavard.releves == 1
    demon.tour(t + 100)
    assert demon.bavard.releves == 1
    demon.tour(t + 3601)  # fin de la pause : les capteurs repartent
    assert not demon.en_pause and demon.bavard.demarrages == 2 and demon.base.lire("pause") is None
    demon.base.ecrire("pause", {"jusqua": None})  # sans fin : jusqu'à « resume »
    demon.tour(t + 3700)
    assert demon.pause_demandee(t + 10**6)


def test_battement_sante_et_purge_quotidienne(demon):
    t = ts(5, 10)
    demon.base.ecrire("derniere_analyse", t)
    vieux = Evenement(t - 40 * 86400, "x", "app", "app:Vieux", {}, 0)
    demon.base.ajouter([vieux])
    demon.tour(t)
    assert demon.base.lire("battement") == t and demon.base.lire("sante")[0]["capteur"] == "bavard"
    assert demon.base.compter() == 0 and any("Purge" in m for m in demon.messages)
    demon.base.ajouter([vieux])
    demon.tour(t + 61)  # même jour : pas de nouvelle purge
    assert demon.base.compter() == 1


@pytest.mark.parametrize(
    ("maintenant", "derniere", "attendu"),
    [
        (ts(5, 20, 59), ts(4, 21, 1), False),  # avant 21 h, celle d'hier est faite
        (ts(5, 21, 0), ts(4, 21, 1), True),  # 21 h
        (ts(5, 21, 30), ts(5, 21, 1), False),  # déjà faite ce soir
        (ts(6, 8, 0), ts(4, 21, 1), True),  # le Mac dormait à 21 h hier soir : au réveil
        (ts(6, 8, 0), 0, True),  # jamais faite
    ],
)
def test_quand_analyser(demon, maintenant, derniere, attendu):
    demon.base.ecrire("derniere_analyse", derniere)
    assert demon.doit_analyser(maintenant) is attendu


def test_sur_batterie_faible_on_attend(demon):
    demon.base.ecrire("derniere_analyse", 0)
    demon.natif = types.SimpleNamespace(alimentation=lambda: (False, 20))
    assert not demon.doit_analyser(ts(5, 21, 30))
    demon.natif = types.SimpleNamespace(alimentation=lambda: (False, 80))
    assert demon.doit_analyser(ts(5, 21, 30))
    demon.natif = types.SimpleNamespace(alimentation=lambda: (True, 5))
    assert demon.doit_analyser(ts(5, 21, 30))


def test_l_analyse_du_soir(demon):
    vu = []
    demon.apres_analyse = lambda d, candidats, quand: vu.append((len(candidats), quand))
    for jour in range(1, 6):  # une corvée de fichiers chaque jour
        demon.base.ajouter(
            [
                Evenement(
                    ts(jour, 15),
                    "fichiers",
                    "fmove",
                    "fmove:Downloads→Documents/Factures [pdf, Facture_*]",
                    {"fichier": f"f{jour}"},
                    jour,
                )
            ]
        )
    demon.tour(ts(5, 21, 5))
    assert demon.base.lire("derniere_analyse") == ts(5, 21, 5)
    assert len(demon.base.candidats()) == 1 and vu == [(1, ts(5, 21, 5))]
    demon.apres_analyse = mock.Mock(side_effect=RuntimeError("IA en panne"))
    demon.analyser(ts(5, 21, 10))  # ne tombe pas
    assert any("Après l'analyse" in m for m in demon.messages)


def test_disque_plein_rien_ne_tombe(demon):
    demon.recevoir(Evenement(1, "x", "app", "app:A"))
    with mock.patch.object(demon.base, "ajouter", side_effect=DisquePlein("plein")):
        assert demon.vider(2) == 0
        demon.recevoir(Evenement(3, "x", "app", "app:B"))
        demon.vider(4)
    assert sum("Disque plein" in m for m in demon.messages) == 1  # dit une seule fois
    demon.recevoir(Evenement(5, "x", "app", "app:C"))
    assert demon.vider(6) == 1


def test_base_abimee_en_cours_de_route(demon):
    demon.recevoir(Evenement(1, "x", "app", "app:A"))
    vraie = demon.base
    with mock.patch.object(vraie, "ajouter", side_effect=sqlite3.DatabaseError("malformed")):
        assert demon.vider(2) == 1
    assert demon.base is not vraie and any("reconstruction" in m for m in demon.messages)


def test_tampon_borne(demon):
    with mock.patch.object(daemon, "TAMPON_MAX", 3):
        for i in range(5):
            demon.recevoir(Evenement(i, "x", "app", f"app:{i}"))
    assert [e.token for e in demon.tampon] == ["app:2", "app:3", "app:4"]


def test_boucle_sous_le_superviseur(tmp_path, monkeypatch):
    monkeypatch.setenv("CORVEES_DOSSIER", str(tmp_path / "d"))
    ctx = types.SimpleNamespace(arret=threading.Event(), log=mock.Mock())
    tours = []

    def attendre(s):
        tours.append(s)
        if len(tours) >= 3:
            ctx.arret.set()
        return ctx.arret.is_set()

    ctx.attendre = attendre
    with mock.patch("core.config.charger", return_value={"modules": {"corvees": {"capteurs": {"fichiers": False}}}}):
        daemon.boucle(ctx)
    assert len(tours) == 3 and (tmp_path / "d" / "corvees.db").exists()
    assert any("capteurs" in str(c) for c in ctx.log.info.call_args_list)


def test_boucle_sur_mac_fait_tourner_la_boucle_d_evenements(tmp_path, monkeypatch):
    monkeypatch.setenv("CORVEES_DOSSIER", str(tmp_path / "d"))
    ctx = types.SimpleNamespace(arret=threading.Event(), log=mock.Mock(), attendre=lambda s: False)
    faux = mock.Mock()
    faux.pomper.side_effect = lambda s: ctx.arret.set()
    faux.alimentation.return_value = (True, None)
    faux.appli_devant.return_value = None
    faux.appli_devant_secours.return_value = None
    with (
        mock.patch("modules.corvees.capteurs.natif.natif", return_value=faux),
        mock.patch("core.config.charger", return_value={"modules": {"corvees": {"capteurs": {"fichiers": False}}}}),
    ):
        daemon.boucle(ctx)
    faux.pomper.assert_called_with(daemon.PAS_S)


def test_interface_de_module(tmp_path, monkeypatch):
    monkeypatch.setenv("CORVEES_DOSSIER", str(tmp_path / "d"))
    with mock.patch("core.config.activer_module") as activer:
        daemon.start()
        daemon.stop()
    assert activer.call_args_list == [mock.call("corvees", True), mock.call("corvees", False)]
    with mock.patch("core.config.charger", return_value={"modules": {"corvees": {}}}):
        base = daemon.ouvrir()
    base.ecrire("battement", 1000.0)
    base.ecrire("sante", [{"capteur": "apps", "statut": "ok"}])
    with mock.patch("core.config.module_actif", return_value=True):
        s = daemon.status(base, maintenant=1050.0)
        h = daemon.health(base, maintenant=1050.0)
    assert s["actif"] and s["vivant"] and s["evenements"] == 0 and s["corvees"] == 0
    assert h["capteurs"][0]["statut"] == "ok" and h["cout_du_mois_usd"] == 0 and h["taille_octets"] > 0
    with mock.patch("core.config.module_actif", return_value=False):
        assert not daemon.status(base, maintenant=5000.0)["vivant"]


def test_la_commande_demande_de_vider_le_tampon(demon):
    t = ts(5, 10)
    demon.base.ecrire("derniere_analyse", t)
    demon.tour(t)
    demon.recevoir(Evenement(t + 1, "x", "app", "app:A"))
    demon.base.ecrire("demande", {"quoi": "vider", "quand": t + 2})
    demon.tour(t + 2)
    assert demon.base.compter() == 1 and demon.base.lire("demande") is None
    assert demon.base.lire("demande_faite") == {"quoi": "vider", "quand": t + 2}


def test_la_pause_est_confirmee_dans_la_base(demon):
    t = ts(5, 10)
    demon.base.ecrire("derniere_analyse", t)
    demon.base.ecrire("pause", {"jusqua": None})
    demon.tour(t)
    assert demon.base.lire("en_pause") is True
    demon.base.effacer("pause")
    demon.tour(t + 1)
    assert demon.base.lire("en_pause") is False


def test_purge_par_le_demon_tout_repart_de_zero(demon):
    t = ts(5, 10)
    demon.base.ecrire("derniere_analyse", t)
    demon.base.ajouter([Evenement(t, "x", "app", "app:A", {}, 0)])
    demon.base.ecrire("pause", {"jusqua": None})
    demon.tour(t)
    dossier = demon.dossier
    (dossier / "propositions" / "abc").mkdir(parents=True)
    (dossier / "rapport.html").write_text("vieux")
    (dossier / "a_moi.txt").write_text("à toi")
    sel_avant = (dossier / "sel").read_bytes()
    ancienne = demon.base
    demon.base.ecrire("demande", {"quoi": "purge", "quand": t + 1})
    demon.tour(t + 1)
    assert demon.base is not ancienne and demon.base.compter() == 0
    assert not (dossier / "propositions").exists() and not (dossier / "rapport.html").exists()
    assert (dossier / "a_moi.txt").exists()  # ce qui n'est pas au détecteur n'est jamais touché
    assert (dossier / "sel").read_bytes() != sel_avant  # nouvelles empreintes : rien ne se recoupe
    assert demon.bavard.memoire is demon.base  # ses curseurs repartent de zéro aussi
    assert demon.base.lire("pause") == {"jusqua": None}  # la pause est gardée
    assert demon.base.lire("demande_faite") == {"quoi": "purge", "quand": t + 1}
    assert any("Purge : toutes les données" in m for m in demon.messages)


def test_purge_capteurs_reconstruits(tmp_path):
    reglages, _ = config.charger({"dossier": str(tmp_path / "d"), "capteurs": {"fichiers": False}})
    d = daemon.Demon(reglages, natif=None, journal=lambda m: None)
    avant = list(d.capteurs)
    d.recommencer(ts(5, 10))
    assert d.capteurs and all(c not in avant for c in d.capteurs)
    assert all(c.memoire is d.base for c in d.capteurs)
    d.fermer(ts(5, 10))


def test_la_notification_en_attente_part_au_battement(demon):
    demon.reglages["notifications"]["vers_journal"] = True
    t = ts(5, 21, 30)
    demon.base.ecrire("derniere_analyse", t)
    demon.base.ecrire("notification_en_attente", {"titre": "🔁 1 corvée repérée", "message": "m", "signatures": ["s"]})
    demon.tour(t)
    assert (demon.dossier / "notifications.log").read_text().count("🔁 1 corvée repérée") == 1
    assert any("Notification :" in m for m in demon.messages)


def test_une_notification_qui_plante_ne_fait_rien_tomber(demon):
    t = ts(5, 21, 30)
    demon.base.ecrire("derniere_analyse", t)
    with mock.patch("modules.corvees.notifier.tenter", side_effect=RuntimeError("non")):
        demon.tour(t)
        demon.tour(t + 61)
    assert sum("Notification : RuntimeError" in m for m in demon.messages) == 1
