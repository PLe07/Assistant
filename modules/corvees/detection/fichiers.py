"""D3 — Règles de fichiers : le même rangement (motif de nom, dossier de départ → d'arrivée), le même renommage ou
la même conversion, au moins 4 fois.

Les étapes subies par un même fichier (téléchargé → renommé → rangé) sont reliées en une chaîne grâce à l'empreinte
de son chemin (« avant » → « fichier ») : la corvée entière devient un seul candidat.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from modules.corvees.detection.flux import Candidat, Flux
from modules.corvees.normalize import jour_de

SORTES = ("fcreate", "fmove", "fren", "fconv", "fdel")
LIEN_MAX_S = 1800  # deux étapes d'une même chaîne : à moins de 30 min


def chaines(flux: Flux) -> list[list[tuple[float, str]]]:
    """Les parcours des fichiers : [[(instant, token), …], …]."""
    parcours: list[list[tuple[float, str]]] = []
    dernier: dict[str, int] = {}  # empreinte du fichier → son parcours
    for e in flux.evenements:
        if e.kind not in SORTES:
            continue
        precedent = e.attrs.get("avant") or e.attrs.get("source")
        i = dernier.get(precedent) if isinstance(precedent, str) else None
        if i is not None and e.ts - parcours[i][-1][0] <= LIEN_MAX_S:
            parcours[i].append((e.ts, e.token))
        else:
            parcours.append([(e.ts, e.token)])
            i = len(parcours) - 1
        if isinstance(e.attrs.get("fichier"), str):
            dernier[e.attrs["fichier"]] = i
    return parcours


_MOTIF = re.compile(r"^(?P<avant>.*\[[^,\]]*, )(?P<motif>[^\]]*)(?P<apres>\].*)$")


def racine(token: str) -> str:
    """« fmove:A→B [pdf, Devoir_Eco_*] » → « fmove:A→B [pdf, Devoir_*] » : la partie fixe du nom, jusqu'au premier
    séparateur (les variantes d'une même règle de rangement se rejoignent). Un renommage garde son motif d'arrivée."""
    m = _MOTIF.match(token)
    if not m:
        return token
    motif = m.group("motif")
    if "→" in motif:  # renommage : « avant→après »
        avant, _, apres = motif.partition("→")
        return f"{m.group('avant')}{_tronquer(avant)}→{_tronquer(apres)}{m.group('apres')}"
    return f"{m.group('avant')}{_tronquer(motif)}{m.group('apres')}"


def squelette(token: str) -> str:
    """Le même token sans aucun nom : « fconv:Documents/Lettres [docx→pdf, *] »."""
    m = _MOTIF.match(token)
    if not m:
        return token
    return f"{m.group('avant')}{'*→*' if '→' in m.group('motif') else '*'}{m.group('apres')}"


def prefixe_commun(motifs: list[str]) -> str:
    """« Lettre_motivation_BNP », « Lettre_motivation_SG » → « Lettre_motivation_* » (coupé à un séparateur)."""
    commun = motifs[0]
    for m in motifs[1:]:
        while not m.startswith(commun):
            commun = commun[:-1]
    coupe = max(commun.rfind(c) for c in "_- ") + 1 if commun else 0
    return (commun[:coupe] + "*") if coupe >= 3 else "*"


def _generaliser(variantes: list[str]) -> str:
    """Le token commun à plusieurs variantes d'une même règle (même sorte, mêmes dossiers, même extension)."""
    m0 = _MOTIF.match(variantes[0])
    if not m0:
        return variantes[0]
    motifs = [_MOTIF.match(v).group("motif") for v in variantes]  # type: ignore[union-attr]
    if all("→" in x for x in motifs):
        avant = prefixe_commun([x.partition("→")[0] for x in motifs])
        apres = prefixe_commun([x.partition("→")[2] for x in motifs])
        return f"{m0.group('avant')}{avant}→{apres}{m0.group('apres')}"
    return f"{m0.group('avant')}{prefixe_commun(motifs)}{m0.group('apres')}"


def _tronquer(motif: str) -> str:
    coupe = re.match(r"^([^_\-\s*]{2,}[_\-\s])", motif)
    return coupe.group(1) + "*" if coupe and "*" in motif else motif


def detecter(flux: Flux, reglages: dict[str, Any]) -> list[Candidat]:
    p = reglages["detection"]["fichiers"]
    groupes: dict[tuple[str, ...], list[list[tuple[float, str]]]] = defaultdict(list)
    exacts: dict[tuple[str, ...], Counter[tuple[str, ...]]] = defaultdict(Counter)
    for c in chaines(flux):
        # L'arrivée du fichier (téléchargement) n'est que le contexte : un parcours où elle a échappé au capteur
        # reste la même corvée.
        coeur = tuple(t for _, t in c if not t.startswith("fcreate:"))
        if coeur:  # un téléchargement seul n'est pas une corvée
            general = tuple(racine(t) for t in coeur)
            groupes[general].append(c)
            exacts[general][coeur] += 1
    # Des variantes trop rares séparément, mais une même règle ensemble (même sorte, mêmes dossiers, même
    # extension) : on les réunit sous leur préfixe commun.
    # (Seulement s'ils partagent vraiment un début de nom : « Lettre_motivation_* » oui, « * » non.)
    par_squelette: dict[tuple[str, ...], list[tuple[str, ...]]] = defaultdict(list)
    for general in groupes:
        par_squelette[tuple(squelette(t) for t in general)].append(general)
    for membres in par_squelette.values():
        if len(membres) < 2 or all(len(groupes[g]) >= p["occurrences_min"] for g in membres):
            continue
        etapes_reunies = tuple(_generaliser([g[i] for g in membres]) for i in range(len(membres[0])))
        if any("*]" == t[-2:] and ", *]" in t or "*→*]" in t for t in etapes_reunies):
            continue  # aucun début de nom commun : ce ne serait pas une règle
        reunies = [c for g in membres for c in groupes.pop(g)]
        groupes[etapes_reunies] = reunies
        exacts[etapes_reunies] = Counter({etapes_reunies: len(reunies)})
    candidats = []
    for general, occs in groupes.items():
        # Une seule forme exacte : on la garde telle quelle ; plusieurs variantes : la forme générale
        variantes = exacts[general]
        etapes = next(iter(variantes)) if len(variantes) == 1 else general
        jours = {jour_de(c[0][0]) for c in occs}
        if len(occs) < p["occurrences_min"] or len(jours) < p.get("jours_min", 2):
            continue
        origines = Counter(t for c in occs for _, t in c if t.startswith("fcreate:"))
        details: dict[str, Any] = {}
        if origines:
            details["origine"] = origines.most_common(1)[0][0]
        candidats.append(
            Candidat(
                "fichiers",
                etapes,
                len(occs),
                len(jours),
                [c[0][0] for c in occs],
                [c[-1][0] - c[0][0] for c in occs],
                details=details,
            )
        )
    return candidats
