"""L'analyse : pour chaque fiche du scan, ses mesures, son score d'impact, son utilité, ce que la base de
connaissances en dit, son verdict et ses mentions ; puis le classement et les gains."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from modules.demarrage.analyse import connaissances, gains, scores, verdicts
from modules.demarrage.analyse.connaissances import Connaissance
from modules.demarrage.analyse.scores import Metriques
from modules.demarrage.analyse.verdicts import Contexte, Verdict
from modules.demarrage.db import Base
from modules.demarrage.modele import SOURCES, Fiche, Inventaire


@dataclass
class Element:
    fiche: Fiche
    metriques: Metriques
    impact: float
    impact_estime: bool
    utilite: str
    raison_utilite: str
    connaissance: Connaissance | None
    verdict: Verdict
    drapeaux: list[str] = field(default_factory=list)
    nom: str = ""
    role: str = ""
    premiere_vue: float | None = None

    @property
    def editeur(self) -> str | None:
        f = self.fiche
        if f.est_apple:
            return "Apple"
        if f.editeur:
            return f.editeur
        if f.details.get("editeur_btm"):
            return str(f.details["editeur_btm"])
        if self.connaissance and self.connaissance.editeur and self.verdict.code != "inconnu":
            return self.connaissance.editeur
        return f"équipe {f.equipe}" if f.equipe else None


@dataclass
class Bilan:
    ts: float
    elements: list[Element]  # les éléments non Apple par impact décroissant, puis Apple
    gains: gains.Gains
    inventaire: Inventaire

    @property
    def classement(self) -> list[Element]:
        return [e for e in self.elements if e.verdict.code != "apple"]

    @property
    def apple(self) -> list[Element]:
        return [e for e in self.elements if e.verdict.code == "apple"]

    def actifs(self) -> list[Element]:
        """Ce qui se lance tout seul (hors macOS) : tout sauf ce qui est déjà inactif."""
        return [e for e in self.classement if e.fiche.actif is not False]

    def couteux(self, reglages: dict[str, Any]) -> list[Element]:
        seuil = reglages["verdicts"]["impact_significatif"]
        return [e for e in self.classement if e.impact >= seuil and not e.impact_estime]

    def element(self, id_: str) -> Element | None:
        return next((e for e in self.elements if e.fiche.id == id_), None)


def nom_lisible(f: Fiche, c: Connaissance | None) -> str:
    if c is not None and c.categorie not in ("apple",):
        return c.nom
    if f.nom:
        return f.nom
    if f.app_parente and f.source in ("ouverture", "ouverture_app"):
        return PurePosixPath(f.app_parente).stem
    return f.label


def distinguer_les_homonymes(elements: list[Element]) -> None:
    """Quatre « Mise à jour de Zoom » ou deux « L'Assistant » côte à côte : on ajoute de quoi les distinguer (le label,
    ou la source si le label est le même), D-44. Les éléments d'Apple gardent leur nom."""
    groupes: dict[str, list[Element]] = {}
    for e in elements:
        if e.verdict.code != "apple":
            groupes.setdefault(e.nom.casefold(), []).append(e)
    for groupe in groupes.values():
        if len(groupe) < 2:
            continue
        labels = [e.fiche.label for e in groupe]
        for e in groupe:
            precision = e.fiche.label
            if labels.count(e.fiche.label) > 1 or precision.casefold() == e.nom.casefold():
                precision = SOURCES.get(e.fiche.source, ("", e.fiche.source))[1]
            e.nom = f"{e.nom} · {precision}"


def analyser(inventaire: Inventaire, base: Base, reglages: dict[str, Any], maintenant: float) -> Bilan:
    mesures = scores.metriques(base, reglages, maintenant)
    premieres = base.premieres_vues()
    elements: list[Element] = []
    for f in inventaire.fiches:
        c = connaissances.trouver(f)
        if c is not None and c.categorie == "assistant" and not f.c_est_moi:
            c = None  # un élément de test ou d'ailleurs qui ressemble à l'Assistant n'est pas lui (D-44)
        m = mesures.get(f.id, Metriques())
        if m.mesure or c is None:
            impact, estime = scores.impact(f, m, reglages), False
        else:
            impact, estime = scores.impact_estime(c.impact, reglages), True
        if f.actif is False or (f.erreurs and not f.programme and not m.mesure):
            impact, estime = 0.0, False  # il ne se lance pas (ou son fichier est cassé) : il ne coûte rien
        niveau, raison = scores.utilite(f, maintenant, reglages, c.recommandation if c else None)
        ctx = Contexte(f, m, impact, niveau, raison, c, reglages)
        verdict = verdicts.juger(ctx)
        role = c.role if c else connaissances.description_generique(f)
        elements.append(Element(f, m, impact, estime, niveau, raison, c, verdict, verdicts.drapeaux(ctx),
                                nom_lisible(f, c), role, premieres.get(f.id)))  # fmt: skip
    distinguer_les_homonymes(elements)
    elements.sort(key=lambda e: (e.verdict.code == "apple", -e.impact, e.nom.casefold()))
    return Bilan(maintenant, elements, gains.calculer(elements), inventaire)
