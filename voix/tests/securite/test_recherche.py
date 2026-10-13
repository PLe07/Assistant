"""Recherche automatisée (§9.3) dans tout le code de `voix/` : aucun `shell=True`, aucun `os.system`/`os.popen`/
`eval`/`exec` ; un seul endroit lance des programmes (l'exécuteur, plus `defaults export` en lecture pour le
raccourci), toujours avec une liste d'arguments ; aucune action de suppression, d'envoi ou d'extinction dans la liste
blanche ni dans les ordres vers l'app."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from voix.actions.executeur import MODULES, SYSTEME
from voix.actions.pont import ORDRES
from voix.nlu.intentions import INTENTIONS

RACINE = Path(__file__).resolve().parents[2] / "voix"
FICHIERS = sorted(RACINE.rglob("*.py"))
LANCEURS_PERMIS = {"actions/executeur.py", "cli.py"}
APPELS_INTERDITS = {
    ("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "execvp"), ("os", "execl"), ("os", "execlp"),
    ("os", "spawnv"), ("os", "spawnl"), ("os", "posix_spawn"), ("subprocess", "getoutput"),
    ("subprocess", "getstatusoutput"), ("pty", "spawn"), ("commands", "getoutput"),
}  # fmt: skip
MOTS_DANGEREUX = re.compile(
    r"\b(?:rm\s+-|rmdir|srm|sudo|shutdown|reboot|halt\b|diskutil|launchctl|killall|kill\s+-9|empty trash|"
    r"vider la corbeille|do shell script|curl|wget|nc\s+-|chmod\s+777|osascript\s+-e)",
    re.IGNORECASE,
)


def _arbres() -> list[tuple[str, ast.AST]]:
    return [(str(f.relative_to(RACINE)), ast.parse(f.read_text(encoding="utf-8"))) for f in FICHIERS]


def test_le_code_est_bien_trouve() -> None:
    assert len(FICHIERS) > 25 and any(f.name == "executeur.py" for f in FICHIERS)


def test_jamais_de_shell_ni_d_evaluation() -> None:
    fautes = []
    for nom, arbre in _arbres():
        for n in ast.walk(arbre):
            if isinstance(n, ast.keyword) and n.arg == "shell":
                fautes.append(f"{nom}:{n.value.lineno} shell=")
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in ("eval", "exec", "__import__"):
                    fautes.append(f"{nom}:{n.lineno} {f.id}()")
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    if (f.value.id, f.attr) in APPELS_INTERDITS:
                        fautes.append(f"{nom}:{n.lineno} {f.value.id}.{f.attr}()")
    assert fautes == []


def test_un_seul_endroit_lance_des_programmes_avec_une_liste() -> None:
    lanceurs = []
    for nom, arbre in _arbres():
        for n in ast.walk(arbre):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "subprocess"
                    and n.func.attr in ("run", "Popen", "call", "check_call", "check_output")):  # fmt: skip
                lanceurs.append(nom)
                assert n.args and isinstance(n.args[0], ast.List), f"{nom}:{n.lineno} : arguments en liste"
    assert set(lanceurs) <= LANCEURS_PERMIS and "actions/executeur.py" in lanceurs


def test_aucun_programme_ni_texte_dangereux() -> None:
    assert set(SYSTEME) == {"open", "osascript", "networksetup", "pmset", "shortcuts", "mdfind", "defaults", "say"}
    assert set(MODULES) == {"tableau", "ambiance", "quotidien", "bouclier"}
    for nom, arbre in _arbres():
        if nom.startswith("nlu/"):
            continue  # la compréhension nomme « éteins », « shutdown »… pour les reconnaître et les refuser
        for n in ast.walk(arbre):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.col_offset >= 0:
                if isinstance(getattr(n, "parent", None), ast.Expr):
                    continue
                m = MOTS_DANGEREUX.search(n.value)
                assert m is None or _documentation(arbre, n), f"{nom}:{n.lineno} « {m.group(0) if m else ''} »"


def _documentation(arbre: ast.AST, constante: ast.Constant) -> bool:
    """Les docstrings peuvent nommer ce qui est interdit (pour dire que c'est interdit)."""
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            corps = getattr(n, "body", [])
            if corps and isinstance(corps[0], ast.Expr) and corps[0].value is constante:
                return True
    return False


def test_ni_suppression_ni_envoi_ni_extinction() -> None:
    interdits = re.compile(r"suppr|effac|envoi|envoy|pay|achat|eteindre_mac|extinction|redemarr|vider|corbeille")
    assert [i for i in INTENTIONS if interdits.search(i)] == []
    assert [o for o in ORDRES if interdits.search(o) or "script" in o or "shell" in o] == []
    sensibles = {i for i, d in INTENTIONS.items() if d.sensible}
    assert sensibles == {"app.fermer_tout", "app.fermer_tout_sauf", "systeme.veille", "systeme.wifi_desactiver"}
