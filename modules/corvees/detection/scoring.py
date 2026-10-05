"""Le score d'une corvée : log(1 + occurrences) × √jours distincts × minutes perdues par mois × automatisabilité.

Les minutes perdues : la durée d'une occurrence (mesurée quand c'est possible, plafonnée) × sa fréquence
mensuelle extrapolée. Ouvrir une appli ou un site, seul, est déjà instantané : son facteur est réduit.
"""

from __future__ import annotations

import math
from typing import Any

from modules.corvees.detection.flux import Candidat, mediane
from modules.corvees.normalize import sous_commandes

NAVIGATION = ("app", "url")


def sorte(token: str) -> str:
    return token.split(":", 1)[0]


def duree(c: Candidat, reglages: dict[str, Any]) -> float:
    """Secondes perdues à chaque fois : le temps habituel de chaque étape faite à la main, ou la durée mesurée si elle
    est plus longue, sans dépasser trois fois ce temps (entre deux étapes, on lit, on réfléchit : ce n'est pas la
    corvée)."""
    s = reglages["scoring"]
    estimee = 0.0
    for t in c.tokens:
        par_etape = float(s["secondes_par_etape"].get(sorte(t), 5))
        estimee += par_etape * (len(sous_commandes(t[4:])) if sorte(t) == "cmd" else 1)
    mesuree = mediane([d for d in c.durees if d > 0])
    if mesuree > 0:  # mesurée, mais bornée : entre le temps habituel des étapes et trois fois ce temps
        estimee = min(max(mesuree, estimee), 3 * estimee)
    return min(estimee, float(s["duree_max_s"]))


def scorer(c: Candidat, reglages: dict[str, Any], jours_observes: int) -> Candidat:
    s = reglages["scoring"]
    c.duree_s = duree(c, reglages)
    c.frequence_mois = c.occurrences / max(jours_observes, 7) * 30
    c.minutes_mois = c.duree_s * c.frequence_mois / 60
    facteur = float(s["automatisabilite"].get(c.type, 0.5))
    # Dans une suite d'actions, une copie que D4 n'a pas retenue comme pont n'est qu'un geste de navigation.
    navigation = NAVIGATION if c.type == "pont" else (*NAVIGATION, "clip")
    if all(sorte(t) in navigation for t in c.tokens):
        if len(c.tokens) == 1:  # ouvrir une appli ou un site, seul : déjà instantané
            facteur *= s["facteur_action_instantanee"]
        elif not (c.details.get("creneau") or c.details.get("jour_semaine")):
            # passer d'appli en appli dans un ordre qui revient sans horaire : de la navigation, pas une corvée
            facteur *= s["facteur_navigation_irreguliere"]
    c.score = math.log1p(c.occurrences) * math.sqrt(c.jours) * c.minutes_mois * facteur
    return c
