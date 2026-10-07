"""Du frigo aux recettes (§5) : ce que tu peux cuisiner tout de suite avec ce que tu as.

Pour chaque recette permise par ton profil (allergies, régime, aversions, équipement, plats notés 👎) :
- on ne compte pas le placard de base (sel, huile, pâtes, riz, épices… réglable dans profil.toml) ;
- un ingrédient manquant qu'un produit que tu as peut remplacer (table de substitutions) n'est plus « manquant » :
  la recette dit comment (« pas de crème ? un yaourt grec fait l'affaire ») ;
- au plus 2 ingrédients manquants (une herbe fraîche ou un accompagnement absents ne bloquent pas) ;
- score : la part de la recette que tu as déjà, et un bonus pour ce qui se perd vite (restes, produits frais), pour
  ce que tu as en quantité suffisante et pour les recettes rapides.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quotidien.frigo.analyse_texte import Element
from quotidien.repas.base import Base, Ligne, Recette
from quotidien.repas.planificateur import Profil, refus

MANQUANTS_MAX = 2
PERISSABLE_JOURS = 5
# Il manque la viande ou le poisson du plat : ce n'est plus vraiment « avec ce que tu as ».
CATEGORIES_PRINCIPALES = {"boeuf", "volaille", "porc", "poisson", "agneau", "crustace", "mollusque", "charcuterie",
                          "tofu"}  # fmt: skip
ECART_VARIETE = 15  # on préfère une autre protéine si elle n'est pas beaucoup moins pertinente


@dataclass
class Adaptation:
    manque: str
    par: str
    conseil: str


@dataclass
class Proposition:
    recette: Recette
    score: float
    utilises: list[str]  # ce que tu as, utilisé par la recette
    manquants: list[str]
    adaptations: list[Adaptation] = field(default_factory=list)
    juste: list[str] = field(default_factory=list)  # tu en as, mais un peu moins que la recette n'en demande
    sans: list[str] = field(default_factory=list)  # facultatifs que tu n'as pas (herbes, accompagnement)

    @property
    def temps(self) -> int:
        return self.recette.temps_total_min

    @property
    def servis(self) -> set[str]:
        """Ce que la recette utilise de ce que tu as (frigo ou placard), directement ou comme remplaçant."""
        return set(self.utilises) | {a.par for a in self.adaptations}


def _perissable(base: Base, e: Element) -> bool:
    return e.reste or base.ingredients[e.ingredient or ""].conservation_jours <= PERISSABLE_JOURS


def facultatif(base: Base, lg: Ligne) -> bool:
    """Une herbe fraîche, un accompagnement (« salade en accompagnement ») : le plat se fait sans."""
    return base.ingredients[lg.id].categorie == "herbe" or lg.note.startswith("en accompagnement")


def evaluer(base: Base, r: Recette, profil: Profil, frigo: dict[str, Element]) -> Proposition | None:
    # Le placard ne compte pas… sauf ce que tu as dit avoir (« un reste de riz » : à finir en priorité).
    besoins = [lg for lg in r.ingredients if lg.id not in profil.placard or lg.id in frigo]
    if not besoins:
        return None
    utilises = sorted({lg.id for lg in besoins if lg.id in frigo})
    if not utilises:
        return None
    manquants: list[str] = []
    sans: list[str] = []  # facultatifs absents
    adaptations: list[Adaptation] = []
    for lg in besoins:
        if lg.id in frigo or lg.id in manquants or lg.id in sans:
            continue
        sub = next((s for s in base.substitutions.get(lg.id, []) if s["par"] in frigo or s["par"] in profil.placard),
                   None)  # fmt: skip
        if sub is not None:
            adaptations.append(Adaptation(lg.id, sub["par"], sub["conseil"]))
        elif facultatif(base, lg):
            sans.append(lg.id)
        else:
            manquants.append(lg.id)
    if len(manquants) > MANQUANTS_MAX:
        return None
    juste = []
    facteur = profil.portions / r.portions
    for lg in besoins:
        e = frigo.get(lg.id)
        if e is not None and e.quantite is not None and e.quantite < 0.7 * lg.quantite * facteur:
            juste.append(lg.id)
    ids = {lg.id for lg in besoins} - set(sans)
    # Une adaptation avec un produit du frigo vaut presque l'ingrédient ; avec un produit du placard, un peu moins.
    adaptes = sum(0.8 if a.par in frigo else 0.4 for a in adaptations)
    # Des pâtes ou du riz que tu as dit avoir comptent à moitié (sauf un reste) : ce n'est pas eux qu'il faut finir.
    presents = sum(0.5 if i in profil.placard and not frigo[i].reste else 1.0 for i in utilises)
    part = (presents + adaptes) / len(ids)
    # Ce qui se perd vite dans ton frigo (restes, frais) : la recette qui en finit le plus passe devant ; puis celle
    # qui utilise le plus de ce que tu as dit avoir (hors placard), y compris comme remplaçant.
    servis = set(utilises) | {a.par for a in adaptations if a.par in frigo}
    a_finir = [i for i, e in frigo.items() if _perissable(base, e)]
    finis = [i for i in servis if i in a_finir]
    dits = [i for i, e in frigo.items() if i not in profil.placard or e.reste]
    score = 100 * part + 12 * len(finis) + (20 * len(finis) / len(a_finir) if a_finir else 0)
    score += 20 * len(servis & set(dits)) / len(dits) if dits else 0
    if a_finir and not finis:
        score -= 25  # n'utilise rien de ce qui va se perdre
    score += 4 * len(utilises) - 15 * len(manquants) - 6 * len(juste) - 3 * len(adaptations) - 4 * len(sans)
    score -= 12 * sum(1 for m in manquants if base.ingredients[m].categorie in CATEGORIES_PRINCIPALES)
    score += 3 * r.rapide
    return Proposition(r, round(score, 2), utilises, manquants, adaptations, sorted(set(juste)), sans)


def proposer(base: Base, profil: Profil, frigo: dict[str, Element], n: int = 3,
             detestees: set[str] | frozenset[str] = frozenset()) -> list[Proposition]:  # fmt: skip
    """Les `n` meilleures recettes réalisables tout de suite (au plus 2 ingrédients manquants), jamais une recette
    interdite par ton profil."""
    if not frigo:
        return []
    propositions = []
    for r in base.liste():
        if r.id in detestees or refus(r, profil) is not None:
            continue
        p = evaluer(base, r, profil, frigo)
        if p is not None:
            propositions.append(p)
    propositions.sort(key=lambda p: (-p.score, p.recette.temps_total_min, p.recette.id))
    # Variété : pas deux fois la même protéine dans les 3 premières, quand une autre presque aussi pertinente existe.
    choisies: list[Proposition] = []
    restantes = list(propositions)
    while restantes and len(choisies) < n:
        p = restantes[0]
        if any(c.recette.proteine == p.recette.proteine != "aucune" for c in choisies):
            autre = next((q for q in restantes if q.score >= p.score - ECART_VARIETE
                          and all(c.recette.proteine != q.recette.proteine for c in choisies)), None)  # fmt: skip
            p = autre or p
        choisies.append(p)
        restantes.remove(p)
    return sorted(choisies, key=lambda p: (-p.score, p.recette.temps_total_min, p.recette.id))
