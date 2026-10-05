"""Les opérations partagées par la CLI et le démon : scanner et enregistrer, analyser le dernier scan, mesurer zsh."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from modules.demarrage import config, scan
from modules.demarrage.analyse import Bilan, analyser
from modules.demarrage.db import Base, DisquePlein
from modules.demarrage.mesure import zsh
from modules.demarrage.modele import Inventaire
from modules.demarrage.signatures import CacheSignatures
from modules.demarrage.systeme import Systeme

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
    premier = base.dernier_scan() is None
    cache = CacheSignatures(base.signatures())
    inventaire = scan.scanner(systeme, reglages, cache, apps_de_la_derniere_session(base))
    nouveaux: list[str] = []
    try:
        nouveaux = base.enregistrer_scan(inventaire)
        if cache.modifie:
            base.sauver_signatures(cache.entrees)
    except DisquePlein:
        log.error("[demarrage] disque plein : scan non enregistré")
    return inventaire, nouveaux, premier


def bilan(systeme: Systeme, base: Base, reglages: dict[str, Any], rescanner: bool = False) -> Bilan:
    inventaire = None if rescanner else base.dernier_scan()
    if inventaire is None:
        inventaire, _, _ = scanner(systeme, base, reglages)
    return analyser(inventaire, base, reglages, systeme.maintenant())


def mesurer_zsh(systeme: Systeme, base: Base, reglages: dict[str, Any], forcer: bool = False) -> dict[str, Any] | None:
    """Le temps d'ouverture du Terminal, au plus une fois par semaine (sauf forcer)."""
    historique = base.zsh(1)
    if historique and not forcer and systeme.maintenant() - historique[-1]["ts"] < ZSH_TOUS_LES_S:
        return historique[-1]
    t = zsh.mesurer(systeme, dossier(reglages), reglages["zsh"]["essais"], reglages["zsh"]["seuil_ms"])
    details = {"essais_ms": t.essais_ms, "causes": t.causes, "erreur": t.erreur}
    try:
        base.enregistrer_zsh(systeme.maintenant(), t.mediane_ms, details)
    except DisquePlein:
        log.error("[demarrage] disque plein : temps de zsh non enregistré")
    return {"ts": systeme.maintenant(), "mediane_ms": t.mediane_ms, **details}
