"""Le menu de la semaine assemblé : quelle semaine, le menu (gardé ou créé), la liste de courses, la page publiée.

- La semaine affichée est celle en cours ; le dimanche à partir de l'heure du menu (17 h par défaut), c'est la
  suivante (celle que le démon vient de préparer).
- `regenerer` refait le menu de cette semaine avec une autre graine (un autre menu, mêmes contraintes).
- La page `Menu de la semaine.html` va dans iCloud `Quotidien/` (ou, sans iCloud Drive, dans Application Support).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from quotidien import config, ia
from quotidien.config import JOURS, Reglages
from quotidien.db import Base as BaseDonnees
from quotidien.repas import courses as module_courses
from quotidien.repas import page as module_page
from quotidien.repas import planificateur as pl
from quotidien.repas.base import Base, charger


@dataclass
class ResultatMenu:
    menu: pl.Menu
    liste: module_courses.ListeCourses
    page: Path
    nouveau: bool


def semaine_affichee(reglages: Reglages, maintenant: datetime) -> date:
    jour = maintenant.date()
    lundi = jour - timedelta(days=jour.weekday())
    h = reglages["horaires"]
    if JOURS[jour.weekday()] == h["menu_jour"] and maintenant.hour * 60 + maintenant.minute >= config.en_minutes(
        h["menu_heure"]
    ):
        return pl.debut_semaine_suivante(jour)
    return lundi


def menu_de(db: BaseDonnees, debut: date) -> pl.Menu | None:
    for m in pl.menus(db):
        if m.debut == debut.isoformat():
            return m
    return None


def dossier_pages() -> Path:
    return config.dossier_icloud() if config.icloud_drive().is_dir() else config.dossier_support()


def liste_de(db: BaseDonnees, reglages: Reglages, menu: pl.Menu, base: Base) -> module_courses.ListeCourses:
    profil, _ = pl.profil_depuis(reglages, base)
    return module_courses.construire(menu, base, profil.placard, module_courses.frigo_quantites(db),
                                     profil.jour_courses)  # fmt: skip


def produire(db: BaseDonnees, reglages: Reglages, debut: date, regenerer: bool = False, base: Base | None = None,
             maintenant: float | None = None) -> ResultatMenu:  # fmt: skip
    base = base or charger()
    menu = None if regenerer else menu_de(db, debut)
    nouveau = menu is None
    if menu is None:
        n = int(db.lire_meta(f"regenerations:{debut.isoformat()}", "0") or 0) + (1 if regenerer else 0)
        db.ecrire_meta(f"regenerations:{debut.isoformat()}", str(n))
        menu = pl.planifier(db, reglages, debut, graine=debut.toordinal() * 100 + n, base=base, maintenant=maintenant)
    liste = liste_de(db, reglages, menu, base)
    page = module_page.publier(menu, base, liste, dossier_pages())
    return ResultatMenu(menu, liste, page, nouveau)


def ligne_repas(base: Base, r: pl.Repas) -> str:
    rec = base.recettes[r.recette]
    moment = " midi" if r.moment == "dejeuner" else ""
    if r.genre == "reste":
        return f"{JOURS[r.date.weekday()]}{moment} : restes de {rec.nom.lower()}"
    suite = f" ({rec.temps_total_min} min)"
    if r.restes_pour:
        suite += " — en faire plus pour " + ", ".join(pl._libelle_cle(c, r.date) for c in r.restes_pour)
    return f"{JOURS[r.date.weekday()]}{moment} : {rec.nom}{suite}"


def resume(resultat: ResultatMenu, base: Base) -> str:
    menu, liste = resultat.menu, resultat.liste
    debut = date.fromisoformat(menu.debut)
    lignes = [f"🍽️ Menu de la semaine du {module_page.date_longue(debut)}"
              f" ({menu.cout:.0f} € de repas, {menu.part_saison:.0%} de saison)"]  # fmt: skip
    lignes += [f"⚠️ {a}" for a in menu.alertes]
    lignes += ["  " + ligne_repas(base, r) for r in menu.repas]
    lignes.append(f"🛒 Courses du {liste.jour_courses} : {len(liste.articles)} articles, ≈ {liste.total:.2f} €")
    lignes += [f"   {n}" for n in liste.notes]
    lignes.append(f"Page : {resultat.page}")
    return "\n".join(lignes)


class JourInconnu(ValueError):
    pass


def jour_dans_menu(menu: pl.Menu, nom: str) -> date:
    """« jeudi » (ou « jeu », « demain », « aujourd'hui », une date ISO) → la date de ce jour dans le menu."""
    t = nom.strip().lower()
    if t in ("aujourd'hui", "aujourdhui", "ce soir"):
        return date.fromtimestamp(time.time())
    if t == "demain":
        return date.fromtimestamp(time.time()) + timedelta(days=1)
    try:
        return date.fromisoformat(t)
    except ValueError:
        pass
    j = config.normaliser_jour(t)
    if j is None:
        raise JourInconnu(f"« {nom} » n'est pas un jour (lundi … dimanche, demain, ou AAAA-MM-JJ)")
    return date.fromisoformat(menu.debut) + timedelta(days=JOURS.index(j))


def jour_passe(nom: str, aujourdhui: date) -> date:
    """Pour noter un repas : « jeudi » est le dernier jeudi passé (ou aujourd'hui si on est jeudi)."""
    t = nom.strip().lower()
    if t in ("aujourd'hui", "aujourdhui", "ce soir"):
        return aujourdhui
    if t == "hier":
        return aujourdhui - timedelta(days=1)
    try:
        return date.fromisoformat(t)
    except ValueError:
        pass
    j = config.normaliser_jour(t)
    if j is None:
        raise JourInconnu(f"« {nom} » n'est pas un jour (lundi … dimanche, hier, ou AAAA-MM-JJ)")
    return aujourdhui - timedelta(days=(aujourdhui.weekday() - JOURS.index(j)) % 7)


def noter_envie(db: BaseDonnees, reglages: Reglages, texte: str, maintenant: float, client: ia.Client | None = None,
                lire_trousseau: ia.LireTrousseau | None = None) -> tuple[bool, str]:  # fmt: skip
    """Une envie pour le prochain menu (commande ou raccourci « Envie de… ») : (comprise ?, réponse à afficher)."""
    from quotidien.repas import envies

    texte = texte.strip()
    if not texte:
        return False, 'Écris ton envie : quotidien envie "mexicain et léger"'
    criteres = envies.comprendre(db, reglages.reglages, texte, client=client, lire_trousseau=lire_trousseau)
    if criteres.vide():
        return False, "🤔 Je n'ai pas compris cette envie (essaie « italien », « léger », « pas de poisson »…)."
    pl.ajouter_envie(db, criteres, maintenant)
    return True, f"✅ Envie notée pour le prochain menu : « {texte} »" + (" (comprise par l'IA)" if criteres.par_ia
                                                                         else "")  # fmt: skip
