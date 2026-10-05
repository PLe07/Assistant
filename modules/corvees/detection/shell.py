"""D5 — Commandes shell : la même suite d'au moins 2 commandes, au moins 4 fois.

Deux formes : une ligne qui enchaîne plusieurs commandes (« cd x && git pull && python main.py »), ou plusieurs
lignes tapées l'une après l'autre (à moins de 5 minutes d'écart).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from modules.corvees.detection.flux import Candidat, Flux, Session
from modules.corvees.detection.sequences import esperance, maximaux, motifs_frequents
from modules.corvees.normalize import jour_de, sous_commandes


def detecter(flux: Flux, reglages: dict[str, Any]) -> list[Candidat]:
    p = reglages["detection"]["shell"]
    candidats = []

    # 1. Les lignes qui enchaînent déjà plusieurs commandes
    lignes: dict[str, list[float]] = defaultdict(list)
    for e in flux.evenements:
        if e.kind == "cmd" and len(sous_commandes(e.token[4:])) >= p["longueur_min"]:
            lignes[e.token].append(e.ts)
    for token, ts in lignes.items():
        jours = {jour_de(t) for t in ts}
        if len(ts) >= p["occurrences_min"] and len(jours) >= p["jours_min"]:
            candidats.append(Candidat("shell", (token,), len(ts), len(jours), ts, [0.0] * len(ts)))

    # 2. Les suites de lignes : un flux fait des seules commandes, coupé après 5 minutes sans commande
    index = {t: i for i, t in enumerate(flux.vocab)}
    commandes = Flux([], flux.vocab, [], flux.debut, flux.fin, flux.jours_actifs, Counter())
    for e in flux.evenements:
        t = index.get(e.token) if e.kind == "cmd" else None
        if t is None:
            continue
        derniere = commandes.sessions[-1] if commandes.sessions else None
        jour = jour_de(e.ts)
        if derniere is None or e.ts - derniere.ts[-1] > p["ecart_max_s"] or jour != derniere.jour:
            derniere = Session([], [], jour)
            commandes.sessions.append(derniere)
        if not derniere.ids or derniere.ids[-1] != t:
            derniere.ids.append(t)
            derniere.ts.append(e.ts)
            commandes.compte[t] += 1
    motifs = motifs_frequents(commandes, p["longueur_min"], p["longueur_max"], p["jours_min"], 0)
    for motif in maximaux(commandes, motifs, 0.8):
        occs = motifs[motif]
        if len(occs) < p["occurrences_min"]:
            continue
        lift = len(occs) / max(esperance(commandes, motif, 0), 1e-9)
        if lift < p.get("lift_min", 3.0):
            continue
        debuts = [commandes.sessions[si].ts[d] for si, d, _, _ in occs]
        durees = [commandes.sessions[si].ts[f] - commandes.sessions[si].ts[d] for si, d, f, _ in occs]
        jours = {commandes.sessions[si].jour for si, *_ in occs}
        candidats.append(
            Candidat("shell", tuple(flux.vocab[t] for t in motif), len(occs), len(jours), debuts, durees, lift=lift)
        )
    return candidats
