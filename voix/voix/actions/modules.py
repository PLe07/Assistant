"""Tes modules (§4.6), s'ils sont installés : uniquement par leur **commande publique**, avec un délai maximum.

- Découverte : `which` (dans `~/.local/bin`, Homebrew, ton PATH) et, pour les modes d'Ambiance, son README lu en
  **lecture seule** à côté de la commande. Jamais d'accès à leurs fichiers de données, jamais d'arrêt ni de relance.
- Commandes : `tableau ouvrir`, `tableau etat`, `ambiance mode <mode>`, `ambiance mood`, `quotidien menu`,
  `bouclier verifier --presse-papiers`. Le mode est vérifié contre ceux annoncés par le README.
"""

from __future__ import annotations

import re
from pathlib import Path

from voix.actions.base import Outils, Reponse, erreur, fait, info
from voix.actions.executeur import MODULES, Executeur

COMMANDES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "module.tableau_ouvrir": ("tableau", ("ouvrir",), "Tableau de bord ouvert"),
    "module.tableau_etat": ("tableau", ("etat",), "État des modules"),
    "module.ambiance_mood": ("ambiance", ("mood",), "Nouvelle ambiance"),
    "module.quotidien_menu": ("quotidien", ("menu",), "Menu de la semaine"),
    "module.bouclier_presse_papiers": ("bouclier", ("verifier", "--presse-papiers"), "Presse-papiers vérifié"),
}
MODE = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
SORTIE_BULLE = 300


def decouvrir(executeur: Executeur) -> dict[str, str]:
    """Les modules installés : nom → chemin de leur commande."""
    trouves: dict[str, str] = {}
    for nom in MODULES:
        chemin = executeur.trouver(nom)
        if chemin is not None:
            trouves[nom] = chemin
    return trouves


def modes_ambiance(commande: str) -> dict[str, str]:
    """Les modes qu'annonce le README d'Ambiance (« ambiance mode focus ») : lu en lecture seule, à côté de la
    commande (le lien suivi jusqu'au projet). Rien trouvé : {} (et les modes connus par défaut s'appliquent)."""
    try:
        reel = Path(commande).resolve()
    except OSError:
        return {}
    for d in list(reel.parents)[:4]:
        readme = d / "README.md"
        try:
            if readme.is_file() and readme.stat().st_size < 1_000_000:
                texte = readme.read_text(encoding="utf-8", errors="replace")
                modes = sorted(set(re.findall(r"ambiance mode ([a-z][a-z0-9_-]{0,30})", texte)))
                if modes:
                    return {m: m for m in modes}
        except OSError:
            continue
    return {}


def _resume(sortie: str) -> str:
    lignes = [ligne.strip() for ligne in sortie.splitlines() if ligne.strip()]
    texte = " ".join(lignes[:3])
    return texte[:SORTIE_BULLE] + ("…" if len(texte) > SORTIE_BULLE else "")


def executer(o: Outils, intention: str, mode: str | None = None) -> Reponse:
    arguments: tuple[str, ...]
    if intention == "module.ambiance_mode":
        programme, arguments, texte = "ambiance", ("mode", mode or ""), f"Mode {mode}"
        if mode is None or not MODE.match(mode) or (o.modes_ambiance and mode not in o.modes_ambiance.values()):
            return erreur(f"Ambiance ne connaît pas le mode « {mode} ».", intention)
    else:
        programme, arguments, texte = COMMANDES[intention]
    if programme not in o.modules:
        return info(f"{MODULES[programme]} n'est pas installé.", intention)
    delai = float(o.reglages["modules"]["delai_s"])
    r = o.lancer(programme, *arguments, delai_s=delai)
    if r.delai_depasse:
        return erreur(f"{MODULES[programme]} ne répond pas (plus de {delai:.0f} s).", intention)
    if not r.ok:
        return erreur(f"{MODULES[programme]} a signalé un problème : {_resume(r.erreur or r.sortie)}", intention)
    resume = _resume(r.sortie)
    if intention in ("module.tableau_etat", "module.quotidien_menu", "module.bouclier_presse_papiers") and resume:
        return info(resume, intention)
    return fait(texte, intention)
