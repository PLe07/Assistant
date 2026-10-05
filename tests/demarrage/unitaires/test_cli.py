"""La commande « demarrage » de bout en bout, sur le faux Mac n° 1 (launchd simulé qui se souvient)."""

import time

import pytest

from modules.demarrage import cli
from tests.demarrage.faux_mac.construire import construire
from tests.demarrage.faux_mac.launchd_simule import LaunchdSimule


@pytest.fixture(autouse=True)
def paris(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


@pytest.fixture
def faux(tmp_path):
    f = construire(tmp_path / "mac")
    f.a_l_instant(600)
    return f


def lancer(faux, reglages, *argv, activer=None):
    lignes: list[str] = []
    ctx = cli.Contexte(reglages, faux.mac, lignes.append, activer)
    code = cli.main(list(argv), ctx)
    return code, "\n".join(lignes)


def test_aide(capsys):
    assert cli.main([]) == 0
    sortie = capsys.readouterr().out
    assert all(
        c in sortie
        for c in ("scan", "mesurer", "rapport", "desactiver", "restaurer", "historique", "surveiller", "doctor")
    )


def test_scan_mesurer_rapport(faux, reglages):
    code, texte = lancer(faux, reglages, "scan")
    assert code == 0 and "éléments trouvés" in texte and "(18 de macOS)" in texte and "S5 dégradé" in texte
    code, texte = lancer(faux, reglages, "mesurer", "--minutes", "2")
    assert code == 0 and "✅ 25 relevés" in texte and "encore 1 min" in texte
    assert "1. 💤 Docker (réseau et socket)" in texte
    code, texte = lancer(faux, reglages, "rapport", "--sans-ouvrir")
    assert code == 0 and "Rapport :" in texte and not faux.mac.lancees("open")
    chemin = texte.rsplit("Rapport : ", 1)[1].strip()
    assert "Docker" in open(chemin, encoding="utf-8").read()
    code, _ = lancer(faux, reglages, "rapport")
    assert faux.mac.lancees("open") == [["open", chemin]]
    _, texte = lancer(faux, reglages, "scan")
    assert "Nouveaux depuis" not in texte  # rien de nouveau


def test_mesurer_sans_scan_prealable(faux, reglages):
    code, texte = lancer(faux, reglages, "mesurer", "--minutes", "0.5")
    assert code == 0 and "✅ 7 relevés" in texte


def test_desactiver_restaurer_historique(faux, reglages):
    lancer(faux, reglages, "scan")
    charges = {p.label: p.chemin_plist for p in faux.plantes if p.charge and p.source != "apple"}
    launchd = LaunchdSimule(faux.mac, charges)
    code, texte = lancer(faux, reglages, "desactiver", "com.docker.socket")
    assert code == 0 and "Simulation : rien n'a été modifié" in texte and "launchctl bootout" in texte
    assert "com.docker.socket" in launchd.charges
    ident = texte.split("[", 1)[1].split("]", 1)[0]
    code, texte = lancer(faux, reglages, "desactiver", ident[:5], "--confirmer")
    assert code == 0 and "✅ C'est fait" in texte and "com.docker.socket" in launchd.desactives
    code, texte = lancer(faux, reglages, "restaurer", ident)
    assert code == 0 and "Simulation" in texte and f"demarrage restaurer {ident} --confirmer" in texte
    code, texte = lancer(faux, reglages, "restaurer", "com.docker.socket", "--confirmer")
    assert code == 0 and "✅ C'est restauré" in texte and "com.docker.socket" in launchd.charges
    code, texte = lancer(faux, reglages, "historique")
    assert "com.docker.socket" in texte and "annulée le" in texte and "Tes ouvertures de session" in texte
    assert "Aucune observée" in texte


def test_desactiver_cas_speciaux(faux, reglages):
    lancer(faux, reglages, "scan")
    code, texte = lancer(faux, reglages, "desactiver", "com.apple.Finder", "--confirmer")
    assert code == 0 and "je n'y touche jamais" in texte
    code, texte = lancer(faux, reglages, "desactiver", "com.adobe.AdobeCreativeCloud", "--confirmer")
    assert code == 0 and "taper toi-même" in texte and "Pour annuler" in texte
    code, texte = lancer(faux, reglages, "desactiver", "com.mystere.agent")
    assert "Ne le supprime pas à l'aveugle" in texte
    code, texte = lancer(faux, reglages, "desactiver", "inconnu-total")
    assert code == 1 and "Je ne connais pas" in texte
    code, texte = lancer(faux, reglages, "desactiver", "com.exemple.doublon")
    assert code == 1 and "Plusieurs éléments" in texte
    code, texte = lancer(faux, reglages, "restaurer", "com.exemple.vpn.tunnel")
    assert code == 0 and "Rien à restaurer" in texte


def test_desactiver_qui_echoue(faux, reglages):
    from modules.demarrage.systeme import Resultat

    lancer(faux, reglages, "scan")
    launchd = LaunchdSimule(faux.mac, {"com.docker.socket": "/x"})
    faux.mac.repondre_debut(["launchctl", "disable"], Resultat(1, "", "refusé"))
    code, texte = lancer(faux, reglages, "desactiver", "com.docker.socket", "--confirmer")
    assert code == 1 and "❌ Rien n'a été modifié" in texte and "refusé" in texte
    faux.mac.repondre_debut(["launchctl", "disable"], launchd._disable)  # la désactivation passe…
    faux.mac.repondre_debut(["launchctl", "bootout"], Resultat(1, "", "non"))  # … l'arrêt non
    lancer(faux, reglages, "desactiver", "com.docker.socket", "--confirmer")
    faux.mac.repondre_debut(["launchctl", "enable"], Resultat(1, "", "toujours non"))
    code, texte = lancer(faux, reglages, "restaurer", "com.docker.socket", "--confirmer")
    assert code == 1 and "toujours non" in texte


def test_surveiller(faux, reglages):
    appels = []
    code, texte = lancer(faux, reglages, "surveiller", "on", activer=lambda n, a: appels.append((n, a)))
    assert code == 0 and "allumée" in texte
    code, texte = lancer(faux, reglages, "surveiller", "off", activer=lambda n, a: appels.append((n, a)))
    assert "éteinte" in texte and appels == [("demarrage", True), ("demarrage", False)]


def test_doctor(faux, reglages):
    code, texte = lancer(faux, reglages, "doctor")
    assert (
        code == 0
        and "macOS 26.0 · arm64" in texte
        and "Pas encore de scan" in texte
        and "lisible par toi seul" in texte
    )
    assert "Surveillance éteinte" in texte
    lancer(faux, reglages, "scan")
    faux.mac.commandes.discard("pmset")
    reglages["actif"] = True
    _, texte = lancer(faux, reglages, "doctor")
    assert "Dernier scan" in texte and "S5 dégradé" in texte and "pmset" in texte and "absente" in texte
    assert "elle ne tourne pas" in texte and "0 relevés" in texte


def test_doctor_conseille_l_automatisation_et_signale_les_bases_corrompues(faux, reglages):
    faux.mac.repondre_debut(["osascript"], "", code=1, erreur="Not authorized (-1743)")
    lancer(faux, reglages, "scan")
    from modules.demarrage import travail

    (travail.dossier(reglages) / "demarrage.db.corrompue-1").write_bytes(b"x")
    _, texte = lancer(faux, reglages, "doctor")
    assert "Automatisation → coche « System Events »" in texte and "corrompue(s) mise(s) de côté" in texte


def test_top_sans_chemin_personnel(faux, reglages):
    lancer(faux, reglages, "mesurer", "--minutes", "1")
    code, texte = lancer(faux, reglages, "top", "--nombre", "12")
    assert code == 0 and texte.count("\n| ") == 13  # l'en-tête + 12 lignes
    assert "| 1 | Docker (réseau et socket) | Docker Inc |" in texte and "`demarrage desactiver" in texte
    assert "à taper soi-même" in texte and "⚠️ Inconnu, à vérifier" in texte
    assert "/Users/" not in texte and "utilisateur" not in texte
