"""Les interdits, vérifiés dans le code du Trieur : pas de sudo, pas de réseau (Claude passe par core.cerveau),
pas de shell, pas d'effacement récursif hors de ses propres dossiers de travail."""

from __future__ import annotations

import re
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3] / "modules" / "trieur"
INTERDITS = {
    "sudo": re.compile(r"\bsudo\b"),
    "réseau": re.compile(r"import (?:urllib|requests|httpx|socket|http\.client)|from (?:urllib|requests|httpx|socket)"),
    "shell": re.compile(r"shell\s*=\s*True|os\.system\(|os\.popen\("),
    "rm -rf": re.compile(r"rm -rf|rm -fr"),
}
# shutil.rmtree n'est permis que sur ce que le Trieur a créé lui-même.
RMTREE_PERMIS = {"traitement.py": "travail", "cli.py": "travail", "entrees/finder.py": "paquet"}


def test_aucun_interdit_dans_le_code():
    trouves = []
    for fichier in MODULE.rglob("*.py"):
        texte = fichier.read_text(encoding="utf-8")
        for nom, motif in INTERDITS.items():
            trouves += [f"{fichier.relative_to(MODULE)} : {nom}" for _ in motif.finditer(texte)]
        for ligne in texte.splitlines():
            if "shutil.rmtree(" in ligne:
                relatif = str(fichier.relative_to(MODULE))
                assert relatif in RMTREE_PERMIS and RMTREE_PERMIS[relatif] in ligne, f"{relatif} : {ligne.strip()}"
    assert trouves == []
