"""Les règles de regles.toml : des indices pondérés par type, et la confiance qui en découle.

score(type) = somme des indices trouvés (une fois chacun) + les points de la catégorie de l'émetteur + ce qui a été
appris de tes corrections. Confiance = (1 − e^(−avance / échelle)) × min(1, score / score_plein), où l'avance est
l'écart avec le deuxième type : deux types proches donnent une confiance basse, même avec beaucoup d'indices.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import tomllib

FICHIER = Path(__file__).resolve().parent.parent / "regles.toml"
TYPES = ["facture_achat", "ticket_caisse", "facture_service", "releve_bancaire", "avis_imposition", "quittance_loyer",
         "bail_contrat", "attestation", "bulletin_paie", "assurance", "billet_transport", "reservation", "sante",
         "identite", "devis", "facture_emise", "garantie_notice", "courrier_admin", "autre"]  # fmt: skip


@dataclass(frozen=True)
class Indice:
    motif: re.Pattern[str]
    poids: float
    haut: bool = False


@dataclass(frozen=True)
class Regles:
    indices: dict[str, tuple[Indice, ...]]
    libelles: dict[str, str]
    categories: dict[str, dict[str, float]]
    lignes_haut: int = 14
    echelle: float = 4.0
    plein: float = 7.0
    minimum: float = 4.0


@dataclass
class Scores:
    points: dict[str, float] = field(default_factory=dict)
    raisons: dict[str, list[str]] = field(default_factory=dict)

    def classement(self) -> list[tuple[str, float]]:
        return sorted(self.points.items(), key=lambda x: -x[1])


class ReglesInvalides(ValueError):
    pass


def lire(chemin: Path = FICHIER) -> Regles:
    try:
        brut = tomllib.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ReglesInvalides(f"{chemin.name} illisible : {e}") from e
    return construire(brut)


def souple(motif: str) -> str:
    """Un espace du motif accepte zéro ou plusieurs espaces : l'OCR en perd (« BULLETINDEPAIE », « N°client »)."""
    return re.sub(r"(?<!\\) ", r"\\s*", motif)


def construire(brut: dict[str, Any]) -> Regles:
    erreurs: list[str] = []
    indices: dict[str, tuple[Indice, ...]] = {}
    libelles: dict[str, str] = {"autre": "Document"}
    for nom, t in brut.get("types", {}).items():
        if nom not in TYPES:
            erreurs.append(f"type inconnu : {nom}")
            continue
        libelles[nom] = str(t.get("libelle", nom))
        liste = []
        for i, x in enumerate(t.get("indices", [])):
            try:
                liste.append(Indice(re.compile(souple(x["re"]), re.M), float(x["poids"]), bool(x.get("haut", False))))
            except (KeyError, TypeError, ValueError, re.error) as e:
                erreurs.append(f"{nom}, indice {i + 1} : {e}")
        indices[nom] = tuple(liste)
    categories = {c: {t: float(p) for t, p in v.items()} for c, v in brut.get("categories", {}).items()}
    for c, v in categories.items():
        erreurs += [f"catégorie {c} : type inconnu {t}" for t in v if t not in TYPES]
    if erreurs:
        raise ReglesInvalides("; ".join(erreurs))
    r = brut.get("reglages", {})
    return Regles(indices, libelles, categories, int(r.get("lignes_haut", 14)), float(r.get("confiance_echelle", 4.0)),
                  float(r.get("score_plein", 7.0)), float(r.get("score_min", 4.0)))  # fmt: skip


@lru_cache(maxsize=2)
def charger(chemin: Path = FICHIER) -> Regles:
    return lire(chemin)


def scorer(lignes: list[str], regles: Regles, categorie: str | None = None,
           bonus: dict[str, float] | None = None) -> Scores:  # fmt: skip
    """« lignes » : le texte normalisé (minuscules, sans accents), lignes non vides."""
    haut = "\n".join(lignes[: regles.lignes_haut])
    tout = "\n".join(lignes)
    s = Scores()
    for nom, indices in regles.indices.items():
        total, raisons = 0.0, []
        for ind in indices:
            m = ind.motif.search(haut) if ind.haut else ind.motif.search(tout)
            poids = ind.poids
            if ind.haut and not m:
                m = ind.motif.search(tout)
                poids /= 2
            if m:
                total += poids
                raisons.append(f"{m.group(0)[:30]} ({poids:+g})")
        s.points[nom], s.raisons[nom] = total, raisons
    for nom, p in regles.categories.get(categorie or "", {}).items():
        s.points[nom] = s.points.get(nom, 0.0) + p
        s.raisons.setdefault(nom, []).append(f"émetteur {categorie} ({p:+g})")
    for nom, p in (bonus or {}).items():
        s.points[nom] = s.points.get(nom, 0.0) + p
        s.raisons.setdefault(nom, []).append(f"appris ({p:+g})")
    return s


def decider(scores: Scores, regles: Regles) -> tuple[str, float]:
    """(type, confiance). Trop peu d'indices : « autre », avec la confiance que ce n'est rien d'autre."""
    rang = scores.classement()
    if not rang:
        return "autre", 0.0
    (premier, s1), s2 = rang[0], max(0.0, rang[1][1]) if len(rang) > 1 else 0.0
    if s1 < regles.minimum:
        return "autre", round(0.5 * (1 - s1 / regles.minimum), 3)
    confiance = (1 - math.exp(-(s1 - s2) / regles.echelle)) * min(1.0, s1 / regles.plein)
    return premier, round(confiance, 3)
