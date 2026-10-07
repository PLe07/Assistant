"""Le brief du matin (§7) : une seule notification à 7 h 15, puis la page `Ma journée.html` dans iCloud `Quotidien/`.

    ☀️ 14 °C → 19 °C, sec : veste légère, lunettes. Vélo OK.
    🍽️ Ce soir : curry de pois chiches (20 min) — reste pour demain midi.
    🎂 Demain : anniversaire de Léa → message prêt.

Une ligne n'apparaît que si elle a du contenu. Chaque brique est indépendante : une panne (météo hors ligne, Contacts
refusés, pas de menu) retire sa ligne ou la remplace par un message clair, jamais tout le brief.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from quotidien import config, reseau
from quotidien.html import e, ecrire_atomique, page
from quotidien.journal import log
from quotidien.repas import planificateur as pl
from quotidien.repas.base import Base, charger
from quotidien.repas.page import date_longue
from quotidien.repas.service import dossier_pages

NOM_PAGE = "Ma journée.html"


@dataclass
class Brief:
    jour: date
    lignes: list[str] = field(default_factory=list)
    details: dict[str, list[str]] = field(default_factory=dict)  # pour la page : le détail de chaque brique

    @property
    def texte(self) -> str:
        return "\n".join(self.lignes)


def composer(*lignes: str | None) -> list[str]:
    """Les lignes non vides, dans l'ordre, sans doublon."""
    vues: list[str] = []
    for ligne in lignes:
        if ligne and ligne.strip() and ligne.strip() not in vues:
            vues.append(ligne.strip())
    return vues


def _plat(base: Base, r: pl.Repas, demain: date) -> str:
    rec = base.recettes[r.recette]
    if r.genre == "reste":
        return f"restes de {rec.nom.lower()}"
    texte = f"{rec.nom.lower()} ({rec.temps_total_min} min)"
    if r.restes_pour:
        cibles = []
        for cle in r.restes_pour:
            jour, _, moment = cle.partition("/")
            quand = "demain" if date.fromisoformat(jour) == demain else pl._libelle_cle(cle, r.date).split(" ")[0]
            cibles.append(f"{quand} {'midi' if moment == 'dejeuner' else 'soir'}")
        texte += " — reste pour " + " et ".join(cibles)
    return texte


def ligne_repas(db: Any, base: Base, jour: date) -> str | None:
    menu = pl.menu_couvrant(db, jour)
    if menu is None:
        return None
    demain = jour + timedelta(days=1)
    morceaux = []
    for moment, libelle in (("dejeuner", "Ce midi"), ("diner", "Ce soir")):
        r = next((x for x in menu.repas if x.date == jour and x.moment == moment), None)
        if r is not None:
            morceaux.append(f"{libelle} : {_plat(base, r, demain)}")
    return "🍽️ " + " · ".join(morceaux) + "." if morceaux else None


def ligne_veille(db: Any, base: Base, reglages: config.Reglages, jour: date) -> str | None:
    """« ❄️ Ce soir, sors le poulet du congélateur… » : ce qu'il faudra faire ce soir pour demain."""
    from quotidien.repas import rappels_veille

    menu = pl.menu_couvrant(db, jour + timedelta(days=1)) or pl.menu_couvrant(db, jour)
    if menu is None:
        return None
    jour_courses = pl.profil_depuis(reglages, base)[0].jour_courses
    textes = [r.texte for r in rappels_veille.rappels(menu, base, jour_courses) if r.jour == jour]
    return " ".join(textes[:2]) or None


def ligne_courses(db: Any, base: Base, reglages: config.Reglages, jour: date) -> str | None:
    from quotidien.repas import service

    menu = pl.menu_couvrant(db, jour)
    if menu is None:
        return None
    if jour.weekday() != pl.profil_depuis(reglages, base)[0].jour_courses:
        return None
    liste = service.liste_de(db, reglages, menu, base)
    return (f"🛒 Jour de courses : {len(liste.articles)} articles, ≈ {liste.total:.0f} € "
            "(liste dans Rappels et sur la page).")  # fmt: skip


def produire(db: Any, reglages: config.Reglages, jour: date, maintenant: float,
             meteo: Callable[[], str | None] | None = None,
             anniversaires: Callable[[], str | None] | None = None,
             base: Base | None = None) -> Brief:  # fmt: skip
    """Le brief du jour. `meteo` et `anniversaires` sont fournis par le démon (et imités dans les tests)."""
    base = base or charger()
    brief = Brief(jour)
    morceaux: list[str | None] = []
    for nom, fabrique in (
        ("météo", meteo or (lambda: _meteo(db, reglages, jour, maintenant))),
        ("repas", lambda: ligne_repas(db, base, jour)),
        ("veille", lambda: ligne_veille(db, base, reglages, jour)),
        ("courses", lambda: ligne_courses(db, base, reglages, jour)),
        ("anniversaires", anniversaires or (lambda: None)),
    ):
        try:
            morceaux.append(fabrique())
        except Exception as err:  # noqa: BLE001 - une brique en panne ne doit jamais tuer le brief
            log().warning("brief : la brique %s a échoué (%s)", nom, err.__class__.__name__)
            morceaux.append(None)
    brief.lignes = composer(*morceaux)
    return brief


def _meteo(db: Any, reglages: config.Reglages, jour: date, maintenant: float) -> str | None:
    from quotidien.meteo import service as meteo

    return meteo.du_jour(db, reglages, jour, lambda: maintenant, reseau.telecharger).texte


def publier(brief: Brief, dossier: Path | None = None) -> Path:
    dossier = dossier or dossier_pages()
    lignes = "".join(f'<div class="carte"><p>{e(x)}</p></div>' for x in brief.lignes) or (
        '<p class="vide">Rien de particulier aujourd\'hui.</p>')  # fmt: skip
    corps = (f"<h1>Ma journée</h1><p class=\"sous\">{e(date_longue(brief.jour).capitalize())}</p>{lignes}"
             '<p class="meta">Le menu de la semaine et la liste de courses : « Menu de la semaine.html », '
             "dans le même dossier.</p>")  # fmt: skip
    chemin = dossier / NOM_PAGE
    ecrire_atomique(chemin, page(f"Ma journée — {date_longue(brief.jour)}", corps))
    # Pour l'assistant et les autres outils (INTEGRATION.md) : le brief en JSON, à lire seulement.
    donnees = {"date": brief.jour.isoformat(), "lignes": brief.lignes}
    ecrire_atomique(config.dossier_support() / "brief.json", json.dumps(donnees, ensure_ascii=False))
    return chemin
