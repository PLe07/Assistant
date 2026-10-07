"""Les rappels de la veille au soir (§4) : « sors le poulet du congélateur », « fais tremper les pois chiches ».

- Légumineuses sèches : à faire tremper la veille (12 h).
- Viande ou poisson frais congelés en rentrant des courses (trop tard pour tenir au frigo) : à sortir la veille et à
  mettre au réfrigérateur.
- Poisson et crevettes achetés surgelés : à décongeler la veille au réfrigérateur.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from quotidien.config import JOURS
from quotidien.repas import courses as module_courses
from quotidien.repas.base import Base
from quotidien.repas.planificateur import Menu


@dataclass(frozen=True)
class RappelVeille:
    jour: date  # le soir où il faut le faire
    pour: date  # le jour du repas
    texte: str
    cle: str


def rappels(menu: Menu, base: Base, jour_courses: int) -> list[RappelVeille]:
    debut = date.fromisoformat(menu.debut)
    courses = module_courses.jour_des_courses(debut, jour_courses)
    sortie: list[RappelVeille] = []
    for r in menu.cuisines():
        rec = base.recettes[r.recette]
        veille = r.date - timedelta(days=1)
        for lg in rec.ingredients:
            ing = base.ingredients[lg.id]
            nom = ing.nom
            if ing.trempage_heures:
                texte = f"🫘 Ce soir, fais tremper les {ing.pluriel} pour {_quand(r.date)} ({rec.nom})."
            elif ing.congeler and (r.date - courses).days >= ing.conservation_jours:
                quoi = _article(ing.id, nom)
                pronom = "les" if quoi.startswith("les ") else ("la" if quoi.startswith("la ") else "le")
                texte = (f"❄️ Ce soir, sors {quoi} du congélateur et mets-{pronom} au réfrigérateur pour "
                         f"{_quand(r.date)} ({rec.nom}).")  # fmt: skip
            elif ing.rayon == "surgeles" and ing.categorie in ("poisson", "crustace"):
                texte = (f"❄️ Ce soir, mets {_article(ing.id, nom)} à décongeler au réfrigérateur pour {_quand(r.date)} "
                         f"({rec.nom}).")  # fmt: skip
            else:
                continue
            sortie.append(RappelVeille(veille, r.date, texte, f"veille:{r.cle}:{lg.id}"))
    return sorted(sortie, key=lambda x: (x.jour, x.cle))


def _quand(jour: date) -> str:
    return f"demain {JOURS[jour.weekday()]}"


ARTICLES = {
    "poulet_filet": "le poulet",
    "poulet_cuisse": "les cuisses de poulet",
    "dinde": "les escalopes de dinde",
    "boeuf_hache": "la viande hachée",
    "boeuf_braiser": "le bœuf",
    "boeuf_emince": "le bœuf",
    "porc_echine": "le porc",
    "saucisse": "les saucisses",
    "merguez": "les merguez",
    "agneau": "l'agneau",
    "saumon": "le saumon",
    "poisson_blanc": "le poisson",
    "crevette": "les crevettes",
    "moules": "les moules",
}


def _article(id_: str, nom: str) -> str:
    return ARTICLES.get(id_, f"le {nom}")
