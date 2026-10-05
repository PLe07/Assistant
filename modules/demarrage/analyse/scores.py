"""Ce que coûte chaque élément (mesures → score d'impact de 0 à 100) et à quel point il sert (utilité).

Score d'impact = 100 × Σ poids × min(1, mesure / référence)
                 + bonus « empêche la veille » + bonus « relancé en boucle », plafonné à 100.
Les poids, références et bonus sont dans config.py (scores). Une mesure absente compte pour 0 : tous les éléments
sont jugés sur les mêmes mesures, le classement reste juste.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from modules.demarrage.db import Base
from modules.demarrage.modele import Fiche

JOUR = 86400.0
MODES_CROISIERE = ("croisiere", "mesure")


@dataclass
class Metriques:
    cpu_session_s: float | None = None  # secondes de processeur dans les 5 min après la connexion (médiane)
    cpu_croisiere_pct: float | None = None  # % d'un cœur, en moyenne, hors ouverture de session
    memoire_mo: float | None = None  # médiane quand il tourne
    energie: float | None = None  # impact énergétique moyen (top)
    veille: float = 0.0  # part des relevés où il empêchait la veille (0 à 1)
    releves: int = 0

    @property
    def mesure(self) -> bool:
        return self.releves > 0


def metriques(base: Base, reglages: dict[str, Any], maintenant: float) -> dict[str, Metriques]:
    """Les mesures de chaque élément sur la fenêtre récente (sessions retenues + croisière)."""
    v = reglages["verdicts"]
    e = reglages["echantillonnage"]
    debut = maintenant - v["fenetre_jours"] * JOUR
    resultats: dict[str, Metriques] = defaultdict(Metriques)

    # Ouverture de session : la somme sur chaque session, puis la médiane des dernières sessions.
    # Seules les sessions vraiment observées (des relevés dans les 5 minutes) comptent : une session « pas observée »
    # (surveillance lancée trop tard) ferait croire à 0 s de processeur pour tout le monde.
    sessions = [s for s in base.sessions(4 * v["sessions_retenues"]) if s.get("connexion") and s.get("releves")]
    sessions = sessions[-v["sessions_retenues"] :]
    par_session: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        fin = s["connexion"] + e["session_minutes"] * 60
        totaux: dict[str, float] = defaultdict(float)
        for _, _, fid, secondes, *_ in base.mesures(s["connexion"], fin, modes=("session",)):
            totaux[fid] += secondes
        for fid, total in totaux.items():
            par_session[fid].append(total)
    for fid, valeurs in par_session.items():
        valeurs += [0.0] * (len(sessions) - len(valeurs))  # absent d'une session : 0 s ce jour-là
        resultats[fid].cpu_session_s = statistics.median(valeurs)

    # Croisière : secondes de processeur / durée couverte, en excluant les trous (veille, Mac éteint).
    releves = base.releves(debut, maintenant, modes=MODES_CROISIERE)
    pas_max = 3 * max(e["croisiere_pas_s"], e["session_pas_s"])
    comptes: set[float] = set()
    duree = 0.0
    for (t0, _), (t1, _) in zip(releves, releves[1:], strict=False):
        if 0 < t1 - t0 <= pas_max:
            comptes.add(t1)
            duree += t1 - t0
    cpu: dict[str, float] = defaultdict(float)
    memoires: dict[str, list[int]] = defaultdict(list)
    energies: dict[str, list[float]] = defaultdict(list)
    veilles: dict[str, int] = defaultdict(int)
    n: dict[str, int] = defaultdict(int)
    for ts, _, fid, cpu_s, rss, puissance, veille in base.mesures(debut, maintenant):
        n[fid] += 1
        if rss > 0:  # la mémoire quand il tourne
            memoires[fid].append(rss)
        veilles[fid] += veille
        if puissance is not None:
            energies[fid].append(puissance)
        if ts in comptes:
            cpu[fid] += cpu_s
    for fid in n:
        m = resultats[fid]
        m.releves = n[fid]
        m.memoire_mo = statistics.median(memoires[fid]) / 1024 if memoires[fid] else 0.0
        m.veille = veilles[fid] / n[fid]
        m.energie = statistics.fmean(energies[fid]) if energies[fid] else None
        if duree > 0:
            m.cpu_croisiere_pct = 100 * cpu[fid] / duree
    return dict(resultats)


def empeche_la_veille(m: Metriques, reglages: dict[str, Any]) -> bool:
    return m.veille >= reglages["verdicts"]["veille_part_min"]


def en_boucle(f: Fiche, reglages: dict[str, Any]) -> bool:
    """Relancé sans cesse par KeepAlive alors qu'il sort en erreur."""
    relances = f.details.get("relances") or 0
    code = f.details.get("dernier_code")
    return f.declencheurs.garder_en_vie and relances >= reglages["scores"]["relances_boucle"] and code not in (0, None)


def impact(f: Fiche, m: Metriques | None, reglages: dict[str, Any]) -> float:
    s = reglages["scores"]
    p, r = s["poids"], s["references"]
    m = m or Metriques()
    total = 0.0
    for poids, valeur, reference in [
        (p["cpu_session"], m.cpu_session_s, r["cpu_session_s"]),
        (p["cpu_croisiere"], m.cpu_croisiere_pct, r["cpu_croisiere_pct"]),
        (p["memoire"], m.memoire_mo, r["memoire_mo"]),
        (p["energie"], m.energie, r["energie"]),
    ]:
        if valeur is not None and reference > 0:
            total += poids * min(1.0, max(0.0, valeur) / reference)
    score = 100 * total
    if empeche_la_veille(m, reglages):
        score += s["bonus_veille"]
    if en_boucle(f, reglages):
        score += s["bonus_boucle"]
    return round(min(100.0, score), 1)


def impact_estime(impact_typique: str, reglages: dict[str, Any]) -> float:
    """Pour un élément pas encore mesuré : l'impact typique de la base de connaissances."""
    return float(reglages["scores"]["impact_estime"].get(impact_typique, 0.0))


def utilite(f: Fiche, maintenant: float, reglages: dict[str, Any], recommandation: str | None) -> tuple[str, str]:
    """(niveau, raison) ; niveau : indispensable, forte, faible, inconnue."""
    if f.est_apple:
        return "indispensable", "fait partie de macOS"
    if f.c_est_moi:
        return "indispensable", "c'est l'Assistant lui-même"
    if f.derniere_utilisation_app is not None:
        jours = (maintenant - f.derniere_utilisation_app) / JOUR
        seuil = reglages["verdicts"]["utilite_jours"]
        if jours > seuil:
            return "faible", f"app pas ouverte depuis {int(jours)} jours"
        return "forte", "app ouverte il y a " + ("moins d'un jour" if jours < 1 else f"{int(jours)} jour(s)")
    if recommandation == "garder":
        return "forte", "utile en permanence (sécurité, pilote, synchronisation…)"
    return "inconnue", "pas d'app associée dont on connaisse l'usage"
