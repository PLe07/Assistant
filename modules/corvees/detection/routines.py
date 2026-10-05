"""D2 — Routines horaires : la même action (ou la même séquence) sur le même créneau (± 45 min) au moins 3 jours
sur 14, ou le même jour de la semaine au moins 3 semaines de suite.

Une appli utilisée toute la journée n'est pas une routine : il faut que l'action soit concentrée sur son créneau
(ou sur son jour de la semaine).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from modules.corvees.detection.flux import NON_ACTIONS, Candidat, Flux
from modules.corvees.normalize import jour_de, jour_semaine, minute_du_jour

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def creneau(instants: list[float], tolerance: int, jours_min: int, concentration_min: float) -> dict[str, Any] | None:
    """Le créneau (heure de Paris) où ces instants se regroupent, ou None. {"minute", "jours", "concentration"}."""
    points = sorted((minute_du_jour(t), jour_de(t)) for t in instants)
    if not points:
        return None
    meilleur: dict[str, Any] | None = None
    debut = 0
    dans_fenetre: Counter[str] = Counter()  # jours présents dans la fenêtre glissante
    for fin in range(len(points)):
        dans_fenetre[points[fin][1]] += 1
        while points[fin][0] - points[debut][0] > 2 * tolerance:
            dans_fenetre[points[debut][1]] -= 1
            if not dans_fenetre[points[debut][1]]:
                del dans_fenetre[points[debut][1]]
            debut += 1
        if meilleur is None or len(dans_fenetre) > meilleur["jours"]:
            milieu = points[(debut + fin) // 2][0]  # les minutes sont triées
            meilleur = {"minute": milieu, "jours": len(dans_fenetre), "dans": fin - debut + 1}
    assert meilleur is not None
    concentration = meilleur["dans"] / len(points)
    if meilleur["jours"] < jours_min or concentration < concentration_min:
        return None
    return {"minute": meilleur["minute"], "jours": meilleur["jours"], "concentration": round(concentration, 2)}


def hebdomadaire(
    instants: list[float], semaines_min: int, concentration_min: float, tolerance_min: int | None = None
) -> dict[str, Any] | None:
    """Le jour de la semaine où ces instants reviennent, au moins N semaines de suite, ou None.
    tolerance_min : exige en plus la même heure (± tolérance) ce jour-là."""
    if tolerance_min is not None and instants:
        meilleur: list[float] = []
        for jour in range(7):
            ce_jour = [t for t in instants if jour_semaine(t) == jour]
            for centre in ce_jour:
                proches = [t for t in ce_jour if abs(minute_du_jour(t) - minute_du_jour(centre)) <= tolerance_min]
                if len(proches) > len(meilleur):
                    meilleur = proches
        reste = len(instants) - len(meilleur)
        instants = meilleur + [t for t in instants if t not in meilleur][:reste]
        if len(meilleur) < semaines_min:
            return None
        trouve = hebdomadaire(meilleur, semaines_min, 0.0)
        if trouve is None or len(meilleur) / max(1, len(instants)) < concentration_min:
            return None
        return trouve
    par_jour: dict[int, set[date]] = defaultdict(set)
    for t in instants:
        d = date.fromisoformat(jour_de(t))
        par_jour[d.weekday()].add(d - timedelta(days=d.weekday()))  # le lundi de sa semaine
    if not par_jour:
        return None
    jour, semaines = max(par_jour.items(), key=lambda x: len(x[1]))
    total = sum(len(s) for s in par_jour.values())
    consecutives, serie, precedente = 0, 0, None
    for lundi in sorted(semaines):
        serie = serie + 1 if precedente is not None and lundi - precedente == timedelta(days=7) else 1
        consecutives = max(consecutives, serie)
        precedente = lundi
    if consecutives < semaines_min or len(semaines) / total < concentration_min:
        return None
    return {"jour_semaine": jour, "semaines": consecutives, "concentration": round(len(semaines) / total, 2)}


def horaire(c: Candidat, flux: Flux, reglages: dict[str, Any]) -> None:
    """Le créneau et le jour de la semaine de CETTE corvée, d'après ses propres occurrences (sur place)."""
    p = reglages["detection"]["routines"]
    limite = flux.fin - p["sur_jours"] * 86400
    jours_fenetre = max(1, len([j for j in flux.jours_actifs if j >= jour_de(limite)]))
    c.details.pop("creneau", None)
    c.details.pop("jour_semaine", None)
    recents = [t for t in c.debuts if t >= limite]
    jours_min = p["jours_min_sequence"] if len(c.tokens) > 1 else p["jours_min"]
    trouve = creneau(recents, p["tolerance_min"], jours_min, p["concentration_min"])
    if trouve:
        c.details["creneau"] = f"{trouve['minute'] // 60:02d}:{trouve['minute'] % 60:02d}"
        c.regularite = max(c.regularite, trouve["jours"] / jours_fenetre)
    # Une suite d'actions le même jour : à la même heure aussi (sinon le hasard en fabrique, parmi des centaines)
    tolerance = p["tolerance_min"] if len(c.tokens) > 1 else None
    hebdo = hebdomadaire(c.debuts, p["semaines_min"], p["concentration_semaine_min"], tolerance)
    if hebdo:
        c.details["jour_semaine"] = JOURS[hebdo["jour_semaine"]]
        c.regularite = max(c.regularite, min(1.0, hebdo["semaines"] / max(1, flux.jours_observes // 7)))


def detecter(flux: Flux, reglages: dict[str, Any], sequences: list[Candidat]) -> list[Candidat]:
    """Les routines d'une seule action ; les séquences déjà trouvées sont complétées de leur créneau, sur place."""
    p = reglages["detection"]["routines"]
    limite = flux.fin - p["sur_jours"] * 86400
    conc_jour, conc_semaine = p["concentration_min"], p["concentration_semaine_min"]
    jours_fenetre = max(1, len([j for j in flux.jours_actifs if j >= jour_de(limite)]))

    # Les séquences : à quel moment reviennent-elles ?
    for c in sequences:
        horaire(c, flux, reglages)

    # Les actions seules
    instants: dict[str, list[float]] = defaultdict(list)
    for e in flux.evenements:
        if e.kind not in NON_ACTIONS:
            instants[e.token].append(e.ts)
    candidats = []
    hebdos: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for token, ts in instants.items():
        # Ce qui n'arrive qu'un jour de la semaine est une routine de ce jour-là, avant d'être un créneau quotidien.
        hebdo = hebdomadaire(ts, p["semaines_min"], conc_semaine)
        if hebdo:
            hebdos[hebdo["jour_semaine"]].append((token, hebdo))
            continue
        recents = [t for t in ts if t >= limite]
        trouve = creneau(recents, p["tolerance_min"], p["jours_min"], conc_jour)
        if trouve:
            dans = [t for t in recents if abs(minute_du_jour(t) - trouve["minute"]) <= p["tolerance_min"]]
            candidats.append(
                Candidat(
                    "routine",
                    (token,),
                    len(dans),
                    trouve["jours"],
                    dans,
                    [0.0] * len(dans),
                    regularite=trouve["jours"] / jours_fenetre,
                    details={"creneau": f"{trouve['minute'] // 60:02d}:{trouve['minute'] % 60:02d}"},
                )
            )
            continue

    # Plusieurs actions du même jour de la semaine, faites ensemble : une seule routine.
    for jour, membres in hebdos.items():
        restants = list(membres)
        while restants:
            token, hebdo = restants.pop(0)
            groupe = [token]
            for autre, _ in list(restants):
                if _ensemble(instants[token], instants[autre]):
                    groupe.append(autre)
                    restants = [r for r in restants if r[0] != autre]
            occurrences = [t for t in instants[groupe[0]] if jour_semaine(t) == jour]
            candidats.append(
                Candidat(
                    "routine",
                    tuple(sorted(groupe, key=lambda g: min(instants[g]))),
                    len(occurrences),
                    len({jour_de(t) for t in occurrences}),
                    occurrences,
                    [0.0] * len(occurrences),
                    regularite=min(1.0, hebdo["semaines"] / max(1, flux.jours_observes // 7)),
                    details={"jour_semaine": JOURS[jour]},
                )
            )
    return candidats


def _ensemble(a: list[float], b: list[float], ecart: float = 1800) -> bool:
    """Deux actions faites ensemble (à moins de 30 min) au moins la moitié des fois."""
    proches = sum(1 for t in a if any(abs(t - u) <= ecart for u in b))
    return proches >= max(1, len(a) // 2)
