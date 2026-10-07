"""Les crédits Claude : coût estimé par module, plafond, projection à la fin du mois (§4.3).

- **Estimé** : lu dans les bases (copies) des modules qui tiennent leurs comptes (Corvées, Trieur, Bouclier,
  Quotidien, Ambiance si l'option est active). L'assistant, lui, passe par ton abonnement Claude Code : son coût est
  un **équivalent API** (jetons × tarif public), pour comparer, pas une facture.
- **Réel** (facultatif, éteint par défaut) : le rapport de coûts officiel de l'organisation, avec une clé Admin rangée
  dans le trousseau (voir `admin_anthropic.py`).

Tarifs publics par million de jetons (entrée, sortie), relevés le 2026-10-06 dans la documentation d'Anthropic. Les
alias de Claude Code (« haiku », « sonnet », « opus ») désignent la génération actuelle.
"""

from __future__ import annotations

import calendar
import time
from dataclasses import dataclass
from typing import Any

TARIFS_USD_PAR_MILLION: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}
ALIAS = {
    "haiku": "claude-haiku-5-5",
    "rapide": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "fort": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
    "fable": "claude-fable-5-1",
}


def tarif(modele: str | None) -> tuple[float, float] | None:
    """Le tarif d'un modèle (identifiant complet, préfixe connu, ou alias) ; None si inconnu."""
    if not modele:
        return None
    m = modele.strip().lower()
    m = ALIAS.get(m, m)
    if m in TARIFS_USD_PAR_MILLION:
        return TARIFS_USD_PAR_MILLION[m]
    for connu in sorted(TARIFS_USD_PAR_MILLION, key=len, reverse=True):
        if m.startswith(connu):
            return TARIFS_USD_PAR_MILLION[connu]
    for nom, complet in ALIAS.items():
        if nom in m:
            return TARIFS_USD_PAR_MILLION[complet]
    return None


def estimer(jetons: dict[str, tuple[int, int]]) -> tuple[float | None, list[str]]:
    """Coût estimé (équivalent API) de jetons par modèle ; et les modèles au tarif inconnu."""
    total = 0.0
    inconnus: list[str] = []
    for modele, (entree, sortie) in jetons.items():
        t = tarif(modele)
        if t is None:
            inconnus.append(modele)
            continue
        total += entree / 1e6 * t[0] + sortie / 1e6 * t[1]
    if inconnus and total == 0 and len(inconnus) == len(jetons):
        return None, inconnus
    return total, inconnus


@dataclass
class Projection:
    mois_usd: float
    projection_usd: float | None  # None : trop tôt dans le mois pour projeter
    plafond_usd: float | None
    pct: float | None  # du plafond, à date


def projeter(mois_usd: float, plafond_usd: float | None, maintenant: float, jours_min: float = 3.0) -> Projection:
    """Projection linéaire à la fin du mois : dépensé / jours écoulés × jours du mois (au moins 3 jours écoulés)."""
    t = time.localtime(maintenant)
    jours_du_mois = calendar.monthrange(t.tm_year, t.tm_mon)[1]
    debut = time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1))
    ecoules = max(0.0, (maintenant - debut) / 86400)
    projection = mois_usd / ecoules * jours_du_mois if ecoules >= jours_min else None
    pct = mois_usd / plafond_usd * 100 if plafond_usd else None
    return Projection(mois_usd, projection, plafond_usd, pct)


def noter(base: Any, etats: list[Any], maintenant: float) -> None:
    """Le coût du mois de chaque module, gardé pour la tendance et le rapport de la semaine."""
    mois = time.strftime("%Y-%m", time.localtime(maintenant))
    lignes = [
        (e.id, mois, float(e.credits_mois), e.plafond_usd, maintenant)
        for e in etats
        if e.credits_mois is not None
    ]
    if lignes:
        base.plusieurs(
            "INSERT INTO credits (module, mois, cout_usd, plafond_usd, maj) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(module, mois) DO UPDATE SET cout_usd = excluded.cout_usd, plafond_usd = excluded.plafond_usd, "
            "maj = excluded.maj",
            lignes,
        )


def mois_precedent(maintenant: float) -> str:
    t = time.localtime(maintenant)
    annee, mois = (t.tm_year, t.tm_mon - 1) if t.tm_mon > 1 else (t.tm_year - 1, 12)
    return f"{annee:04d}-{mois:02d}"


def synthese(base: Any, etats: list[Any], maintenant: float, reel_usd: float | None = None) -> dict[str, Any]:
    """La vue « Crédits » : total du mois, répartition, projection, réel si disponible, tendance."""
    modules = []
    total_api = total_estime = 0.0
    plafonds = 0.0
    for e in etats:
        source = (e.technique or {}).get("credits_source", "base")
        if e.credits_mois is None and e.plafond_usd is None:
            continue
        p = projeter(e.credits_mois or 0.0, e.plafond_usd, maintenant)
        modules.append({
            "id": e.id, "nom": e.nom, "emoji": e.emoji, "mois_usd": e.credits_mois, "plafond_usd": e.plafond_usd,
            "pct": p.pct, "projection_usd": p.projection_usd, "source": source,
            "detail": (e.technique or {}).get("credits_detail", ""),
        })  # fmt: skip
        if source == "estimation":
            total_estime += e.credits_mois or 0.0
        else:
            total_api += e.credits_mois or 0.0
            plafonds += e.plafond_usd or 0.0
    modules.sort(key=lambda m: -(m["mois_usd"] or 0))
    total = projeter(total_api, plafonds or None, maintenant)
    ids = [m["id"] for m in modules if m["source"] != "estimation"]
    precedent = None
    if ids:
        marques = ",".join("?" * len(ids))
        precedent = base.valeur(
            f"SELECT SUM(cout_usd) FROM credits WHERE mois = ? AND module IN ({marques})",  # noqa: S608 - des « ? »
            (mois_precedent(maintenant), *ids),
        )
    return {
        "mois": time.strftime("%Y-%m", time.localtime(maintenant)),
        "total_usd": total_api,
        "plafonds_usd": plafonds or None,
        "projection_usd": total.projection_usd,
        "abonnement_equivalent_usd": total_estime,
        "reel_usd": reel_usd,
        "mois_precedent_usd": float(precedent) if precedent is not None else None,
        "modules": modules,
    }
