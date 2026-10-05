"""Fouille automatique du code du Nettoyeur : pas de sudo, pas de shell, un seul endroit qui lance des commandes."""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
MODULE = RACINE / "modules" / "demarrage"
CODE = sorted([*MODULE.rglob("*.py"), *MODULE.rglob("*.json"), *MODULE.rglob("*.sh"), RACINE / "demarrage.py"])
# Les seuls fichiers où le mot « sudo » a le droit d'apparaître, et pourquoi.
SUDO_PERMIS = {
    MODULE / "systeme.py": "la liste des commandes refusées",
    MODULE / "actions" / "instructions.py": "le texte à recopier soi-même, jamais lancé",
}


def lire(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_le_code_est_bien_trouve():
    assert MODULE / "systeme.py" in CODE and RACINE / "demarrage.py" in CODE


def test_aucun_sudo_ailleurs():
    fautifs = [
        p.relative_to(RACINE).as_posix() for p in CODE if p not in SUDO_PERMIS and re.search(r"sudo", lire(p), re.I)
    ]
    assert fautifs == []


def test_instructions_ne_lancent_rien():
    p = MODULE / "actions" / "instructions.py"
    if p.exists():  # le fichier arrive en P6 ; d'ici là, rien à vérifier
        texte = lire(p)
        assert not re.search(r"^\s*(import|from)\s+(subprocess|os|modules\.demarrage\.systeme)\b", texte, re.M)
        assert "executer(" not in texte


def test_jamais_de_shell():
    for p in CODE:
        texte = lire(p)
        assert "shell=True" not in texte, p
        assert not re.search(r"\bos\.(system|popen|exec\w*|spawn\w*)\s*\(", texte), p


def test_subprocess_seulement_dans_systeme():
    fautifs = [
        p.name for p in CODE if p.suffix == ".py" and p.name != "systeme.py" and re.search(r"\bsubprocess\b", lire(p))
    ]
    assert fautifs == []
