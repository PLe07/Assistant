"""D1 — Séquences répétées : les mêmes 3 à 8 actions dans le même ordre, dans une session, sur des jours distincts,
avec au plus une action parasite intercalée.

Croissance de motifs : on ne prolonge que ce qui est déjà assez fréquent, ce qui reste rapide même sur 200 000
événements. On écarte ce qui n'arrive pas plus souvent qu'au hasard (lift), et on ne garde que les séquences
maximales (une sous-séquence qui n'a pas plus de soutien que sa grande sœur disparaît).
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from modules.corvees.detection.flux import Candidat, Flux

Occurrence = tuple[int, int, int, int]  # (session, début, fin, parasites utilisés)


def motifs_frequents(
    flux: Flux,
    longueur_min: int,
    longueur_max: int,
    jours_min: int,
    parasites_max: int,
    sessions: list[int] | None = None,
) -> dict[tuple[int, ...], list[Occurrence]]:
    """Tous les motifs de longueur_min à longueur_max présents au moins jours_min jours distincts."""
    choisies = sessions if sessions is not None else range(len(flux.sessions))
    jours = [s.jour for s in flux.sessions]
    jours_par_token: dict[int, set[str]] = defaultdict(set)
    for si in choisies:
        s = flux.sessions[si]
        for t in s.ids:
            jours_par_token[t].add(s.jour)
    frequents = {t for t, j in jours_par_token.items() if len(j) >= jours_min}

    niveau: dict[tuple[int, ...], list[Occurrence]] = defaultdict(list)
    for si in choisies:
        for i, t in enumerate(flux.sessions[si].ids):
            if t in frequents:
                niveau[(t,)].append((si, i, i, 0))

    resultats: dict[tuple[int, ...], list[Occurrence]] = {}
    tous_ids = [s.ids for s in flux.sessions]
    for longueur in range(2, longueur_max + 1):
        suivant: dict[tuple[int, ...], list[Occurrence]] = defaultdict(list)
        # Un motif n'est fréquent que si sa fin (le motif sans son premier élément) l'est aussi : on ne prolonge
        # un motif que par les éléments qui prolongent déjà sa fin (même résultat, beaucoup moins de calcul).
        prolongements: dict[tuple[int, ...], set[int]] = defaultdict(set)
        if longueur > 2:
            for motif in niveau:
                prolongements[motif[:-1]].add(motif[-1])
        for motif, occs in niveau.items():
            permis = prolongements.get(motif[1:]) if longueur > 2 else frequents
            if not permis:
                continue
            for si, debut, fin, parasites in occs:
                ids = tous_ids[si]
                k = fin + 1
                if k >= len(ids):
                    continue
                t = ids[k]
                if t in permis and t not in motif:
                    suivant[motif + (t,)].append((si, debut, k, parasites))
                if parasites < parasites_max and k + 1 < len(ids):
                    t = ids[k + 1]
                    if t in permis and t not in motif:
                        suivant[motif + (t,)].append((si, debut, k + 1, parasites + 1))
        niveau = {}
        for motif, occs in suivant.items():
            if len(occs) < jours_min or len({jours[o[0]] for o in occs}) < jours_min:
                continue  # trop peu de jours : inutile de dédoublonner
            uniques = {(si, debut): (si, debut, fin, p) for si, debut, fin, p in occs}
            niveau[motif] = list(uniques.values())
        if longueur >= longueur_min:
            resultats.update(niveau)
        if not niveau:
            break
    return resultats


def _jours(flux: Flux, occs: list[Occurrence]) -> int:
    return len({flux.sessions[si].jour for si, *_ in occs})


def maximaux(flux: Flux, motifs: dict[tuple[int, ...], list[Occurrence]], tolerance: float) -> set[tuple[int, ...]]:
    """Les motifs qu'aucun motif plus long n'explique (même soutien, à la tolérance près)."""
    soutien = {m: _jours(flux, o) for m, o in motifs.items()}
    absorbes: set[tuple[int, ...]] = set()
    for grand, jours_grand in soutien.items():
        for i in range(len(grand)):
            petit = grand[:i] + grand[i + 1 :]
            if petit in soutien and jours_grand >= tolerance * soutien[petit]:
                absorbes.add(petit)
    return set(motifs) - absorbes


def _pont_seul(tokens: tuple[str, ...]) -> bool:
    """Une seule copie et les applis qu'elle relie, rien d'autre."""
    ponts = [t for t in tokens if t.startswith("clip:")]
    if len(ponts) != 1:
        return False
    source, _, destination = ponts[0][5:].partition("→")
    return set(tokens) <= {ponts[0], f"app:{source}", f"app:{destination}"}


def esperance(flux: Flux, motif: tuple[int, ...], parasites_max: int) -> float:
    """Combien de fois on verrait ce motif par hasard, si les actions se suivaient sans lien entre elles."""
    total, fenetres = _fenetres(flux, len(motif))
    proba = math.prod(flux.compte[t] / total for t in motif)
    return fenetres * proba * (1 + parasites_max * (len(motif) - 1))


_CACHE: dict[tuple[int, int, int], tuple[int, int]] = {}


def _fenetres(flux: Flux, n: int) -> tuple[int, int]:
    """(nombre total d'actions, nombre de fenêtres de n actions) : calculé une fois par flux et par longueur."""
    cle = (id(flux), len(flux.sessions), n)
    if cle not in _CACHE:
        if len(_CACHE) > 64:
            _CACHE.clear()
        longueurs = [len(s.ids) for s in flux.sessions]
        _CACHE[cle] = (sum(longueurs) or 1, sum(max(0, x - n + 1) for x in longueurs))
    return _CACHE[cle]


def detecter(flux: Flux, reglages: dict[str, Any]) -> list[Candidat]:
    p = reglages["detection"]["sequences"]
    motifs = motifs_frequents(flux, p["longueur_min"], p["longueur_max"], p["jours_min"], p["parasites_max"])
    candidats = []
    for motif in maximaux(flux, motifs, p.get("tolerance_maximale", 0.8)):
        if _pont_seul(tuple(flux.vocab[t] for t in motif)):
            continue  # « appli A → copier → appli B » : c'est au détecteur de ponts (D4) d'en juger
        occs = motifs[motif]
        lift = len(occs) / max(esperance(flux, motif, p["parasites_max"]), 1e-9)
        if lift < p["lift_min"]:
            continue
        sessions = flux.sessions
        debuts = [sessions[si].ts[d] for si, d, _, _ in occs]
        durees = [sessions[si].ts[f] - sessions[si].ts[d] for si, d, f, _ in occs]
        candidats.append(
            Candidat(
                "sequence",
                tuple(flux.vocab[t] for t in motif),
                len(occs),
                _jours(flux, occs),
                debuts,
                durees,
                lift=lift,
            )
        )
    return candidats
