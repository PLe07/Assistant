"""Le démon de bout en bout, avec une horloge simulée sur plusieurs jours : un seul brief par jour (jamais à 15 h),
le menu du dimanche et sa liste dans Rappels, les rappels de la veille, les anniversaires une seule fois, l'entrée
iCloud des raccourcis, aucune notification la nuit, rien de refait après un redémarrage."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quotidien import config, daemon, planification, reseau
from quotidien.db import Base as BaseDonnees
from tests.faux_mac import FauxMac
from tests.meteo import fabrique

PARIS = ZoneInfo("Europe/Paris")
CONTACTS = [{"identifiant": "1", "prenom": "Léa", "nom": "Exemple", "jour": 14, "mois": 10, "annee": 2001,
             "telephones": [("mobile", "06 11 22 33 44")]}]  # fmt: skip


def t(jour: int, heure: int, minute: int = 0, mois: int = 10) -> float:
    return datetime(2026, mois, jour, heure, minute, tzinfo=PARIS).timestamp()


class Horloge:
    def __init__(self, debut: float) -> None:
        self.maintenant = debut

    def __call__(self) -> float:
        return self.maintenant


class OpenMeteo:
    def __init__(self) -> None:
        self.appels = 0

    def __call__(self, url: str, **_: Any) -> reseau.Reponse:
        reseau.verifier_url(url)
        self.appels += 1
        return reseau.Reponse(200, json.dumps(fabrique.reponse(date(2026, 10, 10), jours=10)).encode(), url)


@pytest.fixture
def monde(maison: Path) -> Any:
    config.icloud_drive().mkdir(parents=True)
    horloge = Horloge(t(11, 6, 0))
    mac = FauxMac({"Travail": ["rapport"]})
    composants = daemon.Composants(telecharger=OpenMeteo(), fournisseur_contacts=lambda: ("ok", CONTACTS))

    def nouveau_demon() -> daemon.Demon:
        return daemon.Demon(BaseDonnees(config.chemin_base()), mac.systeme(), horloge, composants)

    return horloge, mac, nouveau_demon


def _vivre(d: daemon.Demon, horloge: Horloge, jusqu_a: float, pas_minutes: int = 15) -> list[tuple[float, str]]:
    fait: list[tuple[float, str]] = []
    while horloge.maintenant <= jusqu_a:
        tour = d.tour()
        assert not tour.erreurs, tour.erreurs
        fait += [(horloge.maintenant, f) for f in tour.fait]
        horloge.maintenant += pas_minutes * 60
    return fait


def _heure(x: float) -> str:
    return datetime.fromtimestamp(x, PARIS).strftime("%a %d %H:%M")


def test_une_semaine_de_demon(monde: Any) -> None:
    horloge, mac, nouveau_demon = monde
    d = nouveau_demon()
    fait = _vivre(d, horloge, t(15, 23, 0))
    briefs = [_heure(x) for x, f in fait if f.startswith("brief")]
    assert briefs == ["Sun 11 07:15", "Mon 12 07:15", "Tue 13 07:15", "Wed 14 07:15", "Thu 15 07:15"]
    menus = [(_heure(x), f) for x, f in fait if f.startswith("menu")]
    assert menus == [("Sun 11 17:00", "menu : semaine du 2026-10-12")]
    assert [_heure(x) for x, f in fait if f.startswith("rappels de la veille")] == [
        "Sun 11 20:00", "Mon 12 20:00", "Tue 13 20:00", "Wed 14 20:00", "Thu 15 20:00"]  # fmt: skip
    assert len([f for _, f in fait if f.startswith("alerte météo")]) == 5
    # Anniversaire de Léa (ami sans fiche : pas de J-7) : la veille à 19 h 30, le jour J à 9 h.
    titres = [titre for titre, _ in mac.notifications]
    assert titres.count("🎂 Demain") == 1 and titres.count("🎂 Aujourd'hui") == 1
    assert titres.count("☀️ Ma journée") == 5 and titres.count("🍽️ Menu de la semaine prêt") == 1
    # Aucune notification entre 23 h et 7 h.
    db = d.db
    for quand, envoyee in db.lignes("SELECT date, envoyee FROM notifications"):
        heure = datetime.fromtimestamp(quand, PARIS).hour
        assert not envoyee or 7 <= heure < 23
    # Rappels : la liste de courses de la semaine et l'anniversaire, dans NOS listes ; « Travail » intacte.
    assert mac.etat_listes()["Travail"] == 1
    assert len(mac.listes["Courses (menu)"]) > 10
    (anniv,) = mac.listes["Anniversaires"]
    assert anniv["titre"] == "🎂 Anniversaire de Léa (25 ans)" and anniv["date"] == (2026, 10, 14, 9, 0)
    assert "Exemple" not in anniv["note"] and "1. " in anniv["note"]
    # La page « Ma journée » est dans iCloud ; le brief du jour mentionnait le menu.
    page = config.dossier_icloud() / "Ma journée.html"
    assert page.exists() and "Jeudi 15 octobre" in page.read_text(encoding="utf-8")
    assert "🍽️ Ce soir" in (db.lire_meta("brief:dernier") or "")
    # Redémarrage du démon (launchd après un kill) : rien n'est refait.
    horloge.maintenant = t(15, 21, 30)
    avant = len(mac.notifications)
    d2 = nouveau_demon()
    assert d2.tour().fait == [] and len(mac.notifications) == avant


def test_mac_endormi_rattrape_seulement_ce_qui_sert(monde: Any) -> None:
    horloge, mac, nouveau_demon = monde
    horloge.maintenant = t(12, 15, 0)  # réveil à 15 h : pas de brief du matin
    d = nouveau_demon()
    fait = [f for f in d.tour().fait]
    assert not any(f.startswith("brief") for f in fait)
    assert planification.dues(d.db, d.reglages().reglages, horloge.maintenant) == []
    horloge.maintenant = t(13, 8, 40)  # réveil à 8 h 40 : le brief de 7 h 15 est rattrapé, une fois
    assert any(f.startswith("brief") for f in d.tour().fait)
    assert not any(f.startswith("brief") for f in d.tour().fait)
    horloge.maintenant = t(19, 9, 0)  # le lundi matin, le menu du dimanche (manqué) sert encore
    fait = d.tour().fait
    assert "menu : semaine du 2026-10-19" in fait
    horloge.maintenant = t(26, 21, 0)  # lundi soir 21 h : trop tard pour le menu de la veille
    assert not any(f.startswith("menu") for f in d.tour().fait)


def test_entree_icloud_des_raccourcis(monde: Any) -> None:
    horloge, mac, nouveau_demon = monde
    horloge.maintenant = time.time()  # les fichiers déposés ont l'heure réelle
    d = nouveau_demon()
    entree = config.dossier_icloud_raccourcis() / "entree"
    entree.mkdir(parents=True)
    (entree / "frigo-20261011-120000-1234.txt").write_text("2 courgettes, feta, 4 oeufs", encoding="utf-8")
    (entree / "envie-20261011-120001-5678.txt").write_text("mexicain et léger", encoding="utf-8")
    (entree / "frigo-verification-1760000000.txt").write_text("poireaux", encoding="utf-8")
    for f in entree.iterdir():
        os.utime(f, (horloge.maintenant - 10, horloge.maintenant - 10))
    assert "iCloud : 3 demande(s) des raccourcis" in d.tour_rapide().fait
    reponses = config.dossier_icloud_raccourcis() / "reponses"
    frigo = (reponses / "frigo-20261011-120000-1234.txt").read_text(encoding="utf-8")
    assert frigo.startswith("🧊 J'ai compris : 2 courgettes, feta, 4 œufs.") and "1. " in frigo
    assert "ce-soir" not in frigo  # la réponse courte, pour l'écran de l'iPhone
    assert (reponses / "envie-20261011-120001-5678.txt").read_text(encoding="utf-8").startswith("✅ Envie notée")
    frigo_memoire = {r[0] for r in d.db.lignes("SELECT ingredient FROM frigo")}
    assert frigo_memoire == {"courgette", "feta", "oeuf"}  # la vérification de l'installation n'y entre pas
    assert list(entree.iterdir()) == []


def test_brique_en_panne_le_reste_continue(monde: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    horloge, mac, nouveau_demon = monde
    horloge.maintenant = t(11, 20, 5)  # dimanche soir : le menu (17 h) et les rappels de la veille (20 h) sont dus
    d = nouveau_demon()

    def casse(*_: Any, **__: Any) -> Any:
        raise RuntimeError("panne")

    from quotidien.repas import service

    monkeypatch.setattr(service, "produire", casse)
    tour = d.tour_lent()
    assert tour.erreurs == ["menu : RuntimeError"]
    assert any(f.startswith("rappels de la veille") for f in tour.fait)  # la panne du menu n'arrête pas le reste
    assert (d.db.lire_meta("erreur:menu") or "").endswith("|RuntimeError")
    monkeypatch.undo()
    horloge.maintenant += 60
    assert "menu : semaine du 2026-10-12" in d.tour_lent().fait  # retentée au tour suivant


def test_reglages_relus_quand_ils_changent(monde: Any) -> None:
    horloge, mac, nouveau_demon = monde
    d = nouveau_demon()
    assert d.reglages()["horaires"]["brief"] == "07:15"
    config.dossier_support().mkdir(parents=True, exist_ok=True)
    (config.dossier_support() / "reglages.toml").write_text('[horaires]\nbrief = "06:45"\n', encoding="utf-8")
    assert d.reglages()["horaires"]["brief"] == "06:45"
    horloge.maintenant = t(12, 7, 5)  # 6 h 45 tombe dans le silence : repoussé à 7 h (et non 7 h 15)
    assert any(f.startswith("brief") for f in d.tour().fait)


def test_le_fil_des_taches_ne_part_que_s_il_y_a_a_faire(monde: Any) -> None:
    horloge, mac, nouveau_demon = monde
    d = nouveau_demon()
    assert d.a_faire()  # premier tour : anniversaires et ménage jamais faits
    d.tour()
    assert not d.a_faire()  # 6 h : rien jusqu'à 7 h 15
    horloge.maintenant = t(11, 7, 15)
    assert d.a_faire()


def test_boucle_et_battement(monde: Any) -> None:
    import threading

    horloge, mac, nouveau_demon = monde
    d = nouveau_demon()
    arret = threading.Event()
    d.reveil.set()
    assert d.lancer(arret, max_tours=2) == 2
    assert daemon.battement(d.db) == horloge.maintenant


def test_le_demon_demande_l_acces_aux_contacts_une_seule_fois(maison: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quotidien.anniversaires import contacts

    demandes: list[float] = []
    monkeypatch.setattr(contacts, "statut_mac", lambda: "non_demande")
    monkeypatch.setattr(contacts, "demander_acces", lambda delai=120: demandes.append(delai) or "refuse")
    monkeypatch.setattr(contacts, "contacts_du_mac", lambda: ("refuse", []))
    d = daemon.Demon(BaseDonnees(config.chemin_base()), FauxMac().systeme(), lambda: t(11, 9, 0))
    d.annuaire(d.reglages())  # une commande lancée dans le Terminal : jamais de demande ici
    assert demandes == []
    d.par_launchd = True
    d._annuaire = None
    d.annuaire(d.reglages())
    d._annuaire = None
    d.annuaire(d.reglages())
    assert demandes == [120] and d.db.lire_meta("contacts:demande_faite")
