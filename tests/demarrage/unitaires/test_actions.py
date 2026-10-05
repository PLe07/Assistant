"""desactiver, quarantaine, journal, restaurer : sur le faux Mac n° 1, avec un launchd qui se souvient."""

import json
from pathlib import Path

import pytest

from modules.demarrage.actions import quarantaine
from modules.demarrage.actions.desactiver import applescript, desactiver, est_lecture, planifier
from modules.demarrage.actions.journal import Journal
from modules.demarrage.actions.restaurer import restaurer
from modules.demarrage.db import Base
from tests.demarrage.faux_mac.construire import construire
from tests.demarrage.faux_mac.juge import diagnostiquer
from tests.demarrage.faux_mac.launchd_simule import LaunchdSimule


@pytest.fixture
def monde(tmp_path, reglages):
    faux = construire(tmp_path / "mac")
    bilan = diagnostiquer(faux, tmp_path, reglages)
    charges = {p.label: p.chemin_plist for p in faux.plantes if p.charge and p.source != "apple"}
    launchd = LaunchdSimule(faux.mac, charges, ouverture={"zoom.us": "/Applications/zoom.us.app"})
    base = Base(tmp_path / "actions.db")
    yield faux, bilan, launchd, Journal(base), tmp_path / "donnees"
    base.fermer()


def element(bilan, label, source=None):
    return next(e for e in bilan.elements if e.fiche.label == label and (source is None or e.fiche.source == source))


def test_desactiver_puis_restaurer_un_agent(monde):
    faux, bilan, launchd, journal, dossier = monde
    docker = element(bilan, "com.docker.socket")
    simulation = desactiver(docker, faux.mac, journal, dossier)
    assert not simulation.fait and simulation.plan.genre == "launchd" and "com.docker.socket" in launchd.charges
    assert [c[1] for c in simulation.plan.commandes] == ["bootout", "disable"] and journal.toutes() == []
    fait = desactiver(docker, faux.mac, journal, dossier, confirmer=True)
    assert fait.fait and "C'est fait" in fait.message
    assert "com.docker.socket" not in launchd.charges and "com.docker.socket" in launchd.desactives
    action = journal.toutes()[0]
    assert action.avant == {"charge": True, "desactive": False} and action.apres == {"charge": False, "desactive": True}
    # Idempotent : une 2e fois, rien à faire, rien de noté.
    encore = desactiver(docker, faux.mac, journal, dossier, confirmer=True)
    assert not encore.fait and "déjà arrêté et désactivé" in encore.message and len(journal.toutes()) == 1
    # Restaurer : d'abord la simulation, puis pour de vrai.
    essai = restaurer(docker.fiche.id, faux.mac, journal)
    assert (
        not essai.fait
        and [c[1] for c in essai.commandes] == ["enable", "bootstrap"]
        and "com.docker.socket" in launchd.desactives
    )
    retour = restaurer(docker.fiche.id, faux.mac, journal, confirmer=True)
    assert retour.fait and "com.docker.socket" in launchd.charges and "com.docker.socket" not in launchd.desactives
    assert journal.toutes()[0].annulee is not None
    assert "Rien à restaurer" in restaurer(docker.fiche.id, faux.mac, journal, confirmer=True).message


def test_restaurer_ce_qui_est_deja_revenu_a_la_main(monde):
    faux, bilan, launchd, journal, dossier = monde
    keystone = element(bilan, "com.google.keystone.agent")
    desactiver(keystone, faux.mac, journal, dossier, confirmer=True)
    launchd.desactives.discard(keystone.fiche.label)  # tu l'as réactivé toi-même
    launchd.charges[keystone.fiche.label] = keystone.fiche.chemin_plist
    assert "déjà revenu" in restaurer(keystone.fiche.id, faux.mac, journal).message
    assert journal.a_annuler(keystone.fiche.id) is not None  # simulation : rien de noté
    assert "Noté au journal" in restaurer(keystone.fiche.id, faux.mac, journal, confirmer=True).message
    assert journal.a_annuler(keystone.fiche.id) is None


def test_quarantaine_et_retour(monde):
    faux, bilan, launchd, journal, dossier = monde
    parti = element(bilan, "com.exemple.desinstalle.agent")
    plist = faux.mac.chemin(parti.fiche.chemin_plist)
    contenu = plist.read_bytes()
    plan = planifier(parti, faux.mac)
    assert plan.genre == "quarantaine" and plan.commandes == [["launchctl", "bootout", f"gui/501/{parti.fiche.label}"]]
    assert desactiver(parti, faux.mac, journal, dossier).fait is False and plist.exists()
    fait = desactiver(parti, faux.mac, journal, dossier, confirmer=True)
    assert fait.fait and not plist.exists() and parti.fiche.label not in launchd.charges
    cible = Path(journal.toutes()[0].details["quarantaine"])
    manifeste = json.loads((cible / quarantaine.MANIFESTE).read_text())
    assert manifeste["original"] == parti.fiche.chemin_plist and manifeste["avant"]["charge"] is True
    assert (cible / plist.name).read_bytes() == contenu
    assert cible.parent == dossier / "quarantaine" and oct(cible.stat().st_mode)[-3:] == "700"
    assert "Rien à faire : son fichier n'est plus là" in desactiver(parti, faux.mac, journal, dossier).message
    retour = restaurer(parti.fiche.id, faux.mac, journal, confirmer=True)
    assert retour.fait and plist.read_bytes() == contenu and parti.fiche.label in launchd.charges
    assert (cible / f"{quarantaine.MANIFESTE}.restaure").exists()


def test_quarantaine_refuse_d_ecraser_ou_de_remettre_un_fichier_modifie(monde):
    faux, bilan, launchd, journal, dossier = monde
    for label in ("com.exemple.desinstalle.agent", "com.spotify.webhelper"):
        desactiver(element(bilan, label), faux.mac, journal, dossier, confirmer=True)
    parti, spotify = element(bilan, "com.exemple.desinstalle.agent"), element(bilan, "com.spotify.webhelper")
    faux.mac.fichier(parti.fiche.chemin_plist, b"un autre fichier a pris la place")
    assert "existe déjà" in restaurer(parti.fiche.id, faux.mac, journal, confirmer=True).message
    cible = Path(journal.a_annuler(spotify.fiche.id).details["quarantaine"])
    (cible / "com.spotify.webhelper.plist").write_bytes(b"modifie")
    assert "modifié" in restaurer(spotify.fiche.id, faux.mac, journal, confirmer=True).message


def test_deux_quarantaines_la_meme_seconde(mac, tmp_path):
    for i in range(2):
        mac.fichier(f"/Users/utilisateur/Library/LaunchAgents/x{i}.plist", b"<plist/>")
    a = quarantaine.mettre(mac, "/Users/utilisateur/Library/LaunchAgents/x0.plist", tmp_path, {})
    b = quarantaine.mettre(mac, "/Users/utilisateur/Library/LaunchAgents/x1.plist", tmp_path, {})
    assert a != b and b.name.endswith("-2")


def test_element_d_ouverture(monde):
    faux, bilan, launchd, journal, dossier = monde
    zoom = element(bilan, "us.zoom.xos", "ouverture")
    plan = planifier(zoom, faux.mac)
    assert plan.genre == "system_events" and "delete login item" in plan.commandes[0][-1]
    fait = desactiver(zoom, faux.mac, journal, dossier, confirmer=True)
    assert fait.fait and "zoom.us" not in launchd.ouverture
    retour = restaurer(zoom.fiche.id, faux.mac, journal, confirmer=True)
    assert retour.fait and launchd.ouverture["zoom.us"] == "/Applications/zoom.us.app"


def test_element_d_ouverture_sans_autorisation(monde):
    faux, bilan, launchd, journal, dossier = monde
    launchd.automatisation = False
    r = desactiver(element(bilan, "us.zoom.xos", "ouverture"), faux.mac, journal, dossier, confirmer=True)
    assert not r.fait and "Automatisation" in r.message and "Ouvrir à la connexion" in r.message
    assert journal.toutes() == []
    faux.mac.commandes.discard("osascript")
    plan = planifier(element(bilan, "us.zoom.xos", "ouverture"), faux.mac)
    assert plan.genre == "instructions" and "Réglages Système" in plan.texte


def test_refus_instructions_verification(monde):
    faux, bilan, launchd, journal, dossier = monde
    avant = len(faux.mac.appels)
    for label, source, genre, morceau in [
        ("com.apple.Finder", None, "refus", "macOS"),
        ("com.assistant.superviseur", None, "refus", "C'est moi"),
        ("com.adobe.AdobeCreativeCloud", None, "instructions", "launchctl bootout gui/501/com.adobe.Adobe"),
        ("com.exemple.vpn.daemon", "daemon_global", "instructions", "sudo launchctl bootout system/com.exemple.vpn"),
        ("com.ancien.helper", None, "instructions", "sudo mv /Library/PrivilegedHelperTools/com.ancien.helper ~/"),
        ("com.exemple.vpn.daemon", "assistant_privilegie", "instructions", "lancé par le daemon"),
        ("com.exemple.vpn.tunnel", None, "instructions", "Extensions"),
        ("cron : absent", None, "instructions", "crontab -e"),
        ("com.mystere.agent", None, "verifier", "codesign -dv --verbose=2"),
        ("com.exemple.Étiquette avec espaces", None, "rien", ""),
    ]:  # fmt: skip
        e = element(bilan, label, source)
        r = desactiver(e, faux.mac, journal, dossier, confirmer=True)
        assert not r.fait and r.plan.genre == genre, label
        assert morceau in r.plan.texte + r.plan.message, label
    assert all(est_lecture(c) for c in faux.mac.appels[avant:])
    assert journal.toutes() == []


def test_echec_partiel_note_et_restaurable(monde):
    faux, bilan, launchd, journal, dossier = monde
    from modules.demarrage.systeme import Resultat

    faux.mac.repondre_debut(["launchctl", "disable"], Resultat(1, "", "Operation not permitted"))
    notes = element(bilan, "com.notesrapides.agent")
    r = desactiver(notes, faux.mac, journal, dossier, confirmer=True)
    assert r.fait and "en partie" in r.message and "Operation not permitted" in r.erreurs[0]
    assert notes.fiche.label not in launchd.charges
    retour = restaurer(notes.fiche.id, faux.mac, journal, confirmer=True)
    assert retour.fait and [c[1] for c in retour.commandes] == ["bootstrap"] and notes.fiche.label in launchd.charges


def test_echec_complet(monde):
    faux, bilan, launchd, journal, dossier = monde
    from modules.demarrage.systeme import Resultat

    faux.mac.repondre_debut(["launchctl", "bootout"], Resultat(1, "", "refusé"))
    r = desactiver(element(bilan, "com.docker.socket"), faux.mac, journal, dossier, confirmer=True)
    assert not r.fait and r.message == "Rien n'a été modifié." and journal.toutes() == []
    faux.mac.repondre_debut(["launchctl", "bootout"], Resultat(0, ""))  # bootout « réussi » mais rien ne change
    r = desactiver(element(bilan, "com.docker.socket"), faux.mac, journal, dossier, confirmer=True)
    assert r.fait and "ne le montre pas encore" in r.message


def test_restaurer_qui_echoue(monde):
    faux, bilan, launchd, journal, dossier = monde
    from modules.demarrage.systeme import Resultat

    docker = element(bilan, "com.docker.socket")
    desactiver(docker, faux.mac, journal, dossier, confirmer=True)
    faux.mac.repondre_debut(["launchctl", "enable"], Resultat(1, "", "non"))
    r = restaurer(docker.fiche.id, faux.mac, journal, confirmer=True)
    assert not r.fait and r.erreurs and journal.a_annuler(docker.fiche.id) is not None


def test_est_lecture_et_applescript():
    assert est_lecture(["launchctl", "print", "gui/501"]) and est_lecture(["ps", "-axo", "pid="])
    assert est_lecture(
        ["osascript", "-e", 'tell application "System Events"', "-e", "repeat with e in every login item"]
    )
    for c in (["launchctl", "bootout", "gui/501/x"], ["launchctl"], ["osascript", "-e", "delete every login item"],
              ["mv", "a", "b"], ["crontab", "-r"], ["pmset", "sleepnow"], ["open", "x"]):  # fmt: skip
        assert not est_lecture(c), c
    assert applescript('Mon "App" \\ x') == '"Mon \\"App\\" \\\\ x"'
