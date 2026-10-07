"""Le planificateur de repas (§4), 100 % local : le menu de la semaine, sous contraintes, au meilleur score.

Contraintes dures (jamais violées) :
- allergies, régime et aliments détestés ;
- jours chargés : une recette rapide (20 min ou moins) ou des restes ;
- pas de recette cuisinée deux fois en 14 jours ;
- restes mangés dans leur durée de conservation (3 jours au plus) ;
- équipement (four, mixeur…) ; un four peut être remplacé par l'airfryer quand la recette le permet.
Contraintes tenues dès que c'est possible (sinon une alerte claire le dit) : budget à +10 % au plus, au moins 70 % de
fruits et légumes de saison, au moins un chaînage anti-gaspi par semaine.

Score à maximiser : variété (protéines, féculents, cuisines), saison, budget, anti-gaspi (un ingrédient entamé qui
sert deux fois, un plat cuisiné en grande quantité qui couvre un jour chargé), ce qu'il y a dans le frigo, tes envies,
tes notes 👍/👎, tes aliments et cuisines préférés.

Méthode : des centaines de constructions aléatoires guidées par le score, puis une amélioration locale du meilleur
menu trouvé (remplacer un plat par un autre tant que le score monte).
"""

from __future__ import annotations

import json
import math
import random
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from quotidien.config import JOURS, Reglages
from quotidien.db import Base as BaseDonnees
from quotidien.repas import envies as module_envies
from quotidien.repas.base import Base, Recette, charger

REGIME_ETIQUETTE = {"sans_porc": "sans_porc", "pescetarien": "pescetarien", "vegetarien": "vegetarien",
                    "vegan": "vegan"}  # fmt: skip
HISTORIQUE_JOURS = 14
RESTES_MAX = 2  # un plat cuisiné couvre au plus 2 repas de plus
TOLERANCE_BUDGET = 1.10
SAISON_MIN = 0.70
MOTS_CATEGORIES = {
    "poisson": {"poisson"}, "poissons": {"poisson"}, "fruits de mer": {"crustace", "mollusque"},
    "crustace": {"crustace"}, "crustaces": {"crustace"}, "coquillage": {"mollusque"}, "coquillages": {"mollusque"},
    "viande": {"volaille", "boeuf", "porc", "agneau", "charcuterie"},
    "viandes": {"volaille", "boeuf", "porc", "agneau", "charcuterie"}, "viande rouge": {"boeuf", "agneau"},
    "porc": {"porc", "charcuterie"}, "charcuterie": {"charcuterie"}, "volaille": {"volaille"},
    "fromage": {"fromage"}, "fromages": {"fromage"}, "laitage": {"laitier", "fromage"},
    "laitages": {"laitier", "fromage"}, "produits laitiers": {"laitier", "fromage"}, "legumineuses": {"legumineuse"},
    "abats": set(),
}  # fmt: skip
ALLERGENES_MOTS = {"oeuf": "oeufs", "oeufs": "oeufs", "gluten": "gluten", "ble": "gluten", "lactose": "lait",
                   "lait": "lait", "arachide": "arachides", "cacahuete": "arachides", "soja": "soja",
                   "sesame": "sesame", "moutarde": "moutarde", "celeri": "celeri", "noix": "fruits_a_coque",
                   "fruits a coque": "fruits_a_coque", "sulfites": "sulfites"}  # fmt: skip


# --- Profil -----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Profil:
    regime: str
    allergies: frozenset[str]
    interdits: frozenset[str]  # ingrédients jamais (aversions, allergies hors des 14)
    aimes: frozenset[str]
    cuisines_preferees: frozenset[str]
    portions: int
    budget: float
    equipement: frozenset[str]
    dejeuners: bool
    jours_charges: frozenset[int]
    jour_courses: int
    placard: frozenset[str]


def ingredients_designes(base: Base, mots: Iterable[str]) -> tuple[set[str], dict[str, set[str]], list[str]]:
    """Les ingrédients désignés par des mots libres (« coriandre », « poisson », « noix de pécan »…).

    Par prudence, un mot désigne tout ingrédient dont le nom le contient (« poulet » : filet et cuisse) ou qu'il
    contient (« noix de pécan » contient « noix »), plus toute une catégorie (« poisson », « viande ») ou un allergène
    (« lactose », « œufs »). Renvoie (tous les ids, ids par mot, mots non reconnus)."""
    tous: set[str] = set()
    par_mot: dict[str, set[str]] = {}
    inconnus: list[str] = []
    for brut in mots:
        mot = module_envies.normaliser(brut)
        sing = module_envies._au_singulier(mot)
        if not mot:
            continue
        trouves: set[str] = set()
        cats = MOTS_CATEGORIES.get(mot) or MOTS_CATEGORIES.get(sing) or set()
        allergene = ALLERGENES_MOTS.get(mot) or ALLERGENES_MOTS.get(sing)
        for ing in base.ingredients.values():
            noms = {module_envies._au_singulier(module_envies.normaliser(n))
                    for n in (ing.nom, ing.pluriel, ing.id.replace("_", " "), *ing.synonymes)}  # fmt: skip
            if ing.categorie in cats or (allergene and allergene in ing.allergenes):
                trouves.add(ing.id)
                continue
            for n in noms:
                if not n:
                    continue
                if (
                    sing == n
                    or (len(sing) >= 3 and f" {sing} " in f" {n} ")
                    or (len(n) >= 3 and f" {n} " in f" {sing} ")
                ):
                    trouves.add(ing.id)
                    break
        par_mot[brut] = trouves
        tous |= trouves
        if not trouves:
            inconnus.append(brut)
    return tous, par_mot, inconnus


def profil_depuis(reglages: Reglages, base: Base) -> tuple[Profil, list[str]]:
    repas, semaine = reglages["repas"], reglages["semaine"]
    interdits, _, inconnus = ingredients_designes(base, repas["deteste"])
    aimes, _, _ = ingredients_designes(base, repas["aime"])
    avert = [
        f"« {m} » (aliment détesté) ne correspond à aucun ingrédient connu : vérifie l'orthographe." for m in inconnus
    ]
    placard = frozenset(i for i in repas["placard"] if i in base.ingredients)
    profil = Profil(
        regime=repas["regime"],
        allergies=frozenset(repas["allergies"]),
        interdits=frozenset(interdits),
        aimes=frozenset(aimes - interdits),
        cuisines_preferees=frozenset(module_envies.normaliser(c) for c in repas["cuisines_preferees"]),
        portions=int(repas["portions"]),
        budget=float(repas["budget_semaine"]),
        equipement=frozenset(repas["equipement"]),
        dejeuners=bool(repas["dejeuners"]),
        jours_charges=frozenset(JOURS.index(j) for j in semaine["jours_charges"]),
        jour_courses=JOURS.index(repas["jour_courses"]),
        placard=placard,
    )
    return profil, avert


def refus(r: Recette, profil: Profil) -> str | None:
    """Pourquoi la recette est interdite pour ce profil (None : elle est permise)."""
    etiquette = REGIME_ETIQUETTE.get(profil.regime)
    if etiquette and etiquette not in r.etiquettes:
        return f"régime {profil.regime}"
    allergenes = profil.allergies & set(r.allergenes)
    if allergenes:
        return f"allergène : {', '.join(sorted(allergenes))}"
    interdits = profil.interdits & set(r.ids())
    if interdits:
        return f"aliment détesté : {', '.join(sorted(interdits))}"
    for e in r.equipement:
        if e not in profil.equipement and not (e == "four" and "airfryer" in profil.equipement
                                               and "airfryer_possible" in r.etiquettes):  # fmt: skip
            return f"équipement : {e}"
    return None


# --- Le menu ------------------------------------------------------------------------------------------------------


@dataclass
class Repas:
    jour: str  # date ISO
    moment: str  # « dejeuner » ou « diner »
    genre: str  # « cuisine » ou « reste »
    recette: str
    portions: float  # cuisine : portions cuisinées (restes compris) ; reste : portions mangées
    charge: bool = False
    reste_de: str | None = None  # pour un reste : le repas qui l'a cuisiné (« 2026-10-11/diner »)
    restes_pour: list[str] = field(default_factory=list)  # pour un plat cuisiné : les repas qu'il couvre
    raisons: list[str] = field(default_factory=list)

    @property
    def cle(self) -> str:
        return f"{self.jour}/{self.moment}"

    @property
    def date(self) -> date:
        return date.fromisoformat(self.jour)


@dataclass
class Menu:
    debut: str
    repas: list[Repas]
    alertes: list[str] = field(default_factory=list)
    cout: float = 0.0
    budget: float = 0.0
    part_saison: float = 1.0
    chainages: list[str] = field(default_factory=list)
    score: float = 0.0
    envies: list[str] = field(default_factory=list)
    cree_le: float = 0.0
    portions: int = 1

    def cuisines(self) -> list[Repas]:
        return [r for r in self.repas if r.genre == "cuisine"]

    def repas_du(self, jour: date, moment: str = "diner") -> Repas | None:
        for r in self.repas:
            if r.jour == jour.isoformat() and r.moment == moment:
                return r
        return None

    def jours(self) -> list[date]:
        d = date.fromisoformat(self.debut)
        return [d + timedelta(days=i) for i in range(7)]

    def en_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def depuis_json(cls, texte: str) -> Menu:
        d = json.loads(texte)
        repas = [Repas(**r) for r in d.pop("repas")]
        return cls(repas=repas, **d)


@dataclass(frozen=True)
class Creneau:
    jour: date
    moment: str
    charge: bool

    @property
    def cle(self) -> str:
        return f"{self.jour.isoformat()}/{self.moment}"

    @property
    def ordre(self) -> tuple[date, int]:
        return (self.jour, 0 if self.moment == "dejeuner" else 1)


def creneaux(debut: date, profil: Profil, jours: int = 7) -> list[Creneau]:
    sortie = []
    for i in range(jours):
        j = debut + timedelta(days=i)
        charge = j.weekday() in profil.jours_charges
        if profil.dejeuners:
            sortie.append(Creneau(j, "dejeuner", charge))
        sortie.append(Creneau(j, "diner", charge))
    return sortie


@dataclass
class Contexte:
    base: Base
    profil: Profil
    debut: date
    historique: set[str] = field(default_factory=set)  # recettes cuisinées dans les 14 jours d'avant
    detestees: set[str] = field(default_factory=set)  # 👎
    adorees: set[str] = field(default_factory=set)  # 👍
    frigo: dict[str, float] = field(default_factory=dict)  # ingrédient → jours avant qu'il ne se perde
    envies: list[module_envies.Criteres] = field(default_factory=list)
    restes_imposes: dict[str, Repas] = field(default_factory=dict)  # repas de cette semaine couverts la semaine passée
    cache: dict[tuple[str, int], float] = field(default_factory=dict)  # partie fixe du score local, par mois


# --- Évaluation ---------------------------------------------------------------------------------------------------


@dataclass
class Evaluation:
    score: float
    cout: float
    part_saison: float
    chainages: list[str]
    faisable: bool
    details: dict[str, float]


def _portions(profil: Profil, nb_restes: int) -> float:
    return float(profil.portions * (1 + nb_restes))


def part_de_saison(base: Base, cuisines: list[tuple[Recette, date]]) -> float:
    total = de_saison = 0
    for r, jour in cuisines:
        for id_ in r.produits_saisonniers:
            total += 1
            de_saison += base.ingredients[id_].de_saison(jour.month)
    return 1.0 if total == 0 else de_saison / total


def chainages_ingredients(
    base: Base, cuisines: list[tuple[Recette, date, float]], placard: frozenset[str]
) -> list[str]:
    """Un ingrédient frais entamé (format vendu plus grand que le besoin d'une recette) qui sert dans 2 recettes, assez
    proches pour qu'il ne se perde pas entre les deux."""
    usages: dict[str, list[tuple[date, float]]] = {}
    for r, jour, facteur in cuisines:
        for lg in r.ingredients:
            usages.setdefault(lg.id, []).append((jour, lg.quantite * facteur))
    chaines = []
    for id_, liste in usages.items():
        ing = base.ingredients[id_]
        if len(liste) < 2 or id_ in placard or ing.conservation_jours > 21 or ing.categorie in ("epice", "condiment"):
            continue
        plus_petit = min(f.quantite for f in ing.formats)
        jours = sorted(j for j, _ in liste)
        if (jours[-1] - jours[0]).days <= ing.conservation_jours and min(q for _, q in liste) < plus_petit:
            chaines.append(id_)
    return sorted(chaines)


def evaluer(ctx: Contexte, repas: list[Repas], chainage_possible: bool = True) -> Evaluation:
    base, profil = ctx.base, ctx.profil
    cuisines = [(base.recettes[r.recette], r.date, r.portions / base.recettes[r.recette].portions)
                for r in repas if r.genre == "cuisine"]  # fmt: skip
    recettes = [r for r, _, _ in cuisines]
    cout = sum(r.cout_portion_eur * f * r.portions for r, _, f in cuisines)
    part = part_de_saison(base, [(r, j) for r, j, _ in cuisines])
    chaines = chainages_ingredients(base, cuisines, profil.placard)
    liens = sum(len(r.restes_pour) for r in repas if r.genre == "cuisine")
    d: dict[str, float] = {}
    d["saison"] = 30 * part - (150 * (SAISON_MIN - part) if part < SAISON_MIN else 0)
    ratio = cout / profil.budget if profil.budget else 0
    d["budget"] = 6 * (1 - ratio) if ratio <= 1 else -60 * (ratio - 1)
    proteines = Counter(r.proteine for r in recettes if r.proteine != "aucune")
    for x in repas:
        if x.genre == "reste":
            p = base.recettes[x.recette].proteine
            if p != "aucune":
                proteines[p] += 0.5  # type: ignore[assignment]
    feculents = Counter(r.feculent for r in recettes if r.feculent != "aucun")
    cuisines_monde = Counter(r.cuisine for r in recettes)
    d["variete"] = (
        2.5 * len(proteines)
        + 1.0 * len(cuisines_monde)
        + 1.0 * len(feculents)
        - 6 * sum(max(0, n - 2) for n in proteines.values())
        - 4 * sum(max(0, n - 2) for n in feculents.values())
        - 3 * sum(max(0, n - (3 if c == "francaise" else 2)) for c, n in cuisines_monde.items())
    )
    d["antigaspi"] = 8 * min(3, len(chaines)) + 5 * min(2, liens) + 2 * min(3, max(0, liens - 2))
    d["frigo"] = sum(sum(4 + (4 if ctx.frigo[i] <= 3 else 0) for i in r.ids() if i in ctx.frigo) for r in recettes)
    envie = 0.0
    for crit in ctx.envies:
        bons = sum(1 for r in recettes if any(module_envies.correspond(c, r) for c in crit.voulus))
        envie += 6 * min(3, bons)
        envie -= 10 * sum(1 for r in recettes if any(module_envies.correspond(c, r) for c in crit.exclus))
    d["envies"] = envie
    d["gouts"] = sum(
        4 * (r.id in ctx.adorees)
        + 2 * bool(profil.aimes & set(r.ids()))
        + 2 * (module_envies.normaliser(r.cuisine) in profil.cuisines_preferees)
        for r in recettes
    )
    d["difficulte"] = -1.5 * sum(r.difficulte == "avance" for r in recettes)
    faisable = (
        cout <= profil.budget * TOLERANCE_BUDGET
        and part >= SAISON_MIN
        and (liens + len(chaines) >= 1 or not chainage_possible)
    )
    return Evaluation(sum(d.values()), round(cout, 2), round(part, 3), chaines, faisable, d)


# --- Construction ------------------------------------------------------------------------------------------------


def _score_fixe(ctx: Contexte, r: Recette, mois: int) -> float:
    """La partie du score local qui ne dépend pas des autres plats du menu (calculée une fois par mois)."""
    cle = (r.id, mois)
    if cle in ctx.cache:
        return ctx.cache[cle]
    s = 0.0
    if r.produits_saisonniers:
        de_saison = [ctx.base.ingredients[i].de_saison(mois) for i in r.produits_saisonniers]
        s += 3 * sum(de_saison) / len(de_saison) - 2 * (not all(de_saison))
    ids = set(r.ids())
    s += 2.5 * len(ids & set(ctx.frigo))
    for crit in ctx.envies:
        if any(module_envies.correspond(x, r) for x in crit.voulus):
            s += 2.5
        if any(module_envies.correspond(x, r) for x in crit.exclus):
            s -= 6
    s += 2 * (r.id in ctx.adorees) + 1 * bool(ctx.profil.aimes & ids)
    s += 1 * (module_envies.normaliser(r.cuisine) in ctx.profil.cuisines_preferees)
    budget_repas = ctx.profil.budget / 7 / max(1, ctx.profil.portions)
    s -= 2.5 * max(0.0, r.cout_portion_eur / budget_repas - 0.8)
    ctx.cache[cle] = s
    return s


@dataclass
class Compteurs:
    proteines: Counter[str] = field(default_factory=Counter)
    feculents: Counter[str] = field(default_factory=Counter)
    cuisines: Counter[str] = field(default_factory=Counter)

    def ajouter(self, r: Recette) -> None:
        self.proteines[r.proteine] += 1
        self.feculents[r.feculent] += 1
        self.cuisines[r.cuisine] += 1


def _score_local(ctx: Contexte, r: Recette, c: Creneau, deja: Compteurs, source: bool) -> float:
    s = _score_fixe(ctx, r, c.jour.month)
    if r.proteine != "aucune":
        s -= 1.5 * deja.proteines[r.proteine]
    if r.feculent != "aucun":
        s -= 1.0 * deja.feculents[r.feculent]
    if r.cuisine != "francaise":
        s -= 0.7 * deja.cuisines[r.cuisine]
    if source:
        s += 2 * r.batch
    return s


def _possible(r: Recette, c: Creneau, conservation_min: int, utilisees: set[str], nb_restes: int = 0) -> bool:
    """Permise à ce créneau : pas déjà au menu, rapide un jour chargé, assez de garde pour ses restes ; un plat ne
    couvre deux repas de plus que s'il est fait pour (« batch »)."""
    return (
        r.id not in utilisees
        and (r.rapide or not c.charge)
        and r.conservation_jours >= conservation_min
        and nb_restes <= (RESTES_MAX if r.batch else 1)
    )


def _construire(ctx: Contexte, tous: list[Creneau], futurs: list[Creneau], candidats: list[Recette],
                rng: random.Random) -> list[Repas] | None:  # fmt: skip
    profil = ctx.profil
    repas: dict[str, Repas] = {}
    for c in tous:
        if c.cle in ctx.restes_imposes:
            repas[c.cle] = ctx.restes_imposes[c.cle]
    libres = [c for c in tous if c.cle not in repas]
    # 1. Les liens « restes » : un repas chargé (ou le déjeuner du lendemain) mangé dans un plat cuisiné avant.
    proba = rng.uniform(0.35, 0.95)
    liens: dict[str, list[Creneau]] = {}
    sources_de: dict[str, str] = {}
    cibles = [c for c in libres if c.charge or c.moment == "dejeuner"] + [f for f in futurs if f.charge]
    rng.shuffle(cibles)
    for cible in cibles:
        if rng.random() > proba:
            continue
        sources = [s for s in libres if s.cle not in sources_de and not s.charge and s.ordre < cible.ordre
                   and 0 <= (cible.jour - s.jour).days <= 3 and len(liens.get(s.cle, [])) < RESTES_MAX]  # fmt: skip
        if cible in futurs:
            sources = [s for s in sources if (cible.jour - s.jour).days <= 3]
        if sources:
            s = rng.choice(sources)
            liens.setdefault(s.cle, []).append(cible)
            sources_de[cible.cle] = s.cle
    # 2. Les recettes : les sources d'abord (les plus contraintes), puis les jours chargés, puis le reste.
    utilisees: set[str] = {r.recette for r in repas.values()}
    deja = Compteurs()
    ordre = sorted((c for c in libres if c.cle not in sources_de),
                   key=lambda c: (c.cle not in liens, not c.charge, rng.random()))  # fmt: skip
    par_cle = {c.cle: c for c in tous}
    for c in ordre:
        cibles_c = sorted(liens.get(c.cle, []), key=lambda t: t.ordre)

        def pool_pour(cibles: list[Creneau], c: Creneau = c) -> list[Recette]:
            minimum = max([(t.jour - c.jour).days for t in cibles], default=0)
            return [r for r in candidats if _possible(r, c, minimum, utilisees, len(cibles))]

        pool = pool_pour(cibles_c)
        while not pool and cibles_c:
            # Pas de plat qui se garde assez, ou fait pour deux restes : on renonce au reste le plus lointain,
            # qui sera cuisiné.
            sources_de.pop(cibles_c.pop().cle, None)
            pool = pool_pour(cibles_c)
        liens[c.cle] = cibles_c
        if not pool:
            return None
        notes = [(_score_local(ctx, r, c, deja, bool(cibles_c)), r) for r in pool]
        notes.sort(key=lambda x: -x[0])
        haut = notes[:25]
        poids = [math.exp((s - haut[0][0]) / 1.5) for s, _ in haut]
        r = rng.choices([r for _, r in haut], weights=poids)[0]
        utilisees.add(r.id)
        deja.ajouter(r)
        repas[c.cle] = Repas(c.jour.isoformat(), c.moment, "cuisine", r.id, _portions(profil, len(cibles_c)),
                             c.charge, restes_pour=[t.cle for t in cibles_c])  # fmt: skip
        for t in cibles_c:
            if t.cle in par_cle:
                repas[t.cle] = Repas(t.jour.isoformat(), t.moment, "reste", r.id, float(profil.portions), t.charge,
                                     reste_de=c.cle)  # fmt: skip
    # 3. Les cibles dont la source a renoncé (rare) : cuisinées.
    for c in libres:
        if c.cle not in repas:
            pool = [r for r in candidats if _possible(r, c, 0, utilisees)]
            if not pool:
                return None
            r = max(pool, key=lambda r: _score_local(ctx, r, c, deja, False) + rng.random())
            utilisees.add(r.id)
            deja.ajouter(r)
            repas[c.cle] = Repas(c.jour.isoformat(), c.moment, "cuisine", r.id, float(profil.portions), c.charge)
    return [repas[c.cle] for c in tous]


def _ameliorer(ctx: Contexte, repas: list[Repas], candidats: list[Recette], possible: bool) -> list[Repas]:
    """Amélioration locale : remplacer un plat cuisiné par un autre tant que le score (faisabilité d'abord) monte.

    Pour rester rapide, seules les 30 meilleures alternatives (score local) de chaque repas sont essayées."""
    meilleur = evaluer(ctx, repas, possible)
    for _ in range(2):
        progres = False
        for i in range(len(repas)):
            r = repas[i]
            if r.genre != "cuisine" or r.cle in ctx.restes_imposes:
                continue
            c = Creneau(r.date, r.moment, r.charge)
            conservation_min = max([(date.fromisoformat(t[:10]) - r.date).days for t in r.restes_pour], default=0)
            utilisees = {x.recette for x in repas}
            deja = Compteurs()
            for j, x in enumerate(repas):
                if x.genre == "cuisine" and j != i:
                    deja.ajouter(ctx.base.recettes[x.recette])
            n = len(r.restes_pour)
            alternatives = [a for a in candidats if _possible(a, c, conservation_min, utilisees, n)]
            alternatives.sort(key=lambda a: -_score_local(ctx, a, c, deja, bool(r.restes_pour)))
            for alt in alternatives[:30]:
                essai = list(repas)
                essai[i] = Repas(r.jour, r.moment, "cuisine", alt.id, r.portions, r.charge, None, list(r.restes_pour))
                for j, x in enumerate(essai):
                    if x.reste_de == r.cle:
                        essai[j] = Repas(x.jour, x.moment, "reste", alt.id, x.portions, x.charge, r.cle)
                ev = evaluer(ctx, essai, possible)
                if (ev.faisable, round(ev.score, 6)) > (meilleur.faisable, round(meilleur.score, 6)):
                    repas, meilleur, progres = essai, ev, True
                    r = repas[i]
                    utilisees = {x.recette for x in repas}
        if not progres:
            break
    return repas


def candidats_pour(ctx: Contexte) -> list[Recette]:
    return [r for r in ctx.base.liste()
            if refus(r, ctx.profil) is None and r.id not in ctx.detestees and r.id not in ctx.historique]  # fmt: skip


def generer(ctx: Contexte, graine: int = 0, essais: int = 120) -> Menu:
    profil = ctx.profil
    tous = creneaux(ctx.debut, profil)
    futurs = [c for c in creneaux(ctx.debut + timedelta(days=7), profil, 3) if c.charge]
    candidats = candidats_pour(ctx)
    alertes: list[str] = []
    if len(candidats) < 14:
        alertes.append(f"Seulement {len(candidats)} recettes compatibles avec ton profil (allergies, régime, aversions,"
                       " 14 derniers jours) : le menu sera peu varié.")  # fmt: skip
    if any(c.charge for c in tous) and not any(r.rapide for r in candidats):
        alertes.append("Aucune recette rapide compatible : les jours chargés seront couverts par des restes.")
    possible = any(r.conservation_jours >= 1 for r in candidats) and len(candidats) >= 2
    rng = random.Random(graine)
    essais_ok: list[tuple[Evaluation, list[Repas]]] = []
    for _ in range(essais):
        plan = _construire(ctx, tous, futurs, candidats, rng)
        if plan is not None:
            essais_ok.append((evaluer(ctx, plan, possible), plan))
    if not essais_ok:
        # Contraintes impossibles (ex. aucune recette compatible) : un menu vide, et une alerte claire.
        alertes.append("Impossible de composer un menu avec tes contraintes : assouplis ton profil (profil.toml).")
        return Menu(ctx.debut.isoformat(), [], alertes, budget=profil.budget, cree_le=time.time(),
                    portions=profil.portions)  # fmt: skip
    essais_ok.sort(key=lambda x: (x[0].faisable, x[0].score), reverse=True)
    repas = _ameliorer(ctx, essais_ok[0][1], candidats, possible)
    ev = evaluer(ctx, repas, possible)
    if ev.cout > profil.budget * TOLERANCE_BUDGET:
        moins_cher = min(evaluer(ctx, p, possible).cout for _, p in essais_ok)
        alertes.append(f"Budget de {profil.budget:.0f} € impossible à tenir avec tes contraintes : le menu le moins "
                       f"cher trouvé coûte {min(moins_cher, ev.cout):.0f} €. Monte le budget dans profil.toml ou "
                       "assouplis tes aversions.")  # fmt: skip
    if ev.part_saison < SAISON_MIN:
        alertes.append(f"Seulement {ev.part_saison:.0%} de fruits et légumes de saison cette semaine : tes contraintes"
                       " laissent peu de recettes de saison.")  # fmt: skip
    if possible and not ev.chainages and not any(r.restes_pour for r in repas):
        alertes.append("Pas de chaînage anti-gaspi possible cette semaine.")
    _expliquer(ctx, repas, ev)
    return Menu(
        debut=ctx.debut.isoformat(),
        repas=repas,
        alertes=alertes,
        cout=ev.cout,
        budget=profil.budget,
        part_saison=ev.part_saison,
        chainages=ev.chainages,
        score=round(ev.score, 2),
        envies=[e.texte for e in ctx.envies],
        cree_le=time.time(),
        portions=profil.portions,
    )


def _expliquer(ctx: Contexte, repas: list[Repas], ev: Evaluation) -> None:
    for r in repas:
        if r.genre != "cuisine":
            continue
        rec = ctx.base.recettes[r.recette]
        raisons = []
        if r.restes_pour:
            raisons.append("cuisiné en plus grande quantité : il couvre " + ", ".join(
                _libelle_cle(t, r.date) for t in r.restes_pour))  # fmt: skip
        if any(i in ctx.frigo for i in rec.ids()):
            raisons.append("utilise ce qu'il y a dans ton frigo")
        if any(i in ev.chainages for i in rec.ids()):
            noms = [ctx.base.ingredients[i].nom for i in rec.ids() if i in ev.chainages]
            raisons.append("anti-gaspi : finit " + ", ".join(noms))
        for crit in ctx.envies:
            if any(module_envies.correspond(c, rec) for c in crit.voulus):
                raisons.append(f"ton envie : « {crit.texte} »")
                break
        if rec.id in ctx.adorees:
            raisons.append("tu l'as aimé 👍")
        r.raisons = raisons


def _libelle_cle(cle: str, depuis: date | None = None) -> str:
    """« jeudi soir » ; « mercredi soir de la semaine prochaine » si le repas visé tombe la semaine suivante."""
    jour, _, moment = cle.partition("/")
    d = date.fromisoformat(jour)
    texte = f"{JOURS[d.weekday()]} {'midi' if moment == 'dejeuner' else 'soir'}"
    if depuis is not None and d >= debut_semaine_suivante(depuis):
        texte += " de la semaine prochaine"
    return texte


# --- Mémoire : menus, notes, envies, frigo --------------------------------------------------------------------------


def debut_semaine_suivante(jour: date) -> date:
    """Le lundi qui suit `jour` (le menu du dimanche couvre la semaine qui commence le lendemain)."""
    return jour + timedelta(days=7 - jour.weekday())


def enregistrer(db: BaseDonnees, menu: Menu) -> None:
    with db.transaction() as cx:
        cx.execute("INSERT INTO menus(semaine, cree_le, json) VALUES (?, ?, ?) ON CONFLICT(semaine) DO UPDATE SET "
                   "cree_le = excluded.cree_le, json = excluded.json",
                   (menu.debut, menu.cree_le, menu.en_json()))  # fmt: skip


def menus(db: BaseDonnees) -> list[Menu]:
    return [Menu.depuis_json(r["json"]) for r in db.lignes("SELECT json FROM menus ORDER BY semaine")]


def menu_couvrant(db: BaseDonnees, jour: date) -> Menu | None:
    for m in reversed(menus(db)):
        if date.fromisoformat(m.debut) <= jour < date.fromisoformat(m.debut) + timedelta(days=7):
            return m
    return None


def historique(db: BaseDonnees, debut: date) -> set[str]:
    """Les recettes cuisinées dans les 14 jours avant `debut` (menus enregistrés)."""
    deja: set[str] = set()
    for m in menus(db):
        if m.debut == debut.isoformat():
            continue
        for r in m.cuisines():
            if debut - timedelta(days=HISTORIQUE_JOURS) <= r.date < debut:
                deja.add(r.recette)
    return deja


def restes_imposes(db: BaseDonnees, debut: date) -> dict[str, Repas]:
    """Les repas de la semaine qui commence à `debut`, déjà couverts par un plat cuisiné la semaine d'avant."""
    imposes: dict[str, Repas] = {}
    for m in menus(db):
        if date.fromisoformat(m.debut) >= debut:
            continue
        for r in m.cuisines():
            for cible in r.restes_pour:
                jour, _, moment = cible.partition("/")
                if debut <= date.fromisoformat(jour) < debut + timedelta(days=7):
                    charge = False
                    imposes[cible] = Repas(jour, moment, "reste", r.recette, float(m.portions), charge, reste_de=r.cle)
    return imposes


def notes(db: BaseDonnees) -> tuple[set[str], set[str]]:
    """(recettes 👍, recettes 👎) : la dernière note de chaque recette compte."""
    derniere: dict[str, int] = {}
    for ligne in db.lignes("SELECT recette, note FROM notes ORDER BY date, id"):
        derniere[str(ligne["recette"])] = int(ligne["note"])
    return {r for r, n in derniere.items() if n > 0}, {r for r, n in derniere.items() if n < 0}


def envies_en_attente(db: BaseDonnees, debut: date) -> list[module_envies.Criteres]:
    sortie = []
    for ligne in db.lignes(
        "SELECT etiquettes FROM envies WHERE semaine IN ('', ?) ORDER BY date", (debut.isoformat(),)
    ):
        try:
            sortie.append(module_envies.Criteres.depuis_json(json.loads(ligne["etiquettes"])))
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    return sortie


def ajouter_envie(db: BaseDonnees, criteres: module_envies.Criteres, horloge: float | None = None) -> None:
    with db.transaction() as cx:
        cx.execute("INSERT INTO envies(date, texte, etiquettes, semaine) VALUES (?, ?, ?, '')",
                   (horloge or time.time(), criteres.texte,
                    json.dumps(criteres.en_json(), ensure_ascii=False)))  # fmt: skip


def frigo_actuel(db: BaseDonnees, base: Base, maintenant: float | None = None) -> dict[str, float]:
    """Ingrédient du frigo → jours qu'il lui reste avant de se perdre (d'après sa date d'ajout)."""
    t = maintenant or time.time()
    sortie: dict[str, float] = {}
    for ligne in db.lignes("SELECT ingredient, ajoute_le FROM frigo"):
        ing = base.ingredients.get(str(ligne["ingredient"]))
        if ing is None:
            continue
        passes = (t - float(ligne["ajoute_le"])) / 86400
        sortie[ing.id] = max(0.0, ing.conservation_jours - passes)
    return sortie


def contexte(db: BaseDonnees, reglages: Reglages, debut: date, base: Base | None = None,
             maintenant: float | None = None) -> tuple[Contexte, list[str]]:  # fmt: skip
    base = base or charger()
    profil, avert = profil_depuis(reglages, base)
    adorees, detestees = notes(db)
    imposes = restes_imposes(db, debut)
    for r in imposes.values():
        r.charge = date.fromisoformat(r.jour).weekday() in profil.jours_charges
        r.portions = float(profil.portions)
    ctx = Contexte(base, profil, debut, historique(db, debut), detestees, adorees, frigo_actuel(db, base, maintenant),
                   envies_en_attente(db, debut), imposes)  # fmt: skip
    return ctx, avert


def planifier(db: BaseDonnees, reglages: Reglages, debut: date, graine: int | None = None,
              base: Base | None = None, maintenant: float | None = None) -> Menu:  # fmt: skip
    """Génère, enregistre et renvoie le menu de la semaine qui commence à `debut`."""
    ctx, avert = contexte(db, reglages, debut, base, maintenant)
    menu = generer(ctx, graine if graine is not None else debut.toordinal())
    menu.alertes = avert + menu.alertes
    enregistrer(db, menu)
    with db.transaction() as cx:
        cx.execute("UPDATE envies SET semaine = ? WHERE semaine = ''", (debut.isoformat(),))
    return menu


# --- Remplacer un jour, noter un repas ------------------------------------------------------------------------------


class JourIntrouvable(Exception):
    pass


def remplacer(db: BaseDonnees, reglages: Reglages, jour: date, moment: str = "diner", base: Base | None = None,
              maintenant: float | None = None) -> tuple[Menu, Repas]:  # fmt: skip
    """Remplace le plat d'un jour par le meilleur autre plat possible ; les restes qui en dépendent suivent."""
    menu = menu_couvrant(db, jour)
    if menu is None:
        raise JourIntrouvable("pas de menu pour ce jour-là : lance d'abord « quotidien menu »")
    cle = f"{jour.isoformat()}/{moment}"
    index = next((i for i, r in enumerate(menu.repas) if r.cle == cle), None)
    if index is None:
        raise JourIntrouvable(f"pas de repas « {moment} » le {jour.isoformat()} dans le menu")
    ctx, _ = contexte(db, reglages, date.fromisoformat(menu.debut), base, maintenant)
    ctx.restes_imposes = {}
    actuel = menu.repas[index]
    repas = list(menu.repas)
    if actuel.genre == "reste":
        # Un reste qu'on ne veut plus : on cuisine ce jour-là, et le plat d'origine en fait une portion de moins.
        for i, r in enumerate(repas):
            if r.cle == actuel.reste_de:
                r.restes_pour = [t for t in r.restes_pour if t != cle]
                r.portions = _portions(ctx.profil, len(r.restes_pour))
                repas[i] = r
    c = Creneau(jour, moment, actuel.charge)
    conservation_min = (
        max([(date.fromisoformat(t[:10]) - jour).days for t in actuel.restes_pour], default=0)
        if actuel.genre == "cuisine"
        else 0
    )
    utilisees = {r.recette for r in repas}
    possible = True
    meilleurs: list[tuple[tuple[bool, float], Recette]] = []
    for alt in candidats_pour(ctx):
        nb = len(actuel.restes_pour) if actuel.genre == "cuisine" else 0
        if alt.id == actuel.recette or not _possible(alt, c, conservation_min, utilisees, nb):
            continue
        essai = list(repas)
        nouveau = Repas(actuel.jour, moment, "cuisine", alt.id,
                        _portions(ctx.profil, len(actuel.restes_pour) if actuel.genre == "cuisine" else 0),
                        actuel.charge, None, list(actuel.restes_pour) if actuel.genre == "cuisine" else [])  # fmt: skip
        essai[index] = nouveau
        ev = evaluer(ctx, essai, possible)
        meilleurs.append(((ev.faisable, ev.score), alt))
    if not meilleurs:
        raise JourIntrouvable("aucune autre recette possible ce jour-là avec tes contraintes")
    meilleurs.sort(key=lambda x: x[0], reverse=True)
    choisie = meilleurs[0][1]
    nouveau = Repas(actuel.jour, moment, "cuisine", choisie.id,
                    _portions(ctx.profil, len(actuel.restes_pour) if actuel.genre == "cuisine" else 0), actuel.charge,
                    None, list(actuel.restes_pour) if actuel.genre == "cuisine" else [],
                    ["remplacé à ta demande"])  # fmt: skip
    repas[index] = nouveau
    for i, r in enumerate(repas):
        if r.reste_de == cle:
            repas[i] = Repas(r.jour, r.moment, "reste", choisie.id, r.portions, r.charge, cle)
    # Les restes déjà reportés sur la semaine suivante suivent aussi.
    for m in menus(db):
        if m.debut != menu.debut and any(r.reste_de == cle for r in m.repas):
            for r in m.repas:
                if r.reste_de == cle:
                    r.recette = choisie.id
            enregistrer(db, m)
    ev = evaluer(ctx, repas, possible)
    menu.repas, menu.cout, menu.part_saison, menu.chainages = repas, ev.cout, ev.part_saison, ev.chainages
    enregistrer(db, menu)
    return menu, nouveau


def noter(db: BaseDonnees, jour: date, note: int, moment: str = "diner", horloge: float | None = None) -> str:
    """Note le plat d'un jour (+1 👍, −1 👎). Renvoie l'identifiant de la recette notée."""
    menu = menu_couvrant(db, jour)
    if menu is None:
        raise JourIntrouvable("pas de menu pour ce jour-là")
    r = menu.repas_du(jour, moment)
    if r is None:
        raise JourIntrouvable(f"pas de repas « {moment} » ce jour-là")
    with db.transaction() as cx:
        cx.execute("INSERT INTO notes(date, jour, recette, note) VALUES (?, ?, ?, ?)",
                   (horloge or time.time(), jour.isoformat(), r.recette, 1 if note > 0 else -1))  # fmt: skip
    return r.recette


def imposer(db: BaseDonnees, reglages: Reglages, jour: date, recette: str, moment: str = "diner",
            base: Base | None = None, maintenant: float | None = None) -> tuple[Menu, Repas]:  # fmt: skip
    """Met `recette` au menu de ce jour (« ajouter au menu de ce soir », depuis le vide-frigo).

    Le plat qui était prévu ce jour-là ne couvre plus ses restes : ces repas-là sont recuisinés (comme `remplacer`).
    Un reste prévu ce jour-là rend sa portion au plat d'origine. Refusé si la recette est interdite par ton profil."""
    base = base or charger()
    menu = menu_couvrant(db, jour)
    if menu is None:
        raise JourIntrouvable("pas de menu pour ce jour-là : lance d'abord « quotidien menu »")
    cle = f"{jour.isoformat()}/{moment}"
    index = next((i for i, r in enumerate(menu.repas) if r.cle == cle), None)
    if index is None:
        raise JourIntrouvable(f"pas de repas « {moment} » le {jour.isoformat()} dans le menu")
    profil, _ = profil_depuis(reglages, base)
    pourquoi = refus(base.recettes[recette], profil)
    if pourquoi is not None:
        raise JourIntrouvable(f"recette interdite par ton profil ({pourquoi})")
    actuel = menu.repas[index]
    orphelins = list(actuel.restes_pour) if actuel.genre == "cuisine" else []
    if actuel.genre == "reste":
        for r in menu.repas:
            if r.cle == actuel.reste_de:
                r.restes_pour = [t for t in r.restes_pour if t != cle]
                r.portions = _portions(profil, len(r.restes_pour))
    nouveau = Repas(actuel.jour, moment, "cuisine", recette, float(profil.portions), actuel.charge,
                    raisons=["ajouté depuis ton frigo"])  # fmt: skip
    menu.repas[index] = nouveau
    for r in menu.repas:
        if r.reste_de == cle:  # ses restes deviennent des repas à cuisiner (recette provisoire, remplacée juste après)
            r.reste_de = None
    enregistrer(db, menu)
    for cible in orphelins:
        jour_cible, _, moment_cible = cible.partition("/")
        if menu_couvrant(db, date.fromisoformat(jour_cible)) is None:
            continue
        m = menu_couvrant(db, date.fromisoformat(jour_cible))
        assert m is not None
        orphelin = next((x for x in m.repas if x.cle == cible), None)
        if orphelin is not None and orphelin.genre == "reste":
            orphelin.genre, orphelin.restes_pour = "cuisine", []
            enregistrer(db, m)
            remplacer(db, reglages, date.fromisoformat(jour_cible), moment_cible, base, maintenant)
    menu = menu_couvrant(db, jour)
    assert menu is not None
    return menu, nouveau
