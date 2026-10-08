"""L'installation (§7) : ce qu'install.sh pose (agent, commande, dossiers, registre), relançable sans effet de bord,
jamais par-dessus ce qui n'est pas à nous ; la vérification réelle d'un démon en marche ; la désinstallation qui ne
laisse rien et ne touche à rien d'autre. Et les scripts eux-mêmes : pas de sudo, launchctl seulement sur notre label."""

from __future__ import annotations

import plistlib
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tableau import cli, config, daemon, installation, systeme
from tableau.notifier import NotificateurMemoire
from tableau.web import serveur

PROJET = Path(__file__).resolve().parents[2]


@pytest.fixture
def chemins(maison: Path) -> config.Chemins:
    return config.Chemins(maison)


def reglages(c: config.Chemins) -> config.Reglages:
    r = config.charger(c.reglages)
    r.valeurs["installation"]["prefixe_label"] = "moi"
    return r


def test_preparer_puis_relancer(chemins: config.Chemins, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    r = reglages(chemins)
    b = installation.preparer(chemins, r, Path("/opt/python3"), PROJET)
    assert b.refus == [] and len(b.fait) == 4, b.texte()
    agent = chemins.launch_agents / "com.moi.tableau.plist"
    p = plistlib.loads(agent.read_bytes())
    assert p["ProgramArguments"] == ["/opt/python3", "-m", "tableau", "demon"]
    assert p["RunAtLoad"] is True and p["KeepAlive"] is True and p["ThrottleInterval"] == 30 and p["Nice"] == 10
    assert p["LimitLoadToSessionType"] == "Aqua" and p["StandardErrorPath"].endswith(
        "Logs/TableauDeBord/demon.erreurs.log"
    )
    lanceur = chemins.maison / ".local" / "bin" / "tableau"
    assert lanceur.read_text().endswith('exec "/opt/python3" -m tableau "$@"\n') and lanceur.stat().st_mode & 0o111
    assert chemins.registre.exists() and (chemins.support / "jeton").exists()
    registre_avant = chemins.registre.read_text()
    chemins.registre.write_text(registre_avant + "\n# ma note\n")
    # Relancer : rien ne casse, le registre (à toi) est gardé tel quel.
    b2 = installation.preparer(chemins, r, Path("/opt/python3"), PROJET)
    assert b2.refus == [] and "registre déjà présent : gardé tel quel" in b2.fait
    assert chemins.registre.read_text().endswith("# ma note\n")
    assert "iCloud Drive introuvable" in b2.texte()


def test_jamais_par_dessus_ce_qui_n_est_pas_a_nous(chemins: config.Chemins, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    r = reglages(chemins)
    chemins.launch_agents.mkdir(parents=True)
    etranger = chemins.launch_agents / "com.moi.tableau.plist"
    etranger.write_bytes(plistlib.dumps({"Label": "com.moi.tableau", "ProgramArguments": ["/bin/autre"]}))
    lien = chemins.maison / ".local" / "bin" / "tableau"
    lien.parent.mkdir(parents=True)
    lien.write_text("#!/bin/sh\necho autre chose\n")
    b = installation.preparer(chemins, r, Path("/opt/python3"), PROJET)
    assert len(b.refus) == 2 and b.fait == []
    assert etranger.read_bytes() == plistlib.dumps({"Label": "com.moi.tableau", "ProgramArguments": ["/bin/autre"]})
    autre = chemins.maison / "bin" / "tableau"
    autre.parent.mkdir()
    autre.write_text("#!/bin/sh\n")
    autre.chmod(0o755)
    monkeypatch.setenv("PATH", f"{autre.parent}:/usr/bin")
    assert any("une autre commande « tableau »" in x for x in installation.collisions(chemins, "com.moi.tableau"))
    # La désinstallation ne les touche pas non plus.
    d = installation.desinstaller(chemins, r)
    assert len(d.refus) == 2 and etranger.exists() and lien.exists()
    assert not installation.agent_est_a_nous(chemins.maison / "rien.plist")


def test_verifier_un_vrai_demon_puis_desinstaller(
    chemins: config.Chemins, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    icloud = tmp_path / "CloudDocs"
    icloud.mkdir()
    monkeypatch.setenv("TABLEAU_ICLOUD", str(icloud))
    r = reglages(chemins)
    assert installation.preparer(chemins, r, Path("/opt/python3"), PROJET).refus == []
    # Ce qui appartient aux autres, à côté du nôtre : jamais touché.
    autre_agent = chemins.launch_agents / "com.moi.bouclier.plist"
    autre_agent.write_bytes(plistlib.dumps({"Label": "com.moi.bouclier", "ProgramArguments": ["/bin/true"]}))
    autre_support = chemins.maison / "Library" / "Application Support" / "Bouclier"
    autre_support.mkdir(parents=True)
    (autre_support / "config.toml").write_text("x = 1\n")
    (icloud / "Bouclier").mkdir()
    # Pas encore de démon : la vérification le dit, sans attendre indéfiniment.
    b = installation.verifier(chemins, attendre=lambda _s: None, delai_s=0.01)
    assert b.refus and "pas fait de tour" in b.refus[0]
    # Le démon et sa page, un tour.
    d = daemon.Demon(chemins, r, daemon.Branchements(
        notificateur=NotificateurMemoire(), launchctl=lambda _a: systeme.Resultat(0, "PID\tStatus\tLabel\n"),
        docker=lambda _a: systeme.Resultat(1, "", "Cannot connect to the Docker daemon"), surveiller_fichiers=False,
    ))  # fmt: skip
    page = serveur.ouvrir(d.source, d.jeton, 0).demarrer()
    try:
        d.base.ecrire_meta("port", str(page.port))
        d.tour()
        b = installation.verifier(chemins, delai_s=5)
        assert b.refus == [], b.texte()
        assert any("refusée sans jeton" in x for x in b.fait)
        assert (icloud / "Tableau" / "Etat.html").exists()
    finally:
        page.arreter()
        d.fermer()
    # Désinstaller : tout ce qui est à nous part, le reste reste.
    d2 = installation.desinstaller(chemins, r)
    assert d2.refus == [], d2.texte()
    assert not (chemins.launch_agents / "com.moi.tableau.plist").exists()
    assert not (chemins.maison / ".local" / "bin" / "tableau").exists()
    assert not chemins.support.exists() and not chemins.logs.exists() and not (icloud / "Tableau").exists()
    assert autre_agent.exists() and (autre_support / "config.toml").read_text() == "x = 1\n"
    assert (icloud / "Bouclier").is_dir()
    # Relancer la désinstallation : rien à faire, rien ne casse.
    assert installation.desinstaller(chemins, r).fait == []


def test_la_commande_installation(chemins: config.Chemins, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    chemins.preparer()
    chemins.reglages.write_text('[installation]\nprefixe_label = "moi"\n', encoding="utf-8")
    assert cli.main(["installation", "label"]) == 0 and capsys.readouterr().out == "com.moi.tableau\n"
    assert cli.main(["installation", "preparer"]) == 2
    assert cli.main(["installation", "preparer", "--python", "/opt/python3", "--projet", str(PROJET)]) == 0
    assert "agent de démarrage" in capsys.readouterr().out
    assert cli.main(["installation", "desinstaller"]) == 0
    assert "agent retiré" in capsys.readouterr().out


SCRIPTS = [PROJET / "install.sh", PROJET / "uninstall.sh"]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_les_scripts(script: Path) -> None:
    texte = script.read_text(encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    lignes = [ligne for ligne in texte.splitlines() if not ligne.lstrip().startswith("#")]
    code = "\n".join(lignes)
    assert not re.search(r"(^|[;&|]\s*)sudo\b", code, re.M), "jamais de sudo"
    # launchctl : seulement sur notre label (ou notre plist).
    for ligne in lignes:
        if "launchctl " in ligne and not re.search(r"launchctl (print|list)\b", ligne):
            assert "$LABEL" in ligne or "$PLIST" in ligne, ligne
    assert "empreinte.py comparer" in code and "empreinte.py capturer" in code
    assert '[ "$(id -u)" != "0" ]' in code  # refuse de tourner en root
