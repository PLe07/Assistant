"""La page du menu de la semaine (§4) : `Menu de la semaine.html` dans iCloud `Quotidien/`.

Une page autonome : le menu jour par jour (et pourquoi chaque plat), chaque recette dépliable (quantités à la bonne
échelle, étapes, sécurité, conservation), la liste de courses par rayon avec le total, et les alertes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from quotidien.config import JOURS, NOMS_ALLERGENES
from quotidien.html import e, ecrire_atomique, page
from quotidien.repas import unites
from quotidien.repas.base import Base, Recette
from quotidien.repas.courses import ListeCourses
from quotidien.repas.planificateur import Menu, Repas

MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre")  # fmt: skip
NOM_PAGE = "Menu de la semaine.html"


def date_longue(d: date) -> str:
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"


def _quantite(base: Base, id_: str, q: float, unite: str) -> str:
    ing = base.ingredients[id_]
    if unite == "p":
        nom = ing.pluriel if q > 1 else ing.nom
        return f"{unites.afficher(q, 'p')} {nom}"
    return (
        f"{unites.afficher(q, unite)} de {ing.nom}"
        if ing.nom[:1].lower() not in "aeéèêiîoôuyœh"
        else f"{unites.afficher(q, unite)} d'{ing.nom}"
    )


def bloc_recette(base: Base, rec: Recette, portions: float) -> str:
    facteur = portions / rec.portions
    lignes = []
    for lg in rec.ingredients:
        texte = _quantite(base, lg.id, lg.quantite * facteur, lg.unite)
        if lg.note:
            texte += f" ({lg.note})"
        lignes.append(f"<li>{e(texte)}</li>")
    etapes = "".join(f"<li>{e(x)}</li>" for x in rec.etapes)
    allergenes = ", ".join(NOMS_ALLERGENES[a] for a in rec.allergenes) or "aucun des 14"
    securite = "".join(f"<li>{e(x)}</li>" for x in rec.securite)
    return (
        f"<details><summary>{e(rec.nom)}</summary>"
        f'<p class="meta">{rec.preparation_min} min de préparation · {rec.cuisson_min} min de cuisson · '
        f"pour {unites.fraction(portions)} portion{'s' if portions > 1 else ''} · allergènes : {e(allergenes)}</p>"
        f"<h3>Ingrédients</h3><ul>{''.join(lignes)}</ul><h3>Étapes</h3><ol>{etapes}</ol>"
        + (f"<h3>Sécurité</h3><ul>{securite}</ul>" if securite else "")
        + f'<p class="meta">{e(rec.conservation)}</p></details>'
    )


def _ligne_repas(base: Base, r: Repas) -> str:
    rec = base.recettes[r.recette]
    moment = "midi" if r.moment == "dejeuner" else "soir"
    jour = date_longue(r.date)
    puces = []
    if r.charge:
        puces.append("jour chargé")
    if r.genre == "reste":
        titre = f"Restes : {rec.nom}"
        puces.append("rien à cuisiner")
        corps = ""
    else:
        titre = rec.nom
        puces.append(f"{rec.temps_total_min} min")
        if r.restes_pour:
            puces.append(f"à cuisiner pour {unites.fraction(r.portions)}")
        corps = bloc_recette(base, rec, r.portions)
    raisons = "".join(f'<span class="puce">{e(x)}</span>' for x in r.raisons)
    return (
        f'<div class="carte"><div class="ligne"><span class="jour">{e(jour)} {moment}</span>'
        f"<span><strong>{e(titre)}</strong></span></div>"
        f"<div>{''.join(f'<span class=puce>{e(p)}</span>' for p in puces)}{raisons}</div>{corps}</div>"
    )


def rendre(menu: Menu, base: Base, liste: ListeCourses) -> str:
    debut = date.fromisoformat(menu.debut)
    corps = [f"<h1>🍽️ Menu de la semaine</h1><p class=\"sous\">Du {e(date_longue(debut))} · {menu.portions} "
             f"personne{'s' if menu.portions > 1 else ''} · coût des repas ≈ {menu.cout:.2f} € · "
             f"{menu.part_saison:.0%} de saison</p>"]  # fmt: skip
    for alerte in menu.alertes:
        corps.append(f'<div class="carte alerte">⚠️ {e(alerte)}</div>')
    if menu.envies:
        corps.append('<p class="meta">Tes envies prises en compte : ' + e(" · ".join(menu.envies)) + "</p>")
    corps.append("<h2>Les repas</h2>")
    if not menu.repas:
        corps.append('<p class="vide">Pas de menu possible avec ton profil actuel.</p>')
    corps += [_ligne_repas(base, r) for r in menu.repas]
    corps.append(f"<h2>🛒 Liste de courses</h2><p class=\"meta\">Courses prévues le {e(liste.jour_courses)} · total "
                 f"estimé <span class=\"total\">{liste.total:.2f} €</span></p>")  # fmt: skip
    for note in liste.notes:
        corps.append(f'<div class="carte alerte">{e(note)}</div>')
    for rayon, articles in liste.par_rayon():
        items = []
        for a in articles:
            extra = f" — {a.detail}" + (f" · <strong>{e(a.a_congeler)}</strong>" if a.a_congeler else "")
            items.append(f'<li>{e(a.texte)}<span class="meta">{extra}</span></li>')
        corps.append(f'<div class="carte"><h3>{e(base.rayons[rayon]["nom"])}</h3><ul>{"".join(items)}</ul></div>')
    if liste.deja_la:
        deja = ", ".join(f"{d.nom} ({d.raison})" for d in liste.deja_la)
        corps.append(f'<p class="meta">Déjà là : {e(deja)}.</p>')
    if menu.chainages:
        noms = ", ".join(base.ingredients[i].nom for i in menu.chainages)
        corps.append(f'<p class="meta">♻️ Anti-gaspi : {e(noms)} servent dans plusieurs plats.</p>')
    return page("Menu de la semaine", "".join(corps))


def publier(menu: Menu, base: Base, liste: ListeCourses, dossier: Path) -> Path:
    chemin = dossier / NOM_PAGE
    ecrire_atomique(chemin, rendre(menu, base, liste))
    return chemin
