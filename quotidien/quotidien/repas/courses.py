"""La liste de courses du menu (§4) : ingrédients additionnés et convertis, moins ce que tu as déjà (frigo, placard),
arrondis aux formats vendus (6 œufs, 1 botte, 500 g de pâtes), rangés par rayon, avec le total estimé.

Rien ne se perd : chaque ingrédient du menu est soit dans la liste, soit marqué « déjà là » (vérifié par les tests).
La viande et le poisson frais qui servent trop tard pour tenir au frigo sont marqués « à congeler en rentrant ».
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from quotidien.config import JOURS
from quotidien.db import Base as BaseDonnees
from quotidien.repas import unites
from quotidien.repas.base import Base, Format, Ingredient
from quotidien.repas.planificateur import Menu


@dataclass
class Article:
    ingredient: str
    nom: str
    rayon: str
    emoji: str
    besoin: float  # dans l'unité de base de l'ingrédient, après ce que tu as déjà
    besoin_total: float  # avant
    unite: str
    achats: list[tuple[Format, int]]
    cout: float
    texte: str  # « 🥬 Courgettes ×3 »
    detail: str  # « il en faut 600 g »
    a_congeler: str = ""
    recettes: list[str] = field(default_factory=list)


@dataclass
class DejaLa:
    ingredient: str
    nom: str
    raison: str  # « placard » ou « frigo »
    besoin: float
    unite: str


@dataclass
class ListeCourses:
    debut: str
    jour_courses: str
    articles: list[Article]
    deja_la: list[DejaLa]
    total: float
    notes: list[str] = field(default_factory=list)

    def par_rayon(self) -> list[tuple[str, list[Article]]]:
        rayons: dict[str, list[Article]] = {}
        for a in self.articles:
            rayons.setdefault(a.rayon, []).append(a)
        return list(rayons.items())


def meilleur_achat(besoin: float, formats: tuple[Format, ...]) -> tuple[list[tuple[Format, int]], float]:
    """Le moins cher pour couvrir `besoin`, avec un format ou deux ; à prix égal, le moins de reste."""
    if besoin <= 0:
        return [], 0.0
    meilleur: tuple[float, float, list[tuple[Format, int]]] | None = None
    for grand in formats:
        n_max = math.ceil(besoin / grand.quantite - 1e-9)
        for n_grand in range(n_max + 1):
            reste = besoin - n_grand * grand.quantite
            options: list[list[tuple[Format, int]]] = []
            if reste <= 1e-9:
                options.append([(grand, n_grand)] if n_grand else [])
            else:
                for petit in formats:
                    n_petit = math.ceil(reste / petit.quantite - 1e-9)
                    combo = [(grand, n_grand)] if n_grand else []
                    if petit is grand:
                        combo = [(grand, n_grand + n_petit)]
                    else:
                        combo.append((petit, n_petit))
                    options.append(combo)
            for combo in options:
                combo = [(f, n) for f, n in combo if n > 0]
                if not combo:
                    continue
                cout = sum(f.prix * n for f, n in combo)
                quantite = sum(f.quantite * n for f, n in combo)
                cle = (round(cout, 4), round(quantite - besoin, 4), combo)
                if meilleur is None or cle[:2] < meilleur[:2]:
                    meilleur = cle
    assert meilleur is not None
    return meilleur[2], round(meilleur[0], 2)


def _nom(ing: Ingredient, n: float) -> str:
    nom = ing.pluriel if n > 1 else ing.nom
    return nom[:1].upper() + nom[1:]


def _texte_achat(ing: Ingredient, emoji: str, achats: list[tuple[Format, int]]) -> str:
    total_pieces = sum(n for f, n in achats if f.quantite == 1)
    if ing.unite == "p" and all(f.quantite == 1 for f, _ in achats):
        return f"{emoji} {_nom(ing, total_pieces)} ×{total_pieces}"
    morceaux = []
    for f, n in achats:
        libelle = f.libelle or unites.afficher(f.quantite, ing.unite)
        morceaux.append(libelle + (f" ×{n}" if n > 1 else ""))
    return f"{emoji} {_nom(ing, 1)} — {' + '.join(morceaux)}"


def jour_des_courses(debut: date, jour_courses: int) -> date:
    """Le premier jour de courses à partir du début du menu."""
    return debut + timedelta(days=(jour_courses - debut.weekday()) % 7)


def besoins(menu: Menu, base: Base) -> dict[str, list[tuple[float, str, date]]]:
    """Ingrédient → [(quantité, recette, jour)] pour chaque plat cuisiné du menu (restes inclus dans les portions)."""
    sortie: dict[str, list[tuple[float, str, date]]] = {}
    for r in menu.cuisines():
        rec = base.recettes[r.recette]
        facteur = r.portions / rec.portions
        for lg in rec.ingredients:
            sortie.setdefault(lg.id, []).append((lg.quantite * facteur, rec.id, r.date))
    return sortie


def construire(
    menu: Menu,
    base: Base,
    placard: set[str] | frozenset[str],
    frigo: dict[str, tuple[float | None, str | None]],
    jour_courses: int,
) -> ListeCourses:
    """`frigo` : ingrédient → (quantité, unité) ; une quantité inconnue (None) compte comme « assez »."""
    debut = date.fromisoformat(menu.debut)
    courses = jour_des_courses(debut, jour_courses)
    articles: list[Article] = []
    deja: list[DejaLa] = []
    notes: list[str] = []
    avant_courses: list[tuple[date, str]] = []
    for id_, usages in sorted(besoins(menu, base).items()):
        ing = base.ingredients[id_]
        total = sum(q for q, _, _ in usages)
        if id_ in placard:
            deja.append(DejaLa(id_, ing.nom, "placard", total, ing.unite))
            continue
        reste = total
        if id_ in frigo:
            quantite, unite = frigo[id_]
            if quantite is None:
                deja.append(DejaLa(id_, ing.nom, "frigo", total, ing.unite))
                continue
            try:
                dispo = unites.convertir(quantite, unite or ing.unite, ing.unite, ing.poids_piece_g)
            except unites.UniteIncompatible:
                dispo = 0.0
            reste = total - dispo
            if reste <= 1e-9:
                deja.append(DejaLa(id_, ing.nom, "frigo", total, ing.unite))
                continue
        achats, cout = meilleur_achat(reste, ing.formats)
        rayon = base.rayons[ing.rayon]
        a_congeler = ""
        if ing.congeler:
            tard = sorted({j for _, _, j in usages if (j - courses).days >= ing.conservation_jours})
            if tard:
                jours = ", ".join(JOURS[j.weekday()] for j in tard)
                a_congeler = (
                    f"à congeler en rentrant (pour {jours})"
                    if len(tard) == len(usages)
                    else f"congèle la part de {jours} en rentrant"
                )
        avant = sorted({j for _, _, j in usages if j < courses})
        if avant:
            avant_courses.append((avant[0], ing.nom))
        articles.append(
            Article(
                ingredient=id_,
                nom=ing.nom,
                rayon=ing.rayon,
                emoji=rayon["emoji"],
                besoin=reste,
                besoin_total=total,
                unite=ing.unite,
                achats=achats,
                cout=cout,
                texte=_texte_achat(ing, rayon["emoji"], achats),
                detail=f"il en faut {unites.afficher(reste, ing.unite)}",
                a_congeler=a_congeler,
                recettes=sorted({r for _, r, _ in usages}),
            )
        )
    if avant_courses:
        premier = min(j for j, _ in avant_courses)
        noms = ", ".join(sorted({n for _, n in avant_courses}))
        jour_courses_txt, premier_txt = JOURS[courses.weekday()], JOURS[premier.weekday()]
        notes.append(f"Avant tes courses du {jour_courses_txt}, il te faut déjà (dès {premier_txt}) : {noms}.")
    articles.sort(key=lambda a: (base.rayons[a.rayon]["ordre"], a.nom))
    return ListeCourses(menu.debut, JOURS[courses.weekday()], articles, deja, round(sum(a.cout for a in articles), 2),
                        notes)  # fmt: skip


def frigo_quantites(db: BaseDonnees) -> dict[str, tuple[float | None, str | None]]:
    sortie: dict[str, tuple[float | None, str | None]] = {}
    for ligne in db.lignes("SELECT ingredient, quantite, unite FROM frigo"):
        q = ligne["quantite"]
        sortie[str(ligne["ingredient"])] = (float(q) if q is not None else None, ligne["unite"])
    return sortie


def textes_rappels(liste: ListeCourses) -> list[dict[str, Any]]:
    """Les éléments de ta liste de Rappels « Courses (menu) » : titre avec le rayon en préfixe, détail en note."""
    sortie = []
    for a in liste.articles:
        note = a.detail
        if a.a_congeler:
            note += f" · {a.a_congeler}"
        sortie.append({"titre": a.texte, "note": note, "cle": f"courses:{liste.debut}:{a.ingredient}"})
    return sortie
