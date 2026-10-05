"""Les opérations partagées par la CLI et le démon : scanner et enregistrer, analyser le dernier scan, mesurer zsh."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from modules.demarrage import config
from modules.demarrage.db import Base, DisquePlein
from modules.demarrage.modele import Inventaire
from modules.demarrage.systeme import Systeme

if TYPE_CHECKING:
    from modules.demarrage.analyse import Bilan

# Le scan, l'analyse et zsh sont importés dans les fonctions qui s'en servent : la surveillance en fond, qui fait
# scanner un processus fils (scanner_a_part), ne les charge jamais en mémoire (D-46).
RACINE = Path(__file__).resolve().parents[2]

log = logging.getLogger("demarrage")
ZSH_TOUS_LES_S = 7 * 86400


def dossier(reglages: dict[str, Any]) -> Path:
    d = config.dossier_donnees(reglages)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def ouvrir_base(reglages: dict[str, Any]) -> Base:
    return Base(dossier(reglages) / "demarrage.db", journal=lambda m: log.warning("[demarrage] %s", m))


def apps_de_la_derniere_session(base: Base) -> list[str]:
    sessions = base.sessions(1)
    return list(sessions[-1].get("apps_lancees", [])) if sessions else []


def scanner(systeme: Systeme, base: Base, reglages: dict[str, Any]) -> tuple[Inventaire, list[str], bool]:
    """(inventaire, identifiants vus pour la première fois, premier scan ?). Le cache codesign est gardé en base."""
    from modules.demarrage import scan
    from modules.demarrage.signatures import CacheSignatures

    premier = base.dernier_scan() is None
    cache = CacheSignatures(base.signatures())
    inventaire = scan.scanner(systeme, reglages, cache, apps_de_la_derniere_session(base))
    nouveaux: list[str] = []
    try:
        nouveaux = base.enregistrer_scan(inventaire)
        base.ecrire("dernier_scan", inventaire.ts)
        if cache.modifie:
            base.sauver_signatures(cache.entrees)
    except DisquePlein:
        log.error("[demarrage] disque plein : scan non enregistré")
    return inventaire, nouveaux, premier


def scanner_a_part(
    systeme: Systeme, base: Base, reglages: dict[str, Any], delai_s: float = 600.0
) -> tuple[Inventaire, list[str], bool] | None:
    """Le même scan, dans un processus fils (python -m modules.demarrage.scan_fils) : la mémoire qu'il prend (~15 Mo)
    est rendue au système dès qu'il se termine, au lieu de rester au démon pour toujours. None s'il a échoué."""
    env = {"DEMARRAGE_DOSSIER": str(dossier(reglages)), "PYTHONPATH": str(RACINE)}
    r = systeme.executer([sys.executable, "-m", "modules.demarrage.scan_fils"], delai=delai_s, env=env)
    try:
        resultat = json.loads(r.sortie.strip().splitlines()[-1]) if r.ok else None
    except (IndexError, ValueError):
        resultat = None
    inventaire = base.dernier_scan() if isinstance(resultat, dict) else None
    if resultat is None or inventaire is None:
        log.error("[demarrage] scan à part en échec (code %s) : %s", r.code, (r.erreur or r.sortie).strip()[-300:])
        return None
    return inventaire, list(resultat.get("nouveaux", [])), bool(resultat.get("premier"))


def bilan(systeme: Systeme, base: Base, reglages: dict[str, Any], rescanner: bool = False) -> Bilan:
    from modules.demarrage.analyse import analyser

    inventaire = None if rescanner else base.dernier_scan()
    if inventaire is None:
        inventaire, _, _ = scanner(systeme, base, reglages)
    return analyser(inventaire, base, reglages, systeme.maintenant())


def mesurer_zsh(systeme: Systeme, base: Base, reglages: dict[str, Any], forcer: bool = False) -> dict[str, Any] | None:
    """Le temps d'ouverture du Terminal, au plus une fois par semaine (sauf forcer)."""
    historique = base.zsh(1)
    if historique and not forcer and systeme.maintenant() - historique[-1]["ts"] < ZSH_TOUS_LES_S:
        return historique[-1]
    from modules.demarrage.mesure import zsh

    t = zsh.mesurer(systeme, dossier(reglages), reglages["zsh"]["essais"], reglages["zsh"]["seuil_ms"])
    details = {"essais_ms": t.essais_ms, "causes": t.causes, "erreur": t.erreur}
    try:
        base.enregistrer_zsh(systeme.maintenant(), t.mediane_ms, details)
    except DisquePlein:
        log.error("[demarrage] disque plein : temps de zsh non enregistré")
    return {"ts": systeme.maintenant(), "mediane_ms": t.mediane_ms, **details}
