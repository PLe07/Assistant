"""S10 — bonus shell : ~/.zshenv, ~/.zprofile, ~/.zshrc et ~/.zlogin, lus sans jamais être modifiés.

On y repère ce qui ralentit souvent l'ouverture d'un Terminal. Seuls le nom du fichier, le numéro de ligne et la
cause sont gardés, jamais le texte de la ligne (il peut contenir un secret).
"""

from __future__ import annotations

import re
from typing import Any

from modules.demarrage.systeme import Systeme

FICHIERS = (".zshenv", ".zprofile", ".zshrc", ".zlogin")
TAILLE_MAX = 2_000_000

# motif → (cause, conseil)
SUSPECTS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"nvm\.sh|NVM_DIR"), "nvm (Node.js)",
     "charger nvm à la demande (« lazy load ») ou passer à fnm, bien plus rapide"),
    (re.compile(r"conda initialize|conda\.sh|__conda_setup"), "conda",
     "« conda config --set auto_activate_base false », ou n'initialiser conda qu'à la demande"),
    (re.compile(r"oh-my-zsh\.sh"), "oh-my-zsh", "garder moins de plugins (la liste « plugins=(…) »)"),
    (re.compile(r"(^|[\s;])compinit(?![^\n]*-C)"), "compinit (complétion recalculée à chaque Terminal)",
     "« compinit -C » pour réutiliser le cache"),
    (re.compile(r"pyenv init"), "pyenv", "n'appeler « pyenv init » qu'une fois, dans ~/.zprofile"),
    (re.compile(r"rbenv init"), "rbenv", "n'appeler « rbenv init » qu'une fois, dans ~/.zprofile"),
    (re.compile(r"sdkman-init\.sh"), "SDKMAN", "charger SDKMAN à la demande"),
    (re.compile(r"brew shellenv"), "brew shellenv", "le mettre dans ~/.zprofile plutôt que ~/.zshrc"),
    (re.compile(r"thefuck --alias"), "thefuck", "remplacer l'eval par l'alias déjà calculé"),
    (re.compile(r"(?<!#)\bbrew (update|upgrade|doctor)\b"), "brew update/upgrade à chaque Terminal",
     "lancer ces commandes à la main, pas à l'ouverture"),
]  # fmt: skip


def analyser(contenu: str) -> list[dict[str, Any]]:
    trouves: list[dict[str, Any]] = []
    for numero, ligne in enumerate(contenu.splitlines(), start=1):
        if ligne.lstrip().startswith("#"):
            continue
        for motif, cause, conseil in SUSPECTS:
            if motif.search(ligne):
                trouves.append({"ligne": numero, "cause": cause, "conseil": conseil})
    return trouves


def collecter(systeme: Systeme) -> tuple[dict[str, Any], list[str]]:
    rapport: dict[str, Any] = {"fichiers": {}, "suspects": []}
    erreurs: list[str] = []
    for nom in FICHIERS:
        chemin = systeme.chemin(f"{systeme.maison}/{nom}")
        try:
            if not chemin.is_file():
                continue
            if chemin.stat().st_size > TAILLE_MAX:
                erreurs.append(f"~/{nom} : trop gros pour être lu")
                continue
            contenu = chemin.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            erreurs.append(f"~/{nom} illisible ({e.strerror or e})")
            continue
        rapport["fichiers"][nom] = len(contenu.splitlines())
        rapport["suspects"] += [{"fichier": f"~/{nom}", **s} for s in analyser(contenu)]
    return rapport, erreurs
