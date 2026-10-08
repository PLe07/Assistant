"""Le rapport de la semaine (§6) : échéance du dimanche 20 h, rattrapage au réveil, une seule fois ; ce qui a tourné,
ce qui a coincé, les crédits et leur tendance, l'intégrité ; une page autonome, sans fuite. Et la base : migration
des colonnes, agrégats par jours entiers, état relu après un redémarrage."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import time
from pathlib import Path

import pytest

from tableau import config
from tableau.analyse import rapport_semaine as rs
from tableau.analyse.alertes import Alertes
from tableau.db import Base
from tableau.module import EtatModule, Pastille, Probleme
from tableau.notifier import NotificateurMemoire


def local(annee: int, mois: int, jour: int, h: int, m: int = 0) -> float:
    return time.mktime((annee, mois, jour, h, m, 0, 0, 0, -1))


def d20() -> float:
    """Dimanche 11 octobre 2026, 20 h à Paris (calculé après que le fuseau des tests est posé)."""
    return local(2026, 10, 11, 20)


@pytest.fixture
def base(tmp_path: Path) -> Base:
    return Base(tmp_path / "t.db")


@pytest.fixture
def reglages() -> config.Reglages:
    return config.charger(Path("/nulle/part.toml"))


def etats() -> list[EtatModule]:
    return [
        EtatModule("bouclier", "Bouclier", "🛡️", Pastille.VERT, "", credits_mois=0.80, plafond_usd=2.0),
        EtatModule("trieur", "Trieur <script>", "🗂️", Pastille.JAUNE, "", credits_mois=0.30, plafond_usd=1.0),
        EtatModule("corvees", "Corvées", "🧹", Pastille.GRIS, "Éteint"),
    ]


def test_echeance_du_dimanche() -> None:
    assert rs.echeance(local(2026, 10, 11, 20, 5), 6, "20:00") == d20()
    assert rs.echeance(local(2026, 10, 11, 19, 59), 6, "20:00") == local(2026, 10, 4, 20)
    assert rs.echeance(local(2026, 10, 14, 9), 6, "20:00") == d20()
    assert rs.echeance(local(2026, 10, 12, 8), 0, "07:30") == local(2026, 10, 12, 7, 30)
    assert rs.echeance(local(2026, 10, 12, 7), 0, "07:30") == local(2026, 10, 5, 7, 30)
    # Le dimanche du passage à l'heure d'hiver : toujours 20 h à l'horloge.
    assert time.localtime(rs.echeance(local(2026, 10, 25, 21), 6, "20:00"))[3:5] == (20, 0)


def test_du_une_fois_avec_rattrapage(base: Base, reglages: config.Reglages) -> None:
    base.ecrire_meta("premier_tour", str(local(2026, 10, 11, 9)))
    assert rs.du(base, reglages, d20() + 60) is None  # observé moins d'un jour : pas de rapport
    base.ecrire_meta("premier_tour", str(local(2026, 10, 9, 9)))
    assert rs.du(base, reglages, d20() - 60) is None
    # Le Mac dormait à 20 h : fait au réveil, lundi matin.
    assert rs.du(base, reglages, local(2026, 10, 12, 8, 30)) == d20()
    base.ecrire_meta("rapport_fait", str(d20()))
    assert rs.du(base, reglages, local(2026, 10, 12, 8, 31)) is None
    assert rs.du(base, reglages, local(2026, 10, 18, 20, 1)) == local(2026, 10, 18, 20)


def remplir(base: Base) -> None:
    debut = d20() - 7 * 86400
    # Bouclier : vert tout le temps observé ; Trieur : 3 tours sur 4 verts ; Corvées : éteint.
    base.plusieurs(
        "INSERT INTO echantillons VALUES (?, ?, ?, 1, 10, 0, 0, 0)",
        [("bouclier", d20() - 3600 * i, "vert") for i in range(1, 5)]
        + [("trieur", d20() - 3600 * i, p) for i, p in enumerate(["vert", "vert", "rouge", "vert"], 1)]
        + [("corvees", d20() - 3600, "gris")],
    )
    base.executer(
        "INSERT INTO agregats (periode, debut, module, n, vert, jaune, rouge, gris) VALUES ('h', ?, 'trieur', 60, "
        "30, 0, 14, 16)",
        (debut + 86400,),
    )
    base.executer(
        "INSERT INTO agregats (periode, debut, module, n, vert) VALUES ('h', ?, 'trieur', 60, 60)", (debut - 3600,)
    )
    base.plusieurs(
        "INSERT INTO attentes VALUES (?, ?, ?, ?, ?, '')",
        [("trieur", "brief", debut + 86400 * i, "tenue" if i != 3 else "manquee", 0) for i in range(1, 7)],
    )


def test_construire_et_page(base: Base, reglages: config.Reglages, tmp_path: Path) -> None:
    remplir(base)
    # Dans l'ordre : un souci d'avant la semaine encore ouvert, un réglé dans la semaine, un toujours en cours.
    a = Alertes(base, reglages, NotificateurMemoire())
    vieux = Probleme("bouclier", "integrite", "attention", "⚠️ Le code de Bouclier a changé.", "✅")
    for i in range(3):
        a.suivre([vieux], ["bouclier"], d20() - 9 * 86400 + 60 * i)
    t = d20() - 3 * 86400
    p = Probleme("trieur", "file", "attention", "🟡 Trieur : 2 documents attendent depuis 45 min.", "✅", sous_cle="x")
    for i in range(3):
        a.suivre([p, vieux], ["trieur", "bouclier"], t + 60 * i)
    for i in range(3, 8):
        a.suivre([vieux], ["trieur", "bouclier"], t + 60 * i)
    q = Probleme("bouclier", "boucle", "grave", "🔴 Bouclier s'est arrêté 5 fois.", "✅")
    for i in range(3):
        a.suivre([q, vieux], ["bouclier"], d20() - 3600 + 60 * i)
    # Intégrité : Bouclier a du code changé, le Trieur une référence acceptée.
    base.executer("INSERT INTO integrite_etat (module, ecarts) VALUES ('bouclier', ?)", (json.dumps([{"c": 1}] * 2),))
    base.executer("INSERT INTO integrite_etat (module, ecarts) VALUES ('trieur', '[]')")
    base.executer("INSERT INTO integrite_etat (module, ecarts) VALUES ('nettoyeur', 'abîmé')")
    base.noter_evenement(d20() - 86400, "trieur", "reference", "info", "Nouvelle référence")
    # Crédits : 0,50 $ au rapport précédent (même mois), 0,40 $ la semaine d'avant.
    base.ecrire_meta("rapport_credits", json.dumps({"mois": "2026-10", "total": 0.5}))
    base.ecrire_meta("rapport_credits_semaine", "0.4")
    r = rs.construire(base, etats(), d20())
    lignes = {m.id: m for m in r.modules}
    assert lignes["bouclier"].part_vert == 1.0 and lignes["corvees"].part_vert is None
    assert lignes["trieur"].part_vert == pytest.approx((3 + 30) / (4 + 44))  # l'agrégat d'avant la semaine exclu
    assert (lignes["trieur"].tenues, lignes["trieur"].manquees) == (5, 1)
    assert [(s["module"], bool(s["regle_le"])) for s in r.soucis] == [
        ("bouclier", False), ("trieur", True), ("bouclier", False),
    ]  # fmt: skip
    assert r.credits_semaine == pytest.approx(0.6) and r.tendance == "en hausse"
    assert [(i["module"], i["fichiers"], i["acceptees"]) for i in r.integrite] == [("bouclier", 2, 0), ("trieur", 0, 1)]
    assert r.resume == (
        "📊 Ta semaine : 1 module sur 2 ont bien tourné, 3 soucis (1 réglé), 1,10 $ de crédits ce mois-ci, "
        "code changé : Bouclier."
    )
    chemin = rs.ecrire(r, tmp_path / "rapports")
    assert chemin.name == "semaine-2026-10-11.html" and stat.S_IMODE(chemin.stat().st_mode) == 0o600
    page = chemin.read_text(encoding="utf-8")
    assert "Trieur &lt;script&gt;" in page and "<script" not in page
    assert not re.search(r"(src|href)=|https?://|@import|url\(", page)  # autonome : aucune ressource extérieure
    assert "/Users/" not in page and str(tmp_path) not in page
    for titre in ("Ce qui a tourné", "Ce qui a coincé", "Crédits Claude", "Intégrité"):
        assert titre in page
    assert "toujours en cours" in page and "nouvelle référence acceptée" in page
    assert "prefers-color-scheme: dark" in page and 'name="viewport"' in page


def test_credits_semaine_et_tendance(base: Base) -> None:
    assert rs._credits_semaine(base, 1.0, "2026-10") is None  # premier rapport
    base.ecrire_meta("rapport_credits", "abîmé")
    assert rs._credits_semaine(base, 1.0, "2026-10") is None
    # Changement de mois : la fin de septembre plus le début d'octobre.
    base.ecrire_meta("rapport_credits", json.dumps({"mois": "2026-09", "total": 2.0}))
    base.executer("INSERT INTO credits VALUES ('bouclier', '2026-09', 2.5, 2.0, 0)")
    assert rs._credits_semaine(base, 0.25, "2026-10") == pytest.approx(0.75)
    assert rs._tendance(None, 1.0) is None and rs._tendance(1.0, None) is None
    assert rs._tendance(0.0, 0.01) == "stable" and rs._tendance(1.0, 1.1) == "stable"
    assert rs._tendance(0.5, 1.0) == "en baisse" and rs._tendance(2.0, 1.0) == "en hausse"


def test_semaine_calme(base: Base, tmp_path: Path) -> None:
    r = rs.construire(base, [EtatModule("bouclier", "Bouclier", "🛡️", Pastille.VERT, "")], d20())
    assert r.resume == "📊 Ta semaine : aucun souci, 0,00 $ de crédits ce mois-ci."
    page = rs.en_html(r)
    assert "Rien : tout a tourné." in page and "Aucun code changé." in page and "inconnu (premier rapport)" in page
    assert "pas observé" in page


def test_faire_si_du_puis_nettoyer(base: Base, reglages: config.Reglages, tmp_path: Path) -> None:
    dossier = tmp_path / "rapports"
    base.ecrire_meta("premier_tour", str(local(2026, 10, 5, 9)))  # le dimanche 4 n'a pas été observé
    assert rs.faire_si_du(base, reglages, etats(), dossier, d20() - 60) is None
    r = rs.faire_si_du(base, reglages, etats(), dossier, d20() + 120)
    assert r is not None and r.chemin is not None and r.chemin.exists()
    assert rs.faire_si_du(base, reglages, etats(), dossier, d20() + 180) is None
    assert json.loads(base.lire_meta("rapport_credits") or "") == {"mois": "2026-10", "total": pytest.approx(1.1)}
    assert [e["genre"] for e in base.evenements(0)] == ["rapport"]
    vieux = dossier / "semaine-2026-06-01.html"
    vieux.write_text("x")
    os.utime(vieux, (d20() - 100 * 86400, d20() - 100 * 86400))
    (dossier / "autre.txt").write_text("pas à nous")
    assert rs.nettoyer(dossier, d20()) == 1 and not vieux.exists() and (dossier / "autre.txt").exists()
    assert rs.dernier(dossier) == r.chemin and rs.dernier(tmp_path / "vide") is None
    # La semaine suivante : la dépense de la semaine est calculée et gardée.
    r2 = rs.faire_si_du(base, reglages, etats(), dossier, local(2026, 10, 18, 20, 1))
    assert r2 is not None and r2.credits_semaine == pytest.approx(0.0)
    assert base.lire_meta("rapport_credits_semaine") == "0.0"


def test_etat_relu_depuis_la_base(base: Base) -> None:
    e = EtatModule("trieur", "Trieur", "🗂️", Pastille.ROUGE, "Arrêté", cpu_pct=1.5,
                   problemes=[Probleme("trieur", "arrete", "grave", "🔴", "✅", nuit_permise=True)])  # fmt: skip
    base.ecrire_etat_module("trieur", e.en_dict(), 1.0)
    relu = EtatModule.depuis_dict(base.etats_modules()["trieur"])
    assert relu == e
    abime = EtatModule.depuis_dict({"pastille": "violet", "problemes": [{"genre": "x"}, "n'importe"], "autre": 1})
    assert abime.pastille == Pastille.GRIS and abime.problemes == [] and abime.id == "?" and abime.nom == "?"


def test_migration_des_colonnes(tmp_path: Path) -> None:
    """Une base de la première version (sans confirme_le ni phrase) est complétée sans rien perdre."""
    chemin = tmp_path / "ancienne.db"
    db = sqlite3.connect(chemin)
    db.execute(
        "CREATE TABLE problemes (cle TEXT PRIMARY KEY, module TEXT NOT NULL, genre TEXT NOT NULL, gravite TEXT NOT "
        "NULL, message TEXT NOT NULL, resolution TEXT NOT NULL DEFAULT '', nuit_permise INTEGER NOT NULL DEFAULT 0, "
        "ouvert_le REAL NOT NULL, vu_le REAL NOT NULL, observations INTEGER NOT NULL DEFAULT 1, absent_depuis REAL, "
        "notifie_le REAL, rappel_le REAL, resolu_le REAL, resolution_envoyee INTEGER NOT NULL DEFAULT 0)"
    )
    db.execute("INSERT INTO problemes (cle, module, genre, gravite, message, ouvert_le, vu_le) VALUES "
               "('a:b', 'a', 'b', 'grave', 'm', 1, 1)")  # fmt: skip
    db.commit()
    db.close()
    base = Base(chemin)
    r = base.ligne("SELECT cle, confirme_le, phrase FROM problemes")
    assert r is not None and tuple(r) == ("a:b", None, "")


def test_agregats_par_jours_entiers(base: Base) -> None:
    """Les heures d'un jour passent ensemble dans son agrégat journalier, même si l'entretien tombe en plein jour."""
    jour = 86400 * 20000  # un jour UTC entier
    base.plusieurs(
        "INSERT INTO agregats (periode, debut, module, n, cpu_moy, rss_moy, vert) VALUES ('h', ?, 'm', 1, 1, 1, 1)",
        [(jour + 3600 * h,) for h in range(24)],
    )
    base.entretenir(jour + 90 * 86400 + 12 * 3600)  # midi, 90 jours après : le jour n'est pas encore entier
    assert base.valeur("SELECT COUNT(*) FROM agregats WHERE periode = 'h'") == 24
    base.entretenir(jour + 91 * 86400 + 3600)
    assert base.valeur("SELECT COUNT(*) FROM agregats WHERE periode = 'h'") == 0
    assert base.valeur("SELECT n FROM agregats WHERE periode = 'j'") == 24
