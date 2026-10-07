"""`quotidien doctor` (clair, sans rien modifier) et l'installation : LaunchAgent, commande, raccourcis signés,
relançable sans effet de bord, jamais un fichier qui n'est pas à nous, vérification « kill puis relance »."""

from __future__ import annotations

import plistlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quotidien import cli, config, daemon, doctor, installation, planification
from quotidien.db import Base as BaseDonnees
from quotidien.systeme import Resultat
from tests.faux_mac import FauxMac

PARIS = ZoneInfo("Europe/Paris")
MERCREDI = datetime(2026, 10, 14, 12, 0, tzinfo=PARIS).timestamp()


@pytest.fixture
def db(maison: Path) -> BaseDonnees:
    return BaseDonnees(config.chemin_base())


def test_doctor_tout_va_bien_puis_tout_va_mal(db: BaseDonnees) -> None:
    r = config.defauts()
    db.ecrire_meta("demon_battement", str(MERCREDI - 20))
    db.cx.execute("INSERT INTO meteo_cache(cle, recu_le, json) VALUES ('x', ?, '{}')", (MERCREDI - 3600,))
    from quotidien.repas import service

    service.produire(db, r, datetime(2026, 10, 12).date())
    config.icloud_drive().mkdir(parents=True)
    config.dossier_icloud().mkdir(parents=True)
    for nom in ("Mon frigo", "Envie de…"):
        (config.dossier_icloud() / f"{nom}.shortcut").write_bytes(b"x")
    db.cx.execute("INSERT INTO listes_apple(role, nom, creee_par_nous) VALUES ('courses', 'Courses (menu)', 1)")
    (config.dossier_support() / "profil.toml").write_text("", encoding="utf-8")
    agent = installation.EtatAgent(True, 4242, "0")
    lignes = doctor.bilan(db, r, FauxMac().systeme(), MERCREDI, contacts_statut=lambda: "ok", agent=lambda: agent,
                          client=lambda: SimpleNamespace(nom="abonnement Claude"))  # fmt: skip
    texte = doctor.texte(lignes)
    assert all(x.etat == doctor.OK for x in lignes), texte
    assert "actif (battement il y a 20 s), com." in texte and "pid 4242" in texte
    assert "prévision Open-Meteo reçue il y a 60 min" in texte and "semaine du 2026-10-12 (7 repas)" in texte
    assert "nos listes : Courses (menu)" in texte and "raccourcis déposés : 2/2" in texte
    assert "abonnement Claude · ce mois : 0.00 $ sur 2.00 $" in texte
    assert "Tâche : brief du matin" in texte and "prochaine : demain à 07:15" in texte
    assert "Tâche : menu de la semaine" in texte and "prochaine : dimanche 18 octobre à 17:00" in texte
    # Tout va mal : démon arrêté, réglages abîmés, pas de météo, Contacts refusés, pas d'IA, une tâche en échec.
    db.ecrire_meta("demon_battement", str(MERCREDI - 3600))
    db.ecrire_meta("erreur:brief", f"{MERCREDI}|RuntimeError")
    mauvais = config.Reglages(r.profil, r.reglages, ["profil.toml [repas] budget : …"])
    lignes = doctor.bilan(db, mauvais, FauxMac().systeme(), MERCREDI + 86400 * 8,
                          contacts_statut=lambda: "refuse", agent=lambda: installation.EtatAgent(False, None, None),
                          client=lambda: None)  # fmt: skip
    etats = {x.brique: x for x in lignes}
    assert etats["Démon"].etat == doctor.PROBLEME and "relance ./install.sh" in etats["Démon"].detail
    assert etats["Réglages"].etat == doctor.ATTENTION and etats["Contacts"].etat == doctor.ATTENTION
    assert "accès refusé" in etats["Contacts"].detail and etats["IA"].etat == doctor.ATTENTION
    assert "aucune (repli local partout)" in etats["IA"].detail
    assert etats["Tâche : brief du matin"].etat == doctor.ATTENTION and "RuntimeError" in etats[
        "Tâche : brief du matin"].detail  # fmt: skip
    assert etats["Menu"].etat == doctor.ATTENTION and etats["Météo"].etat == doctor.ATTENTION


def test_doctor_modes_degrades_et_commande(db: BaseDonnees, capsys: pytest.CaptureFixture[str]) -> None:
    r = config.defauts()
    r.reglages["rappels"]["active"] = False
    r.reglages["anniversaires"]["contacts"] = False
    r.reglages["ia"]["active"] = False
    lignes = {x.brique: x for x in doctor.bilan(db, r, FauxMac().systeme(), MERCREDI, agent=lambda: installation
                                                .EtatAgent(True, None, "1"))}  # fmt: skip
    assert lignes["Démon"].etat == doctor.ATTENTION and "silencieux" in lignes["Démon"].detail
    assert lignes["Réglages"].etat == doctor.ATTENTION and "profil.toml absent" in lignes["Réglages"].detail
    assert lignes["Tâche : brief du matin"].detail.startswith("prochaine : demain")
    sept_heures_et_demie = datetime(2026, 10, 14, 7, 30, tzinfo=PARIS).timestamp()  # brief dû, pas encore fait
    lignes = {x.brique: x for x in doctor.bilan(db, r, FauxMac().systeme(), sept_heures_et_demie)}
    assert lignes["Tâche : brief du matin"].detail.startswith("prochaine : maintenant")
    assert "désactivés dans reglages.toml" in lignes["Rappels"].detail
    assert "désactivés" in lignes["Contacts"].detail and "désactivée" in lignes["IA"].detail
    assert "iCloud Drive introuvable" in lignes["iCloud"].detail
    planification.noter(db, planification.echeances_du_jour(datetime(2026, 10, 14).date(), r.reglages)[0],
                        MERCREDI - 3600, "brief : 3 ligne(s)")  # fmt: skip
    lignes = {x.brique: x for x in doctor.bilan(db, r, FauxMac().systeme(), MERCREDI)}
    assert "dernière : aujourd'hui à 11:00" in lignes["Tâche : brief du matin"].detail
    assert cli.main(["doctor"], FauxMac().systeme(), lambda: MERCREDI) == 1  # démon arrêté
    assert "❌ Démon" in capsys.readouterr().out


def test_label_et_agent(maison: Path) -> None:
    assert installation.prefixe({"installation": {"prefixe_label": "Jean Dupont!"}}) == "jeandupont"
    assert installation.prefixe({"installation": {"prefixe_label": "!!!"}}) == "utilisateur"
    lab = installation.label({"installation": {"prefixe_label": "moi"}})
    assert lab == "com.moi.quotidien"
    p = installation.plist_agent(lab, Path("/x/.venv/bin/python"), Path("/x"))
    assert p["ProgramArguments"] == ["/x/.venv/bin/python", "-m", "quotidien", "demon"]
    assert p["RunAtLoad"] is True and p["KeepAlive"] is True and p["ThrottleInterval"] == 30
    assert ".local/bin" in p["EnvironmentVariables"]["PATH"]  # launchd n'hérite pas du shell : claude doit être trouvé


def test_preparer_relancable_et_prudent(maison: Path, tmp_path: Path) -> None:
    projet = tmp_path / "projet"
    projet.mkdir()
    (projet / "profil.example.toml").write_text('[repas]\nregime = "omnivore"\n', encoding="utf-8")
    r = config.defauts().reglages
    r["installation"]["prefixe_label"] = "moi"
    b = installation.preparer(r, Path("/usr/bin/python3"), projet)
    assert not b.refus and any("profil.toml" in x for x in b.fait)
    assert "iCloud Drive introuvable" in b.avertissements[0]
    agent = installation.chemin_agent("com.moi.quotidien")
    assert installation.agent_est_a_nous(agent) and installation.lanceur_est_a_nous(installation.lanceur())
    (config.dossier_support() / "profil.toml").write_text("# à moi\n", encoding="utf-8")
    config.icloud_drive().mkdir(parents=True)
    b = installation.preparer(r, Path("/usr/bin/python3"), projet)  # relancé : ton profil n'est pas écrasé
    assert (config.dossier_support() / "profil.toml").read_text(encoding="utf-8") == "# à moi\n"
    assert (config.dossier_icloud() / "entree").is_dir() and not b.avertissements
    # Un fichier qui n'est pas à nous : on s'arrête, rien n'est touché.
    agent.write_bytes(plistlib.dumps({"Label": "com.moi.quotidien", "ProgramArguments": ["/bin/autre"]}))
    b = installation.preparer(r, Path("/usr/bin/python3"), projet)
    assert b.refus and "n'est pas l'agent de Quotidien" in b.refus[0]
    assert plistlib.loads(agent.read_bytes())["ProgramArguments"] == ["/bin/autre"]
    d = installation.desinstaller(r)
    assert agent.exists() and not installation.lanceur().exists()  # l'agent étranger reste
    assert any("commande retirée" in x for x in d.fait)
    installation.lanceur().write_text("#!/bin/sh\necho autre\n", encoding="utf-8")
    assert any("n'est pas le lanceur de Quotidien" in x for x in installation.preparer(r, Path("/x"), projet).refus)


def test_desinstaller_tout(maison: Path) -> None:
    r = config.defauts().reglages
    for d in (config.dossier_support(), config.dossier_logs()):
        d.mkdir(parents=True)
    assert installation.desinstaller(r).fait == [] and config.dossier_support().exists()
    b = installation.desinstaller(r, tout=True)
    assert len(b.fait) == 2 and not config.dossier_support().exists()


def test_raccourcis_signes(maison: Path, tmp_path: Path) -> None:
    signes: list[Path] = []

    def signer(source: Path, destination: Path) -> tuple[bool, str]:
        destination.write_bytes(source.read_bytes())
        signes.append(destination)
        return True, ""

    b = installation.raccourcis(tmp_path / "sorties", signer)
    assert len(b.avertissements) == 2 and "pas d'iCloud Drive" in b.avertissements[0]
    config.icloud_drive().mkdir(parents=True)
    b = installation.raccourcis(tmp_path / "sorties", signer)
    assert len(b.fait) == 2 and {p.name for p in signes} == {"Mon frigo.shortcut", "Envie de….shortcut"}
    b = installation.raccourcis(tmp_path / "sorties", lambda s, d: (False, "pas de compte iCloud"))
    assert all("non signé (pas de compte iCloud)" in x for x in b.avertissements)


def test_verification_kill_relance_et_aller_retour(maison: Path, db: BaseDonnees) -> None:
    config.icloud_drive().mkdir(parents=True)
    r = config.defauts().reglages
    mac = FauxMac()
    mac.launchctl = [Resultat(0, "state = running\n\tpid = 100\n"), Resultat(0, "state = running\n\tpid = 100\n"),
                     Resultat(0, "state = running\n\tpid = 222\n")]  # fmt: skip
    horloge = [1000.0]
    demon = daemon.Demon(db, mac.systeme(), lambda: horloge[0])

    def attendre(s: float) -> None:
        horloge[0] += s
        import os

        for f in (config.dossier_icloud() / "entree").glob("*.txt"):
            os.utime(f, (0, 0))
        demon.tour_rapide()

    b = installation.verifier_reel(r, db, mac.systeme(), attendre, lambda: horloge[0])
    assert not b.refus, b.refus
    assert "tourne (pid 100)" in b.fait[0] and "relancé par launchd" in b.fait[1] and "pid 222" in b.fait[1]
    assert "réponse du démon" in b.fait[2] and b.fait[-1] == "fichiers de vérification retirés d'iCloud"
    assert ["kill", "-TERM", "100"] in mac.appels
    assert list((config.dossier_icloud() / "entree").iterdir()) == []
    assert list((config.dossier_icloud() / "reponses").iterdir()) == []
    assert db.lignes("SELECT * FROM frigo") == []  # la vérification ne touche pas ton frigo
    # Démon absent ; démon qui ne revient pas.
    assert "n'est pas lancé" in installation.verifier_reel(r, db, FauxMac().systeme()).refus[0]
    mac2 = FauxMac()
    mac2.launchctl = [Resultat(0, "pid = 5\n")] + [Resultat(0, "pid = 5\n")] * 100
    temps = [0.0]
    b = installation.verifier_reel(r, db, mac2.systeme(), lambda s: temps.__setitem__(0, temps[0] + s),
                                   lambda: temps[0], delai_relance=10)  # fmt: skip
    assert "n'a pas relancé le démon en 10 s" in b.refus[0]


def test_cli_installation(maison: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    mac = FauxMac()
    assert cli.main(["installation", "label"], mac.systeme()) == 0
    assert capsys.readouterr().out.strip().endswith(".quotidien")
    assert cli.main(["installation", "preparer", "--python", "/x/python", "--projet", str(tmp_path)],
                    mac.systeme()) == 0  # fmt: skip
    assert "agent de démarrage" in capsys.readouterr().out
    assert cli.main(["installation", "raccourcis"], mac.systeme()) == 0
    assert cli.main(["installation", "listes"], mac.systeme()) == 0
    assert "(aucune liste créée par Quotidien)" in capsys.readouterr().out
    assert cli.main(["installation", "supprimer-listes"], mac.systeme()) == 0
    assert cli.main(["installation", "desinstaller"], mac.systeme()) == 0
    assert "agent retiré" in capsys.readouterr().out
    assert cli.main(["installation", "desinstaller", "--tout"], mac.systeme()) == 0


def test_cli_brief(maison: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from quotidien.anniversaires import contacts

    monkeypatch.setattr(contacts, "contacts_du_mac", lambda: ("indisponible", []))
    monkeypatch.setattr(daemon, "_ligne_meteo", lambda *a: "☀️ Beau temps.")
    mac = FauxMac()
    assert cli.main(["brief"], mac.systeme(), lambda: MERCREDI) == 0
    sortie = capsys.readouterr().out
    assert "Page :" in sortie and mac.notifications == []
    assert cli.main(["brief", "--notifier"], mac.systeme(), lambda: MERCREDI) == 0
    assert mac.notifications and mac.notifications[0][0] == "☀️ Ma journée"
    assert "☀️ Beau temps." in capsys.readouterr().out


def _rien(*_: Any) -> None:
    return None
