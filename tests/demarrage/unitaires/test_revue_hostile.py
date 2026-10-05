"""P10 — chaque défaut trouvé en relisant le Nettoyeur « pour le casser » a son test de non-régression."""

import time

import pytest

from modules.demarrage import scan
from modules.demarrage.analyse import analyser
from modules.demarrage.db import Base
from modules.demarrage.fichiers import absent_certain, localiser
from modules.demarrage.modele import Fiche, Inventaire
from modules.demarrage.notifier import Notifieur
from tests.demarrage.outils import plist, programme

JOUR = 86400.0


def test_un_antivirus_jamais_ouvert_n_est_pas_inutile(tmp_path, reglages):
    """La base dit « garder » (sécurité, VPN, pilote) : utile, même si l'app n'a pas été ouverte depuis 60 jours."""
    b = Base(tmp_path / "d.db")
    maintenant = 100 * JOUR
    f = Fiche(id="bd", label="com.bitdefender.agent", source="agent_utilisateur", programme="/opt/bd/agent",
              programme_existe=True, signature="developpeur", editeur="Bitdefender", actif=True,
              app_parente="/Applications/Bitdefender.app", derniere_utilisation_app=maintenant - 60 * JOUR)  # fmt: skip
    lourd = {"cpu_s": 30.0, "rss_ko": 900 * 1024, "puissance": 20.0, "veille": False}
    for k in range(6):
        b.enregistrer_releve(maintenant - 600 + 120 * k, "croisiere", 5.0, {"bd": lourd})
    el = analyser(Inventaire(ts=maintenant, fiches=[f]), b, reglages, maintenant).elements[0]
    b.fermer()
    assert el.impact >= reglages["verdicts"]["impact_significatif"]
    assert el.verdict.code == "utile" and el.utilite == "forte"


def test_disque_externe_debranche_n_est_pas_un_orphelin(mac):
    assert not absent_certain(mac, "/Volumes/Disque Photo/Outils/agent")
    mac.chemin("/Volumes").mkdir()
    assert not absent_certain(mac, "/Volumes/Disque Photo/Outils/agent")
    assert absent_certain(mac, "/Applications/Parti.app/Contents/MacOS/x")


def test_tilde_deplie(mac):
    programme(mac, "/Users/utilisateur/bin/outil")
    assert localiser(mac, "~/bin/outil") == "/Users/utilisateur/bin/outil"
    plist(mac, "/Users/utilisateur/Library/LaunchAgents/t.plist", Label="t", ProgramArguments=["~/bin/outil"])
    from modules.demarrage.collecteurs.plists import fiche_depuis_plist

    f = fiche_depuis_plist(mac, "/Users/utilisateur/Library/LaunchAgents/t.plist", "agent_utilisateur")
    assert f.programme == "/Users/utilisateur/bin/outil" and f.programme_existe


def test_launchctl_muet_on_ne_conclut_pas(mac, reglages):
    plist(mac, "/Users/utilisateur/Library/LaunchAgents/a.plist", Label="a", Program="/opt/a")
    mac.repondre_debut(["launchctl"], "", code=5, erreur="Input/output error")
    f = next(x for x in scan.scanner(mac, reglages).fiches if x.label == "a")
    assert f.charge is None and f.desactive is None and f.actif is None  # « inconnu », pas « pas chargé »


def test_changement_d_heure(tmp_path, reglages, monkeypatch):
    """Dimanche 25 octobre 2026 à Paris : à 3 h, il est 2 h. Les heures silencieuses suivent l'heure du Mac."""
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    try:
        b = Base(tmp_path / "d.db")
        n = Notifieur(b, reglages, lambda t, m: True)
        avant = time.mktime((2026, 10, 25, 1, 59, 0, 0, 0, -1))
        assert n.en_silence(avant) and n.en_silence(avant + 3600)  # 2 h 59 (heure d'été) puis 2 h 59 (hiver)
        huit_heures = time.mktime((2026, 10, 25, 8, 0, 0, 0, 0, -1))
        assert not n.en_silence(huit_heures) and huit_heures - avant == 7 * 3600 + 60
        assert n.proposer("recap", "r", huit_heures) and not n.proposer("recap", "r", huit_heures + 15 * 3600)
        assert n.proposer("recap", "r", huit_heures + 24 * 3600)  # le lendemain, de nouveau permis
        b.fermer()
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


@pytest.mark.parametrize("label", ["com.apple.Finder", "com.apple.mds"])
def test_un_element_apple_reste_apple_meme_lourd_et_inutile(tmp_path, reglages, label):
    b = Base(tmp_path / "d.db")
    plist_apple = f"/System/Library/LaunchAgents/{label}.plist"
    f = Fiche(
        id="ap", label=label, source="apple", est_apple=True, chemin_plist=plist_apple,
        programme="/System/x", programme_existe=True, signature="apple", actif=True,
        derniere_utilisation_app=1.0, app_parente="/System/Applications/X.app",
    )  # fmt: skip
    b.enregistrer_releve(
        10.0, "mesure", 90.0, {"ap": {"cpu_s": 99.0, "rss_ko": 5_000_000, "puissance": 99.0, "veille": True}}
    )
    el = analyser(Inventaire(ts=20.0, fiches=[f]), b, reglages, 20.0).elements[0]
    b.fermer()
    assert el.verdict.code == "apple" and el.verdict.action == "aucune"
