"""La commande « corvees », sur un mois simulé : chaque sous-commande, ses messages, ses erreurs."""

import os
from types import SimpleNamespace
from unittest import mock

import pytest

from modules.corvees import cli, config, daemon, privacy, propositions, rapport
from modules.corvees.db import Base
from tests.corvees.simulation.generateur import generer
from tests.corvees.unitaires.test_ia import FauxClaude, tout_decrire


@pytest.fixture(scope="module")
def monde():
    return generer(101)


@pytest.fixture
def dossier(tmp_path, monde):
    d = tmp_path / "donnees"
    r, _ = config.charger({"dossier": str(d)})
    b = Base(d / "corvees.db", privacy.Gardien(r, privacy.sel(d)))
    b.ajouter(monde.evenements)
    b.fermer()
    return d


class Monde:
    """Une commande lancée dans ce monde : horloge figée à la fin du mois simulé, démon imité si besoin."""

    def __init__(self, dossier, monde, demon=None):
        self.reglages, _ = config.charger({"dossier": str(dossier)})
        self.reglages["installation"]["launchagents"] = str(dossier.parent / "LaunchAgents")
        self.fin = monde.fin
        self.demon = demon
        self.reponses = ["OUI"]
        self.lancees = []

    def lancer(self, commande, **_):
        self.lancees.append(commande)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def contexte(self):
        ctx = cli.Contexte(
            self.reglages,
            maintenant=lambda: self.fin,
            dormir=self.dormir,
            entree=lambda question: self.reponses.pop(0),
            lancer=self.lancer,
            demander=FauxClaude(tout_decrire),
        )
        ctx.plateforme = "darwin"
        return ctx

    def dormir(self, secondes):
        if self.demon is not None:  # le démon fait un tour pendant que la commande attend
            self.demon.tour(self.fin)

    def __call__(self, *argv):
        with mock.patch("core.config.module_actif", return_value=False):
            return cli.main(list(argv), self.contexte())


@pytest.fixture
def corvees(dossier, monde):
    return Monde(dossier, monde)


def ids(corvees):
    ctx = corvees.contexte()
    try:
        return {c["tokens"][0]: c["id"] for c in ctx.base.candidats()}
    finally:
        ctx.base.fermer()


def test_aide_et_commande_inconnue(capsys):
    assert cli.main([]) == 0 and "accept ID [--installer]" in capsys.readouterr().out
    assert cli.main(["--help"]) == 0
    with pytest.raises(SystemExit) as e:
        cli.main(["inconnue"])
    assert e.value.code == 2 and "⛔" in capsys.readouterr().out


def test_status(corvees, capsys):
    assert corvees("status") == 0
    sortie = capsys.readouterr().out
    assert "éteint" in sortie and "démon : arrêté" in sortie
    assert "événements gardés · 0 corvée(s)" in sortie and "Dernière analyse : jamais" in sortie


def test_analyser(corvees, capsys):
    assert corvees("analyser") == 0 and "--maintenant" in capsys.readouterr().out
    assert corvees("analyser", "--maintenant") == 0
    sortie = capsys.readouterr().out
    assert "10 corvée(s) repérée(s)" in sortie and "Le détail : corvees rapport" in sortie
    assert rapport.chemin(corvees.reglages).exists()
    assert len(list(propositions.racine(corvees.reglages).iterdir())) == 10
    ctx = corvees.contexte()
    assert ctx.base.lire("notification_en_attente") is None  # tu es là : pas de notification
    assert ctx.base.lire("derniere_analyse") == corvees.fin
    ctx.base.fermer()


def test_analyser_sans_rien(tmp_path, monde, capsys):
    vide = Monde(tmp_path / "vide", monde)
    assert vide("analyser", "--maintenant") == 0 and "Rien de solide" in capsys.readouterr().out


def test_analyser_avec_le_demon_vide_d_abord_son_tampon(dossier, monde, capsys):
    corvees = Monde(dossier, monde)
    reglages = corvees.reglages
    demon = daemon.Demon(reglages, capteurs=[])
    corvees.demon = demon
    demon.base.ecrire("battement", corvees.fin)
    demon.base.ecrire("derniere_analyse", corvees.fin)
    with mock.patch.object(demon, "vider", wraps=demon.vider) as vider:
        assert corvees("analyser", "--maintenant") == 0
    assert vider.called and demon.base.lire("demande_faite")["quoi"] == "vider"
    demon.base.fermer()


def test_rapport(corvees, capsys):
    corvees("analyser", "--maintenant")
    assert corvees("rapport") == 0
    assert "(ouvert dans ton navigateur)" in capsys.readouterr().out
    assert corvees.lancees == [["open", str(rapport.chemin(corvees.reglages))]]
    assert corvees("rapport", "--sans-ouvrir") == 0 and len(corvees.lancees) == 1


def test_accepter_refuser_reporter(corvees, capsys):
    corvees("analyser", "--maintenant")
    trouve = ids(corvees)
    facture = trouve["fmove:Downloads→Documents/Factures [pdf, Facture_*]"]
    spotify = trouve["app:Spotify"]
    pont = trouve["clip:Mail→Microsoft Excel"]
    capsys.readouterr()

    assert corvees("accept", facture) == 0
    sortie = capsys.readouterr().out
    assert sortie.startswith("✅ Acceptée") and "Les étapes :" in sortie and "script.sh" in sortie
    assert corvees("reject", pont) == 0 and "3 fois plus fréquente" in capsys.readouterr().out
    assert corvees("snooze", spotify, "3") == 0 and "Reportée" in capsys.readouterr().out
    assert corvees("snooze", spotify, "0") == 2

    ctx = corvees.contexte()
    decisions = {d["id"]: d for d in ctx.base.decisions().values()}
    ctx.base.fermer()
    assert decisions[facture]["statut"] == "accept"
    assert decisions[pont]["statut"] == "reject" and decisions[pont]["frequence_ref"] > 0
    assert decisions[spotify]["statut"] == "snooze" and decisions[spotify]["jusqua"] == corvees.fin + 3 * 86400
    page = rapport.chemin(corvees.reglages).read_text()  # le rapport est remis à jour
    assert facture not in page and pont not in page and spotify not in page

    assert corvees("accept", "zzzzzz") == 1 and "Je ne connais pas" in capsys.readouterr().out
    assert corvees("reject", "zzzzzz") == 1 and corvees("snooze", "zzzzzz") == 1


def test_accepter_et_installer_puis_desinstaller(corvees, capsys):
    corvees("analyser", "--maintenant")
    trouve = ids(corvees)
    facture = trouve["fmove:Downloads→Documents/Factures [pdf, Facture_*]"]
    pont = trouve["clip:Safari→Numbers"]
    capsys.readouterr()
    # Claude (imité) propose une tâche launchd pour chaque corvée : celle des factures surveille ~/Downloads ;
    # celle du copier-coller n'a pas de moment évident, elle ne s'installe pas.
    assert corvees("accept", facture, "--installer") == 0
    sortie = capsys.readouterr().out
    assert "Tâche installée" in sortie and f"corvees desinstaller {facture}" in sortie
    assert corvees.lancees[-1][:2] == ["launchctl", "bootstrap"]
    assert corvees("accept", pont, "--installer") == 1 and "Pas d'installation" in capsys.readouterr().out
    assert corvees("desinstaller", facture) == 0 and "arrêtée et retirée" in capsys.readouterr().out
    assert corvees.lancees[-1][:2] == ["launchctl", "bootout"]
    assert corvees("desinstaller", facture) == 1 and "Rien d'installé" in capsys.readouterr().out


def test_pause_et_reprise_sans_demon(corvees, capsys):
    assert corvees("pause") == 0 and "Le démon ne tourne pas" in capsys.readouterr().out
    assert corvees("pause", "0") == 2
    assert corvees("status") == 0 and "jusqu'à « corvees resume »" in capsys.readouterr().out
    assert corvees("pause", "2") == 0
    ctx = corvees.contexte()
    assert ctx.base.lire("pause") == {"jusqua": corvees.fin + 7200}
    ctx.base.fermer()
    assert corvees("resume") == 0 and "Reprise" in capsys.readouterr().out
    ctx = corvees.contexte()
    assert ctx.base.lire("pause") is None
    ctx.base.fermer()


def test_pause_avec_le_demon_confirmee(dossier, monde, capsys):
    corvees = Monde(dossier, monde)
    demon = daemon.Demon(corvees.reglages, capteurs=[])
    corvees.demon = demon
    demon.base.ecrire("battement", corvees.fin)
    demon.base.ecrire("derniere_analyse", corvees.fin)
    assert corvees("pause", "1") == 0
    assert "tous les capteurs sont coupés" in capsys.readouterr().out and demon.en_pause
    demon.base.fermer()


def test_purge_demande_confirmation(corvees, capsys):
    corvees.reponses = ["non"]
    assert corvees("purge") == 1 and "Rien n'a été effacé" in capsys.readouterr().out
    ctx = corvees.contexte()
    assert ctx.base.compter() > 0  # rien n'a bougé
    ctx.base.fermer()


def test_purge_sans_demon_efface_tout_et_desinstalle(corvees, capsys):
    corvees("analyser", "--maintenant")
    trouve = ids(corvees)
    corvees("accept", trouve["fmove:Downloads→Documents/Factures [pdf, Facture_*]"], "--installer")
    dossier = config.dossier_donnees(corvees.reglages)
    etranger = dossier / "a_moi.txt"
    etranger.write_text("pas au détecteur")
    assert corvees("purge") == 0 and "Tout est effacé" in capsys.readouterr().out
    restants = sorted(p.name for p in dossier.iterdir())
    assert "propositions" not in restants and "rapport.html" not in restants and "a_moi.txt" in restants
    assert corvees.lancees[-1][:2] == ["launchctl", "bootout"]  # la tâche installée a été retirée
    ctx = corvees.contexte()
    assert ctx.base.compter() == 0 and ctx.base.candidats() == []
    ctx.base.fermer()


def test_purge_avec_le_demon_c_est_lui_qui_efface(dossier, monde, capsys):
    corvees = Monde(dossier, monde)
    demon = daemon.Demon(corvees.reglages, capteurs=[])
    corvees.demon = demon
    demon.base.ecrire("battement", corvees.fin)
    demon.base.ecrire("derniere_analyse", corvees.fin)
    ancienne = demon.base
    assert corvees("purge", "--oui") == 0 and "Tout est effacé" in capsys.readouterr().out
    assert demon.base is not ancienne and demon.base.compter() == 0
    demon.base.fermer()


def test_purge_le_demon_ne_repond_pas(corvees, capsys):
    ctx = corvees.contexte()
    ctx.base.ecrire("battement", corvees.fin)
    ctx.base.fermer()
    with mock.patch.object(cli, "ATTENTE_DEMON_S", 0.01):
        assert corvees("purge", "--oui") == 1
    assert "n'a pas répondu" in capsys.readouterr().out
    assert (config.dossier_donnees(corvees.reglages) / "corvees.db").exists()


def test_doctor(corvees, capsys):
    assert corvees("doctor") == 0
    sortie = capsys.readouterr().out
    assert "Module éteint" in sortie and "Pas encore de nouvelles des capteurs" in sortie
    assert "lisible par toi seul" in sortie and "Claude ce mois-ci : 0.00 $ sur 2.00 $" in sortie
    ctx = corvees.contexte()
    ctx.base.ecrire(
        "sante",
        [
            {"capteur": "apps", "statut": "ok", "detail": ""},
            {"capteur": "fenetres", "statut": "désactivé", "detail": "autorisation Accessibilité"},
        ],
    )
    ctx.base.ecrire("battement", corvees.fin - 5)
    ctx.base.fermer()
    with mock.patch("core.config.module_actif", return_value=True):
        assert cli.main(["doctor"], corvees.contexte()) == 0
    sortie = capsys.readouterr().out
    assert "✅ Démon vivant (battement il y a 5 s)" in sortie
    assert "✅ Capteur apps ok" in sortie and "⚠️ Capteur fenetres désactivé : autorisation Accessibilité" in sortie


def test_doctor_bloquant_quand_le_demon_ne_tourne_pas(corvees, capsys):
    with mock.patch("core.config.module_actif", return_value=True):
        assert cli.main(["doctor"], corvees.contexte()) == 1
    assert "❌ Démon arrêté alors que le module est allumé" in capsys.readouterr().out


def test_doctor_base_lisible_par_d_autres(corvees, capsys):
    chemin = config.dossier_donnees(corvees.reglages) / "corvees.db"
    os.chmod(chemin, 0o644)
    corvees("doctor")  # en l'ouvrant, le détecteur la remet à 600
    assert "lisible par toi seul" in capsys.readouterr().out and oct(chemin.stat().st_mode)[-3:] == "600"
    with mock.patch.object(cli.stat, "S_IMODE", return_value=0o644):  # si la remise à 600 avait échoué
        corvees("doctor")
    assert "LISIBLE PAR D'AUTRES" in capsys.readouterr().out


def test_doctor_claude(monkeypatch):
    from core.cerveau import ClaudeIndisponible

    with mock.patch("core.cerveau.binaire_claude", side_effect=ClaudeIndisponible("introuvable")):
        assert cli._claude()[0] is None
    with mock.patch("core.cerveau.binaire_claude", return_value="/bin/claude"):
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")
        assert "jeton absent" in cli._claude()[1]
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
        assert cli._claude() == (True, "Claude : Claude Code trouvé, jeton présent")


def test_les_raccourcis(monkeypatch, tmp_path):
    monkeypatch.setenv("CORVEES_DOSSIER", str(tmp_path / "d"))
    with mock.patch("core.config.charger", return_value={"modules": {"corvees": {}}}):
        with mock.patch("core.config.module_actif", return_value=False):
            assert cli.main(["status"]) == 0


def test_derniers(corvees, capsys):
    assert corvees("derniers", "3") == 0
    sortie = capsys.readouterr().out.splitlines()
    assert sortie[0].startswith("🔎 Les 3 derniers événements notés") and len(sortie) == 4
    assert all(" · " in ligne and ":" in ligne for ligne in sortie[1:])
    assert corvees("derniers", "0") == 2


def test_derniers_sans_rien(tmp_path, monde, capsys):
    vide = Monde(tmp_path / "vide", monde)
    assert vide("derniers") == 0 and "Rien de noté" in capsys.readouterr().out


def test_derniers_avec_le_demon_vide_d_abord_son_tampon(dossier, monde, capsys):
    from modules.corvees.db import Evenement

    corvees = Monde(dossier, monde)
    demon = daemon.Demon(corvees.reglages, capteurs=[])
    corvees.demon = demon
    demon.base.ecrire("battement", corvees.fin)
    demon.base.ecrire("derniere_analyse", corvees.fin)
    demon.recevoir(Evenement(corvees.fin + 1, "apps", "app", "app:Tout_nouveau"))
    assert corvees("derniers", "1") == 0
    assert "app:Tout_nouveau" in capsys.readouterr().out
    demon.base.fermer()
