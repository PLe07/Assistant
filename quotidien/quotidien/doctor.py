"""`quotidien doctor` (§7) : l'état de chaque brique, les autorisations, le budget IA et la prochaine exécution de
chaque tâche, en clair. Ne modifie rien (lecture seule, pas même une demande d'accès)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from quotidien import config, ia, planification
from quotidien.db import Base as BaseDonnees
from quotidien.systeme import Systeme

OK, ATTENTION, PROBLEME = "✅", "⚠️", "❌"
NOMS_TACHES = {"brief": "brief du matin", "rappels_veille": "rappels de la veille", "alerte_meteo": "alerte météo",
               "menu": "menu de la semaine"}  # fmt: skip


@dataclass
class Ligne:
    brique: str
    etat: str
    detail: str


def _depuis(secondes: float) -> str:
    if secondes < 120:
        return f"{int(secondes)} s"
    if secondes < 7200:
        return f"{int(secondes // 60)} min"
    if secondes < 172800:
        return f"{int(secondes // 3600)} h"
    return f"{int(secondes // 86400)} jours"


def _quand(t: float, fuseau: str, maintenant: float) -> str:
    d = datetime.fromtimestamp(t, ZoneInfo(fuseau))
    jour = d.date()
    auj = datetime.fromtimestamp(maintenant, ZoneInfo(fuseau)).date()
    if jour == auj:
        quand = "aujourd'hui"
    elif (jour - auj).days == 1:
        quand = "demain"
    else:
        from quotidien.repas.page import date_longue

        quand = date_longue(jour)
    return f"{quand} à {d.strftime('%H:%M')}"


def bilan(db: BaseDonnees, reglages: config.Reglages, systeme: Systeme, maintenant: float | None = None,
          contacts_statut: Callable[[], str] | None = None, agent: Callable[[], Any] | None = None,
          client: Callable[[], Any] | None = None) -> list[Ligne]:  # fmt: skip
    from quotidien import daemon, installation, rappels_apple
    from quotidien.anniversaires import contacts, proches

    t = maintenant or time.time()
    r = reglages.reglages
    fuseau = r["lieu"]["fuseau"]
    lignes: list[Ligne] = []

    # Démon
    lab = installation.label(r)
    etat = agent() if agent else installation.etat_agent(systeme, lab)
    battement = daemon.battement(db)
    if battement is not None and t - battement < 120:
        lignes.append(Ligne("Démon", OK, f"actif (battement il y a {_depuis(t - battement)})"
                                         + (f", {lab} pid {etat.pid}" if etat.pid else "")))  # fmt: skip
    elif etat.charge:
        lignes.append(Ligne("Démon", ATTENTION, f"{lab} chargé mais silencieux (dernier code : {etat.dernier_code})"))
    else:
        lignes.append(Ligne("Démon", PROBLEME, f"arrêté : relance ./install.sh (label {lab})"))

    # Réglages et base
    if reglages.avertissements:
        lignes.append(Ligne("Réglages", ATTENTION, " · ".join(reglages.avertissements[:3])))
    elif (config.dossier_support() / "profil.toml").exists():
        lignes.append(Ligne("Réglages", OK, f"{config.dossier_support() / 'profil.toml'}"))
    else:
        lignes.append(Ligne("Réglages", ATTENTION, "profil.toml absent : valeurs par défaut (relance ./install.sh)"))
    if db.corrompue_mise_de_cote is not None:
        lignes.append(Ligne("Base", ATTENTION, f"abîmée, mise de côté ({db.corrompue_mise_de_cote.name}) : neuve"))
    else:
        lignes.append(Ligne("Base", OK, str(db.chemin)))

    # Météo
    ligne = db.cx.execute("SELECT MAX(recu_le) FROM meteo_cache").fetchone()
    if ligne and ligne[0]:
        age = t - float(ligne[0])
        lignes.append(Ligne("Météo", OK if age < 86400 else ATTENTION, f"prévision Open-Meteo reçue il y a "
                                                                       f"{_depuis(age)}"))  # fmt: skip
    else:
        lignes.append(Ligne("Météo", ATTENTION, "aucune prévision reçue pour l'instant (hors ligne ?)"))

    # Menu
    from quotidien.repas import service

    debut = service.semaine_affichee(reglages, datetime.fromtimestamp(t, ZoneInfo(fuseau)).replace(tzinfo=None))
    menu = service.menu_de(db, debut)
    if menu is not None:
        lignes.append(Ligne("Menu", OK, f"semaine du {debut.isoformat()} ({len(menu.repas)} repas)"))
    else:
        lignes.append(Ligne("Menu", ATTENTION, f"pas encore de menu pour la semaine du {debut.isoformat()} "
                                               "(quotidien menu)"))  # fmt: skip

    # Contacts et proches
    statut = (contacts_statut or contacts.statut_mac)() if r["anniversaires"]["contacts"] else "desactive"
    fiches = proches.lire_fiches()
    texte = contacts.STATUTS.get(statut, "désactivés dans reglages.toml")
    lignes.append(Ligne("Contacts", OK if statut == "ok" else ATTENTION,
                        f"{texte} · proches.toml : {len(fiches.personnes)} fiche(s)"))  # fmt: skip

    # Rappels
    nos = rappels_apple.Rappels(db, systeme, r).nos_listes()
    if not r["rappels"]["active"]:
        lignes.append(Ligne("Rappels", ATTENTION, "désactivés dans reglages.toml (notifications seules)"))
    elif nos:
        lignes.append(Ligne("Rappels", OK, "nos listes : " + ", ".join(nos)))
    else:
        lignes.append(Ligne("Rappels", ATTENTION, "aucune liste créée pour l'instant (au premier menu ou "
                                                  "anniversaire ; accès à accepter une fois)"))  # fmt: skip

    # iCloud et raccourcis
    if config.icloud_drive().is_dir():
        from quotidien.raccourcis import generer

        poses = [n for n in generer.RACCOURCIS if (config.dossier_icloud() / f"{n}.shortcut").exists()]
        derniere = db.cx.execute("SELECT MAX(recue_le) FROM demandes").fetchone()
        detail = f"{config.dossier_icloud()} · raccourcis déposés : {len(poses)}/2"
        if derniere and derniere[0]:
            detail += f" · dernière demande il y a {_depuis(t - float(derniere[0]))}"
        lignes.append(Ligne("iCloud", OK if len(poses) == 2 else ATTENTION, detail))
    else:
        lignes.append(Ligne("iCloud", ATTENTION, "iCloud Drive introuvable : pas de raccourcis iPhone"))

    # IA
    budget = ia.Budget(db, r, lambda: t)
    choisi = client() if client else ia.choisir_client(r, systeme.trousseau_lire)
    qui = choisi.nom if choisi is not None else "aucune (repli local partout)"
    if not r["ia"]["active"]:
        qui = "désactivée dans reglages.toml"
    lignes.append(Ligne("IA", OK if choisi is not None else ATTENTION,
                        f"{qui} · ce mois : {budget.depense_du_mois():.2f} $ sur {budget.plafond:.2f} $"))  # fmt: skip

    # Tâches
    prochaines = planification.prochaines(db, r, t)
    for nom, libelle in NOMS_TACHES.items():
        derniere_fois = planification.derniere(db, nom)
        erreur = db.lire_meta(f"erreur:{nom}")
        if nom not in prochaines:
            detail = "prochaine : —"
        elif prochaines[nom] <= t:
            detail = "prochaine : maintenant (au prochain tour du démon)"
        else:
            detail = "prochaine : " + _quand(prochaines[nom], fuseau, t)
        if derniere_fois is not None:
            detail += f" · dernière : {_quand(derniere_fois[1], fuseau, t)}"
        etat_tache = OK
        if erreur:
            quand_erreur, _, genre = erreur.partition("|")
            if derniere_fois is None or float(quand_erreur) > derniere_fois[1]:
                etat_tache, detail = ATTENTION, detail + f" · dernier échec : {genre}"
        lignes.append(Ligne(f"Tâche : {libelle}", etat_tache, detail))
    return lignes


def texte(lignes: list[Ligne]) -> str:
    largeur = max(len(x.brique) for x in lignes)
    return "\n".join(f"{x.etat} {x.brique.ljust(largeur)}  {x.detail}" for x in lignes)


def aujourd_hui(maintenant: float, reglages: dict[str, Any]) -> date:
    return planification.aujourdhui(maintenant, reglages)
