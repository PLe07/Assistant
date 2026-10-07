"""L'empreinte d'intégrité (§1.1) : elle voit un octet changé, et ignore ce qui est à Quotidien."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

RACINE = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("empreinte", RACINE / "integrite" / "empreinte.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def empreinte() -> ModuleType:
    return _module()


def test_fichiers_du_projet_voit_un_octet_change(tmp_path: Path, empreinte: ModuleType) -> None:
    (tmp_path / "code.py").write_text("print(1)\n")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "x.log").write_text("vivant")
    (tmp_path / "base.db").write_text("vivant")
    avant = empreinte.fichiers_du_projet(tmp_path, None)
    assert set(avant) == {"code.py"}
    (tmp_path / "code.py").write_text("print(2)\n")
    assert empreinte.fichiers_du_projet(tmp_path, None) != avant


def test_quotidien_est_exclu_du_depot_hote(tmp_path: Path, empreinte: ModuleType) -> None:
    (tmp_path / "a.txt").write_text("a")
    nous = tmp_path / "quotidien"
    nous.mkdir()
    (nous / "b.txt").write_text("b")
    assert set(empreinte.fichiers_du_projet(tmp_path, nous)) == {"a.txt"}


def test_comparer_signale_chaque_ecart(empreinte: ModuleType) -> None:
    ref = {"projets": {"p": {"fichiers": {"a": "1"}}}, "launch_agents": {}, "application_support": {}, "divers": {},
           "rappels": {"Courses": "3"}}  # fmt: skip
    act = json.loads(json.dumps(ref))
    assert empreinte.comparer(ref, act) == []
    act["projets"]["p"]["fichiers"]["a"] = "2"
    act["rappels"]["Courses"] = "4"
    ecarts = empreinte.comparer(ref, act)
    assert len(ecarts) == 2


def test_nos_listes_de_rappels_creees_apres_ne_comptent_pas(empreinte: ModuleType) -> None:
    ref = {"rappels": {"Courses": "3", "Anniversaires": "2"}}
    act = {"rappels": {"Courses": "3", "Anniversaires": "2", "Anniversaires (Quotidien)": "5", "Courses (menu)": "9"}}
    assert empreinte.comparer(ref, act) == []
    # Mais une liste d'un nom à nous qui existait AVANT est celle de quelqu'un d'autre : elle est comparée.
    act["rappels"]["Anniversaires"] = "3"
    assert len(empreinte.comparer(ref, act)) == 1
    # Et une liste inconnue apparue est un écart.
    act["rappels"]["Anniversaires"] = "2"
    act["rappels"]["Travail"] = "1"
    assert len(empreinte.comparer(ref, act)) == 1


def test_rappels_indisponibles(empreinte: ModuleType) -> None:
    assert empreinte.comparer({"rappels": {"(listes)": "indisponible"}}, {"rappels": {"X": "1"}}) == []
    assert empreinte.comparer({"rappels": {"X": "1"}}, {"rappels": {"(listes)": "indisponible"}}) != []


def test_notre_label_et_nos_raccourcis_exclus(empreinte: ModuleType) -> None:
    assert empreinte.NOTRE_LABEL.match("com.camille.quotidien")
    assert not empreinte.NOTRE_LABEL.match("com.camille.bouclier")
    assert not empreinte.NOTRE_LABEL.match("com.camille.quotidien.autre")
    assert "Mon frigo" in empreinte.NOS_RACCOURCIS and "Envie de…" in empreinte.NOS_RACCOURCIS


def test_launch_agents_et_support(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empreinte: ModuleType) -> None:
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.camille.corvees.plist").write_text("<plist/>")
    (agents / "com.camille.quotidien.plist").write_text("<plist/>")
    support = tmp_path / "Library" / "Application Support"
    (support / "Trieur").mkdir(parents=True)
    (support / "Trieur" / "config.toml").write_text("x = 1")
    (support / "Quotidien").mkdir()
    (support / "Quotidien" / "profil.toml").write_text("y = 1")
    monkeypatch.setattr(empreinte, "MAISON", tmp_path)
    monkeypatch.setattr(
        empreinte, "_commande", lambda *a, **k: (0, "PID\tStatus\tLabel\n123\t0\tcom.camille.corvees\n")
    )
    agents_vus = empreinte.launch_agents()
    assert set(agents_vus) == {"com.camille.corvees"}
    assert agents_vus["com.camille.corvees"]["launchd"] == {"charge": True, "tourne": True, "dernier_code": "0"}
    assert set(empreinte.support_applications()) == {"Trieur/config.toml"}


def test_capture_et_comparaison_reelles_du_conteneur(tmp_path: Path) -> None:
    """Le script tel quel, en ligne de commande : capture puis comparaison identique."""
    cible = tmp_path / "etat.json"
    script = RACINE / "integrite" / "empreinte.py"
    env = {**os.environ, "QUOTIDIEN_INTEGRITE_SANS_RAPPELS": "1"}  # pas de fenêtre d'autorisation pendant les tests
    r1 = subprocess.run([sys.executable, str(script), "capturer", str(cible)], capture_output=True, text=True, env=env)
    assert r1.returncode == 0, r1.stderr
    r2 = subprocess.run([sys.executable, str(script), "comparer", str(cible)], capture_output=True, text=True, env=env)
    assert r2.returncode == 0 and "INTÉGRITÉ OK" in r2.stdout, r2.stdout + r2.stderr
    r3 = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert r3.returncode == 2


def test_reference_du_depot_est_versionnee_et_sans_nom_personnel() -> None:
    ref = RACINE / "integrite" / "etat_avant.json"
    donnees = json.loads(ref.read_text(encoding="utf-8"))
    assert "depot_hote" in donnees["projets"]
    assert not any(cle.startswith("quotidien/") for cle in donnees["projets"]["depot_hote"]["fichiers"])
    assert "bouclier/bouclier/cli.py" in donnees["projets"]["depot_hote"]["fichiers"]  # Bouclier est protégé aussi
