"""Bonus : le temps d'ouverture d'un Terminal. On chronomètre `zsh -i -c exit` 5 fois et on garde la médiane.

Au-dessus du seuil (300 ms), on cherche la cause avec zprof. Pour ça, on copie tes fichiers zsh dans un dossier
temporaire à nous, on y ajoute `zmodload zsh/zprof`, et on lance zsh avec ZDOTDIR pointé sur cette copie. Tes
fichiers ne sont jamais modifiés, et la copie est effacée juste après.
"""

from __future__ import annotations

import re
import shutil
import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from modules.demarrage.systeme import Systeme

FICHIERS = (".zshenv", ".zprofile", ".zshrc", ".zlogin")
_LIGNE_ZPROF = re.compile(
    r"^\s*\d+\)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)%\s+(\S+)\s*$"
)
# nom de fonction zprof → cause lisible
CAUSES = [
    (re.compile(r"^(nvm|_nvm)"), "nvm (Node.js)"),
    (re.compile(r"conda"), "conda"),
    (re.compile(r"^(compinit|compdump|compaudit|_comp)"), "compinit (complétion)"),
    (re.compile(r"^(_omz|omz|_zsh_autosuggest|_zsh_highlight)"), "oh-my-zsh et ses plugins"),
    (re.compile(r"pyenv"), "pyenv"),
    (re.compile(r"rbenv"), "rbenv"),
    (re.compile(r"sdk"), "SDKMAN"),
]


@dataclass
class TempsZsh:
    mediane_ms: float | None
    essais_ms: list[float] = field(default_factory=list)
    causes: list[dict[str, float | str]] = field(default_factory=list)  # {"fonction", "cause", "ms", "part"}
    erreur: str = ""


def cause_de(fonction: str) -> str:
    return next((nom for motif, nom in CAUSES if motif.search(fonction)), fonction)


def analyser_zprof(texte: str, n: int = 5) -> list[dict[str, float | str]]:
    """Les fonctions qui coûtent le plus, en temps propre (« self »)."""
    lignes = []
    for ligne in texte.splitlines():
        m = _LIGNE_ZPROF.match(ligne)
        if m:
            fonction = m.group(8)
            lignes.append({"fonction": fonction, "cause": cause_de(fonction), "ms": float(m.group(5)),
                           "part": float(m.group(7))})  # fmt: skip
    return sorted(lignes, key=lambda x: float(x["ms"]), reverse=True)[:n]


def chronometrer(systeme: Systeme, essais: int = 5, delai: float = 20.0) -> TempsZsh:
    if not systeme.a_la_commande("zsh"):
        return TempsZsh(None, erreur="zsh absent")
    durees: list[float] = []
    for _ in range(essais):
        r = systeme.executer(["zsh", "-i", "-c", "exit"], delai=delai)
        if r.code == 124:
            return TempsZsh(None, durees, erreur=f"zsh ne s'ouvre pas en {delai:.0f} s")
        if not r.ok:
            return TempsZsh(None, durees, erreur=f"zsh a échoué (code {r.code}) : {r.erreur.strip()[:100]}")
        durees.append(r.duree_s * 1000)
    return TempsZsh(round(statistics.median(durees), 1), [round(d, 1) for d in durees])


def profiler(systeme: Systeme, dossier_temp: Path, delai: float = 20.0) -> list[dict[str, float | str]]:
    """zprof dans une copie isolée de tes fichiers zsh (ZDOTDIR) ; la copie est effacée ensuite."""
    dossier_temp.mkdir(parents=True, exist_ok=True)
    copie = Path(tempfile.mkdtemp(prefix="zprof-", dir=dossier_temp))
    try:
        for nom in FICHIERS:
            source = systeme.chemin(f"{systeme.maison}/{nom}")
            if source.is_file():
                shutil.copyfile(source, copie / nom)
        zshenv = copie / ".zshenv"
        ancien = zshenv.read_text(encoding="utf-8", errors="replace") if zshenv.exists() else ""
        zshenv.write_text("zmodload zsh/zprof\n" + ancien, encoding="utf-8")
        zshrc = copie / ".zshrc"
        ancien = zshrc.read_text(encoding="utf-8", errors="replace") if zshrc.exists() else ""
        zshrc.write_text(ancien + "\nzprof\n", encoding="utf-8")
        r = systeme.executer(["zsh", "-i", "-c", "exit"], delai=delai, env={"ZDOTDIR": str(copie)})
        return analyser_zprof(r.sortie) if r.ok or r.sortie else []
    finally:
        shutil.rmtree(copie, ignore_errors=True)


def mesurer(systeme: Systeme, dossier_temp: Path, essais: int = 5, seuil_ms: float = 300.0) -> TempsZsh:
    t = chronometrer(systeme, essais)
    if t.mediane_ms is not None and t.mediane_ms > seuil_ms:
        t.causes = profiler(systeme, dossier_temp)
    return t
