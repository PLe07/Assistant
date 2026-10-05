"""L'analyse complète, locale et sans IA : les cinq détecteurs, le score, la fusion de ce qui décrit la même
corvée, la mémoire de tes décisions, puis le classement."""

from __future__ import annotations

import gc
import time
from typing import Any

from modules.corvees.db import Evenement
from modules.corvees.detection import fichiers, memoire, ponts, routines, scoring, sequences, shell
from modules.corvees.detection.fichiers import squelette
from modules.corvees.detection.flux import Candidat, Flux, preparer
from modules.corvees.normalize import local

# Quand deux détecteurs voient la même corvée, le type le plus parlant l'emporte.
PRIORITE = {"fichiers": 5, "shell": 4, "pont": 3, "routine": 2, "sequence": 1}
JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def _part_simultanee(petit: Candidat, grand: Candidat, marge: float = 900) -> float:
    """La part des fois où « petit » a lieu en même temps que « grand » (à 15 min près)."""
    if not petit.debuts:
        return 0.0
    plages = sorted(
        (d - marge, d + (grand.durees[i] if i < len(grand.durees) else 0) + marge) for i, d in enumerate(grand.debuts)
    )
    ensemble = 0
    for t in petit.debuts:
        if any(a <= t <= b for a, b in plages):
            ensemble += 1
    return ensemble / len(petit.debuts)


def cles_fusion(c: Candidat) -> frozenset[str]:
    """Les étapes de fichiers se comparent par leur squelette (sorte, dossiers, extension) : « Lettre_*_SG » et la
    règle générale « Lettre_* » sont la même étape ; le « en même temps » de meme_corvee évite toute confusion."""
    return frozenset(squelette(t) for t in c.tokens)


def meme_corvee(a: Candidat, b: Candidat, ta: frozenset[str] | None = None, tb: frozenset[str] | None = None) -> bool:
    ta = ta if ta is not None else cles_fusion(a)
    tb = tb if tb is not None else cles_fusion(b)
    commun = ta & tb
    if not commun:
        return False
    if not (min(ta, tb, key=len) <= max(tb, ta, key=len) or len(commun) / len(ta | tb) >= 0.5):
        return False
    # La même corvée si l'une a presque toujours lieu en même temps que l'autre (une variante avec une action de
    # contexte en plus, ou la même vue par deux détecteurs).
    return max(_part_simultanee(a, b), _part_simultanee(b, a)) >= 0.5


def _evaluer(c: Candidat, reglages: dict[str, Any], flux: Flux) -> None:
    """L'horaire propre à ce candidat, le type qui en découle, puis son score."""
    routines.horaire(c, flux, reglages)
    if c.type == "sequence" and (c.details.get("creneau") or c.details.get("jour_semaine")):
        c.type = "routine"  # une suite d'actions qui revient à heure fixe ou le même jour : une routine
    scoring.scorer(c, reglages, flux.jours_observes)


def fusionner(candidats: list[Candidat], reglages: dict[str, Any], flux: Flux) -> list[Candidat]:
    """Ce qui décrit la même corvée ne fait qu'un. Le représentant : la forme qui l'explique le mieux une fois
    chacune évaluée avec son propre horaire (le meilleur score) ; le type : le plus parlant du groupe."""
    # Ce qui ne pourra jamais atteindre le score minimal, même mieux classé ensuite, n'est pas examiné.
    seuil = reglages["scoring"]["score_min"] / 3
    groupes: list[list[Candidat]] = []
    cles: dict[int, frozenset[str]] = {}
    index: dict[str, set[int]] = {}  # étape → groupes qui la contiennent
    for c in sorted((x for x in candidats if x.score >= seuil), key=lambda x: (-x.score, -len(x.tokens))):
        cles[id(c)] = kc = cles_fusion(c)
        voisins = sorted(set().union(*(index.get(t, set()) for t in kc)))
        numero = next(
            (g for g in voisins if any(meme_corvee(c, x, kc, cles[id(x)]) for x in groupes[g])),
            None,
        )
        if numero is None:
            groupes.append([c])
            numero = len(groupes) - 1
        else:
            groupes[numero].append(c)
        for t in kc:
            index.setdefault(t, set()).add(numero)
    resultat = []
    for groupe in groupes:
        for c in groupe:
            _evaluer(c, reglages, flux)
        rep = max(groupe, key=lambda x: (x.score, x.occurrences, len(x.tokens)))
        for x in groupe:
            if x is rep:
                continue
            for cle, valeur in x.details.items():
                if cle not in ("creneau", "jour_semaine"):  # l'horaire est celui du représentant
                    rep.details.setdefault(cle, valeur)
            rep.regularite = max(rep.regularite, x.regularite)
            rep.lift = max(rep.lift, x.lift)
        rep.type = max((x.type for x in groupe), key=lambda t: PRIORITE.get(t, 0))
        if len(groupe) > 1:
            rep.details["vu_par"] = sorted({x.type for x in groupe})
        scoring.scorer(rep, reglages, flux.jours_observes)  # avec son type définitif
        resultat.append(rep)
    return resultat


def _exemples(c: Candidat) -> list[str]:
    derniers = sorted(c.debuts)[-3:]
    return [f"{JOURS_COURTS[local(t).weekday()]} {local(t):%d/%m %H:%M}" for t in derniers]


def analyser(
    evenements: list[Evenement],
    reglages: dict[str, Any],
    decisions: dict[str, dict[str, Any]] | None = None,
    maintenant: float | None = None,
    debut: float | None = None,
    fin: float | None = None,
) -> list[dict[str, Any]]:
    """Les corvées repérées, de la plus rentable à automatiser à la moins rentable (au plus « top »)."""
    # Des millions de petits objets, aucun cycle : le ramasse-miettes de Python, déclenché sans cesse, coûtait
    # 40 % du temps. Il est mis en pause pendant l'analyse (quelques secondes), puis rallumé.
    actif = gc.isenabled()
    gc.disable()
    try:
        return _analyser(evenements, reglages, decisions, maintenant, debut, fin)
    finally:
        if actif:
            gc.enable()


def _analyser(
    evenements: list[Evenement],
    reglages: dict[str, Any],
    decisions: dict[str, dict[str, Any]] | None,
    maintenant: float | None,
    debut: float | None,
    fin: float | None,
) -> list[dict[str, Any]]:
    maintenant = maintenant or time.time()
    flux = preparer(evenements, reglages["sessions"]["inactivite_min"], debut, fin)
    seqs = sequences.detecter(flux, reglages)
    tous = (
        seqs
        + routines.detecter(flux, reglages, seqs)
        + fichiers.detecter(flux, reglages)
        + ponts.detecter(flux, reglages)
        + shell.detecter(flux, reglages)
    )
    for c in tous:
        scoring.scorer(c, reglages, flux.jours_observes)
    s = reglages["scoring"]
    retenus = [c for c in fusionner(tous, reglages, flux) if c.score >= s["score_min"]]
    exportes = []
    for c in sorted(retenus, key=lambda x: -x.score):
        e = c.exporter()
        e["exemples"] = _exemples(c)
        exportes.append(e)
    compte = comptes(flux)
    frequence = lambda tokens: memoire.frequence(compte, flux.jours_observes, tokens)  # noqa: E731
    return memoire.filtrer(exportes, decisions or {}, maintenant, frequence)[: s["top"]]


def comptes(flux: Flux) -> dict[str, int]:
    return {flux.vocab[t]: n for t, n in flux.compte.items()}


def frequence_actuelle(evenements: list[Evenement], reglages: dict[str, Any], tokens: list[str], fin: float) -> float:
    """La fréquence mensuelle des étapes clés de ces tokens dans les événements : à noter avec chaque refus."""
    flux = preparer(evenements, reglages["sessions"]["inactivite_min"], fin=fin)
    return memoire.frequence(comptes(flux), flux.jours_observes, tokens)
