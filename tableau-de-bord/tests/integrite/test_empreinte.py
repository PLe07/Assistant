"""L'empreinte « avant » des autres projets (§1.1) : elle voit chaque changement de code ou de réglage, ignore les
données vivantes et notre propre dossier, et ne modifie rien."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "integrite" / "empreinte.py"


def _git(dossier: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(dossier), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})  # fmt: skip


def monde(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Une maison imitée : le dépôt de l'assistant (avec tableau-de-bord/ dedans), ~/Projets/ambiance, des
    LaunchAgents, Application Support, et un faux launchctl."""
    maison = tmp_path / "maison"
    depot = maison / "Assistant"
    (depot / "modules" / "trieur").mkdir(parents=True)
    (depot / "modules" / "trieur" / "config.py").write_text("SEUIL = 0.75\n")
    (depot / "reglages.json").write_text("{}\n")
    (depot / "logs").mkdir()
    (depot / "logs" / "assistant.log").write_text("ligne\n")
    (depot / "donnees").mkdir()
    (depot / "donnees" / "etat.db").write_bytes(b"x")
    notre = depot / "tableau-de-bord" / "integrite"
    notre.mkdir(parents=True)
    shutil.copy(SCRIPT, notre / "empreinte.py")
    (depot / "tableau-de-bord" / "README.md").write_text("nous\n")
    _git(depot, "init", "-q")
    _git(depot, "add", "-A")
    _git(depot, "commit", "-qm", "départ")
    ambiance = maison / "Projets" / "ambiance"
    ambiance.mkdir(parents=True)
    (ambiance / "main.py").write_text("print('ambiance')\n")
    (ambiance / "audio.log").write_text("vivant\n")
    agents = maison / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    for label in ("com.exemple.bouclier", "com.exemple.tableau"):
        with open(agents / f"{label}.plist", "wb") as f:
            plistlib.dump({"Label": label, "ProgramArguments": ["/bin/true"]}, f)
    support = maison / "Library" / "Application Support" / "Bouclier"
    support.mkdir(parents=True)
    (support / "config.toml").write_text("[ia]\nbudget_mensuel_usd = 2.0\n")
    (support / "etat.json").write_text('{"vivant": 1}\n')
    (maison / "Library" / "Application Support" / "TableauDeBord").mkdir()
    (maison / "Library" / "Application Support" / "TableauDeBord" / "reglages.toml").write_text("x = 1\n")
    (maison / ".zshrc").write_text("export X=1\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    launchctl = bin_ / "launchctl"
    launchctl.write_text('#!/bin/sh\ncat "$FAUX_LAUNCHCTL"\n')
    launchctl.chmod(0o755)
    liste = tmp_path / "liste.txt"
    liste.write_text("PID\tStatus\tLabel\n123\t0\tcom.exemple.bouclier\n-\t0\tcom.exemple.tableau\n")
    return maison, notre / "empreinte.py", liste


def lancer(script: Path, maison: Path, liste: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "TABLEAU_INTEGRITE_MAISON": str(maison), "FAUX_LAUNCHCTL": str(liste),
           "PATH": f"{liste.parent / 'bin'}:{os.environ['PATH']}"}  # fmt: skip
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, env=env)


def tout(dossier: Path) -> dict[str, tuple[str, int]]:
    return {
        str(p.relative_to(dossier)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in sorted(dossier.rglob("*"))
        if p.is_file() and ".git" not in p.parts and "etat_avant.json" not in p.name
    }


@pytest.fixture
def capture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    maison, script, liste = monde(tmp_path)
    ref = tmp_path / "etat_avant.json"
    r = lancer(script, maison, liste, "capturer", str(ref))
    assert r.returncode == 0, r.stderr
    return maison, script, liste, ref


def test_capture_puis_comparaison_identique_sans_rien_modifier(capture: tuple[Path, Path, Path, Path]) -> None:
    maison, script, liste, ref = capture
    avant = tout(maison)
    r = lancer(script, maison, liste, "comparer", str(ref))
    assert r.returncode == 0 and "INTÉGRITÉ OK" in r.stdout, r.stdout + r.stderr
    assert tout(maison) == avant, "l'empreinte a modifié un fichier"
    etat = json.loads(ref.read_text())
    fichiers = etat["projets"]["depot_hote"]["fichiers"]
    assert "modules/trieur/config.py" in fichiers and "reglages.json" in fichiers
    assert not any(f.startswith("tableau-de-bord/") for f in fichiers), "notre dossier ne doit pas compter"
    assert not any(f.startswith(("logs/", "donnees/")) for f in fichiers)
    assert "projets/ambiance" in etat["projets"] and "audio.log" not in etat["projets"]["projets/ambiance"]["fichiers"]
    assert "com.exemple.bouclier" in etat["launch_agents"] and "com.exemple.tableau" not in etat["launch_agents"]
    assert etat["launch_agents"]["com.exemple.bouclier"]["launchd"] == {"charge": True, "tourne": True,
                                                                        "dernier_code": "0"}  # fmt: skip
    assert "Bouclier/config.toml" in etat["application_support"]
    assert "Bouclier/etat.json" not in etat["application_support"]
    assert not any(k.startswith("TableauDeBord") for k in etat["application_support"])


@pytest.mark.parametrize(
    "changement, attendu",
    [
        (lambda m: (m / "Assistant" / "modules" / "trieur" / "config.py").write_text("SEUIL = 0.5\n"), "config.py"),
        (lambda m: (m / "Projets" / "ambiance" / "main.py").write_text("x\n"), "main.py"),
        (lambda m: (m / "Library" / "LaunchAgents" / "com.exemple.bouclier.plist").write_bytes(b"x"), "bouclier"),
        (lambda m: (m / "Library" / "Application Support" / "Bouclier" / "config.toml").write_text("x"), "config.toml"),
        (lambda m: (m / ".zshrc").write_text("export X=2\n"), ".zshrc"),
        (lambda m: (m / "Assistant" / "nouveau.py").write_text("x"), "nouveau.py"),
        (lambda m: (m / "Library" / "LaunchAgents" / "com.exemple.tdbtest.1.plist").write_bytes(b"x"), "tdbtest"),
    ],
)
def test_chaque_changement_est_vu(capture: tuple[Path, Path, Path, Path], changement, attendu: str) -> None:
    maison, script, liste, ref = capture
    changement(maison)
    r = lancer(script, maison, liste, "comparer", str(ref))
    assert r.returncode == 1 and attendu in r.stdout, r.stdout


def test_un_agent_arrete_ou_un_agent_de_test_reste_charge(capture: tuple[Path, Path, Path, Path]) -> None:
    maison, script, liste, ref = capture
    liste.write_text("PID\tStatus\tLabel\n-\t1\tcom.exemple.bouclier\n-\t0\tcom.exemple.tdbtest.3\n")
    r = lancer(script, maison, liste, "comparer", str(ref))
    assert r.returncode == 1 and "tourne" in r.stdout and "com.exemple.tdbtest.3" in r.stdout


def test_donnees_vivantes_et_notre_dossier_ignores(capture: tuple[Path, Path, Path, Path]) -> None:
    maison, script, liste, ref = capture
    (maison / "Assistant" / "logs" / "assistant.log").write_text("autre\n")
    (maison / "Assistant" / "donnees" / "etat.db").write_bytes(b"y")
    (maison / "Assistant" / "tableau-de-bord" / "nouveau.py").write_text("nous\n")
    (maison / "Projets" / "ambiance" / "audio.log").write_text("encore\n")
    (maison / "Library" / "Application Support" / "Bouclier" / "etat.json").write_text("{}")
    (maison / "Library" / "Application Support" / "TableauDeBord" / "reglages.toml").write_text("y = 2\n")
    (maison / "Library" / "LaunchAgents" / "com.exemple.tableau.plist").write_bytes(b"autre")
    r = lancer(script, maison, liste, "comparer", str(ref))
    assert r.returncode == 0, r.stdout


def test_usage(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 2 and "Usage" in r.stdout


def test_verifier_sh_hors_mac_utilise_la_reference_du_depot() -> None:
    verifier = SCRIPT.parent / "verifier.sh"
    assert os.access(verifier, os.X_OK)
    texte = verifier.read_text()
    assert "integrite/mac" not in texte or "$ICI/mac" in texte
    assert 'REF="$ICI/etat_avant.json"' in texte
