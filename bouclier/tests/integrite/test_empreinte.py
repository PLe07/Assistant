"""§1 : l'empreinte « avant » voit tout écart chez les autres projets, et rien de ce que Bouclier fait chez lui."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

RACINE = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("empreinte_test", RACINE / "integrite" / "empreinte.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["empreinte_test"] = m
    spec.loader.exec_module(m)
    return m


def _git(depot: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=depot, check=True,
                   capture_output=True)  # fmt: skip


@pytest.fixture
def faux_mac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path, Path]:
    m = _module()
    maison = tmp_path / "home"
    depot = maison / "Assistant"
    (depot / "modules" / "trieur").mkdir(parents=True)
    (depot / "modules" / "trieur" / "config.py").write_text("X = 1\n")
    (depot / "reglages.json").write_text("{}\n")
    (depot / ".gitignore").write_text("donnees/\nreglages.json\n")
    (depot / "donnees").mkdir()
    (depot / "donnees" / "etat.db").write_text("vivant")
    bouclier = depot / "bouclier"
    bouclier.mkdir()
    (bouclier / "a.py").write_text("print(1)\n")
    _git(depot, "init", "-q")
    _git(depot, "add", ".")
    _git(depot, "commit", "-q", "-m", "init")
    (maison / "Projets" / "ambiance").mkdir(parents=True)
    (maison / "Projets" / "ambiance" / "main.py").write_text("pass\n")
    agents = maison / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.exemple.trieur.plist").write_text("<plist/>")
    (maison / "Library" / "Application Support" / "Trieur").mkdir(parents=True)
    (maison / "Library" / "Application Support" / "Trieur" / "reglages.json").write_text("{}")
    (maison / ".zshrc").write_text("export A=1\n")
    boite = maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "BoiteMac"
    boite.mkdir(parents=True)
    monkeypatch.setattr(m, "MAISON", maison)
    monkeypatch.setattr(m, "RACINE_BOUCLIER", bouclier.resolve())
    monkeypatch.setattr(m, "ICLOUD", maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    return m, maison, depot


def test_identique_puis_ecarts(faux_mac: tuple[ModuleType, Path, Path]) -> None:
    m, maison, depot = faux_mac
    avant = m.capturer()
    assert "depot_hote" in avant["projets"] and "projets/ambiance" in avant["projets"]
    assert "modules/trieur/config.py" in avant["projets"]["depot_hote"]["fichiers"]
    assert "bouclier/a.py" not in avant["projets"]["depot_hote"]["fichiers"]
    assert m.comparer(avant, m.capturer()) == []

    # Ce que Bouclier fait chez lui, et ce que les projets écrivent eux-mêmes en tournant : aucun écart.
    (depot / "bouclier" / "a.py").write_text("print(2)\n")
    (depot / "bouclier" / "nouveau.py").write_text("x\n")
    (depot / "donnees" / "etat.db").write_text("a bougé tout seul")
    (maison / "Library" / "LaunchAgents" / "com.exemple.bouclier.plist").write_text("<plist/>")
    assert m.comparer(avant, m.capturer()) == []

    # Un octet changé chez un autre projet : écart.
    (depot / "modules" / "trieur" / "config.py").write_text("X = 2\n")
    (maison / "Projets" / "ambiance" / "main.py").write_text("pass # \n")
    (maison / ".zshrc").write_text("export A=2\n")
    (maison / "Library" / "LaunchAgents" / "com.exemple.trieur.plist").write_text("<plist> </plist>")
    (maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "BoiteMac" / "f.pdf").write_text("x")
    ecarts = m.comparer(avant, m.capturer())
    texte = "\n".join(ecarts)
    for attendu in ("modules/trieur/config.py", "ambiance", ".zshrc", "com.exemple.trieur", "BoiteMac",
                    "status_porcelain"):  # fmt: skip
        assert attendu in texte, attendu


def test_ligne_de_commande(faux_mac: tuple[ModuleType, Path, Path], tmp_path: Path,
                           capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    m, _, depot = faux_mac
    ref = tmp_path / "ref" / "etat.json"
    assert m.main(["empreinte", "capturer", str(ref)]) == 0
    assert m.main(["empreinte", "comparer", str(ref)]) == 0
    assert "INTÉGRITÉ OK" in capsys.readouterr().out
    (depot / "reglages.json").write_text('{"x": 1}\n')
    assert m.main(["empreinte", "comparer", str(ref)]) == 1
    assert "reglages.json" in capsys.readouterr().out
    assert m.main(["empreinte"]) == 2


def test_verifier_sh_du_depot_reel() -> None:
    """Le vrai verifier.sh, sur ce dépôt : identique à l'empreinte prise avant la première ligne de Bouclier."""
    r = subprocess.run([str(RACINE / "integrite" / "verifier.sh")], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "INTÉGRITÉ OK" in r.stdout


def test_etat_launchd_sans_numero_de_processus(faux_mac: tuple[ModuleType, Path, Path],
                                               monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """Un redémarrage du Mac change le pid d'un agent : pas un écart. Un agent arrêté ou déchargé : un écart."""
    m, _, _ = faux_mac
    sortie = ["PID\tStatus\tLabel\n412\t0\tcom.exemple.trieur\n"]

    def commande(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
        if args[:2] == ["launchctl", "list"]:
            return 0, sortie[0]
        return m._commande_origine(args, cwd)

    monkeypatch.setattr(m, "_commande_origine", m._commande, raising=False)
    monkeypatch.setattr(m, "_commande", commande)
    avant = m.capturer()
    assert avant["launch_agents"]["com.exemple.trieur"]["launchd"] == {"charge": True, "tourne": True}
    sortie[0] = "PID\tStatus\tLabel\n9001\t0\tcom.exemple.trieur\n"
    assert m.comparer(avant, m.capturer()) == []
    sortie[0] = "PID\tStatus\tLabel\n-\t0\tcom.exemple.trieur\n"
    assert any("tourne" in e for e in m.comparer(avant, m.capturer()))
    sortie[0] = "PID\tStatus\tLabel\n"
    assert any("charge" in e for e in m.comparer(avant, m.capturer()))
