"""La base de recettes et d'ingrédients, chargée une fois (lecture seule).

Les fichiers JSON sont produits par `outils/construire_recettes.py` à partir des sources écrites à la main.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

ICI = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Format:
    quantite: float
    prix: float
    libelle: str


@dataclass(frozen=True)
class Ingredient:
    id: str
    nom: str
    pluriel: str
    rayon: str
    unite: str  # g, ml ou p
    poids_piece_g: float | None
    formats: tuple[Format, ...]
    allergenes: tuple[str, ...]
    categorie: str
    saison: tuple[int, ...] | None  # None : pas un fruit ou légume ; () : importé
    compte_saison: bool
    conservation_jours: int
    placard: bool
    congeler: bool
    hache: bool
    trempage_heures: int
    vegetarien: bool
    vegan: bool
    pescetarien: bool
    porc: bool
    synonymes: tuple[str, ...]

    @property
    def prix_unitaire(self) -> float:
        return min(f.prix / f.quantite for f in self.formats)

    def de_saison(self, mois: int) -> bool:
        return self.saison is not None and mois in self.saison


@dataclass(frozen=True)
class Ligne:
    id: str
    quantite: float
    unite: str
    note: str = ""


@dataclass(frozen=True)
class Recette:
    id: str
    nom: str
    famille: str
    portions: int
    ingredients: tuple[Ligne, ...]
    etapes: tuple[str, ...]
    preparation_min: int
    cuisson_min: int
    temps_total_min: int
    difficulte: str
    cuisine: str
    proteine: str
    feculent: str
    cout_total_eur: float
    cout_portion_eur: float
    saisons: tuple[int, ...]
    produits_saisonniers: tuple[str, ...]
    etiquettes: frozenset[str]
    allergenes: tuple[str, ...]
    ustensiles: tuple[str, ...]
    equipement: tuple[str, ...]
    conservation_jours: int
    conservation: str
    securite: tuple[str, ...]
    source: str

    @property
    def rapide(self) -> bool:
        return "rapide" in self.etiquettes

    @property
    def batch(self) -> bool:
        return "batch" in self.etiquettes

    def ids(self) -> list[str]:
        return [lg.id for lg in self.ingredients]


@dataclass
class Base:
    ingredients: dict[str, Ingredient]
    recettes: dict[str, Recette]
    rayons: dict[str, dict[str, Any]]
    substitutions: dict[str, list[dict[str, str]]]
    calendrier: dict[str, dict[str, list[str]]]
    synonymes: dict[str, str] = field(default_factory=dict)

    def ingredient(self, id_: str) -> Ingredient:
        return self.ingredients[id_]

    def liste(self) -> list[Recette]:
        return list(self.recettes.values())


def _ingredient(d: dict[str, Any]) -> Ingredient:
    saison = d["saison"]
    return Ingredient(
        id=d["id"],
        nom=d["nom"],
        pluriel=d["pluriel"],
        rayon=d["rayon"],
        unite=d["unite"],
        poids_piece_g=d["poids_piece_g"],
        formats=tuple(Format(f["quantite"], f["prix"], f["libelle"]) for f in d["formats"]),
        allergenes=tuple(d["allergenes"]),
        categorie=d["categorie"],
        saison=None if saison is None else (() if saison == "imp" else tuple(saison)),
        compte_saison=d["compte_saison"],
        conservation_jours=d["conservation_jours"],
        placard=d["placard"],
        congeler=d["congeler"],
        hache=d["hache"],
        trempage_heures=d["trempage_heures"],
        vegetarien=d["vegetarien"],
        vegan=d["vegan"],
        pescetarien=d["pescetarien"],
        porc=d["porc"],
        synonymes=tuple(d["synonymes"]),
    )


def _recette(d: dict[str, Any]) -> Recette:
    return Recette(
        id=d["id"],
        nom=d["nom"],
        famille=d["famille"],
        portions=d["portions"],
        ingredients=tuple(Ligne(i["id"], i["quantite"], i["unite"], i.get("note", "")) for i in d["ingredients"]),
        etapes=tuple(d["etapes"]),
        preparation_min=d["preparation_min"],
        cuisson_min=d["cuisson_min"],
        temps_total_min=d["temps_total_min"],
        difficulte=d["difficulte"],
        cuisine=d["cuisine"],
        proteine=d["proteine"],
        feculent=d["feculent"],
        cout_total_eur=d["cout_total_eur"],
        cout_portion_eur=d["cout_portion_eur"],
        saisons=tuple(d["saisons"]),
        produits_saisonniers=tuple(d["produits_saisonniers"]),
        etiquettes=frozenset(d["etiquettes"]),
        allergenes=tuple(d["allergenes"]),
        ustensiles=tuple(d["ustensiles"]),
        equipement=tuple(d["equipement"]),
        conservation_jours=d["conservation_jours"],
        conservation=d["conservation"],
        securite=tuple(d["securite"]),
        source=d["source"],
    )


def _lire(nom: str) -> Any:
    return json.loads((ICI / nom).read_text(encoding="utf-8"))


@cache
def charger() -> Base:
    ingredients = {k: _ingredient(v) for k, v in _lire("ingredients.json").items()}
    recettes: dict[str, Recette] = {}
    for fichier in sorted((ICI / "recettes").glob("*.json")):
        for d in json.loads(fichier.read_text(encoding="utf-8")):
            recettes[d["id"]] = _recette(d)
    synonymes: dict[str, str] = {}
    for ing in ingredients.values():
        for nom in (ing.nom.lower(), ing.pluriel.lower(), ing.id.replace("_", " "), *ing.synonymes):
            synonymes.setdefault(nom, ing.id)
    return Base(
        ingredients=ingredients,
        recettes=recettes,
        rayons=_lire("rayons.json"),
        substitutions=_lire("substitutions.json"),
        calendrier=_lire("saisons.json"),
        synonymes=synonymes,
    )
