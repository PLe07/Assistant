"""Les analyses : textes, temps (veille, changement d'heure), attentes, santé, crédits, ressources."""

from __future__ import annotations

import io
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from tableau import config, planif, systeme, textes
from tableau.analyse import attentes, credits, credits_reels, ressources, sante
from tableau.db import Base
from tableau.module import (
    Attente,
    Credits,
    DefModule,
    EtatLaunchd,
    EtatModule,
    FileAttente,
    Observation,
    Pastille,
    StatsLogs,
    StatsProcessus,
)


@pytest.fixture
def base(tmp_path: Path) -> Base:
    return Base(tmp_path / "tableau.db")


@pytest.fixture
def reglages() -> config.Reglages:
    return config.charger(Path("/inexistant/reglages.toml"))


def local(annee: int, mois: int, jour: int, h: int, m: int = 0) -> float:
    return time.mktime((annee, mois, jour, h, m, 0, 0, 0, -1))


# --- textes ----------------------------------------------------------------------------------------------------------


def test_textes() -> None:
    assert [textes.duree(s) for s in (5, 300, 7200, 9000, 40000, 300000)] == ["5 s", "5 min", "2 h", "2 h 30", "11 h",
                                                                              "3 j"]  # fmt: skip
    m = local(2026, 10, 7, 10)
    assert textes.il_y_a(None, m) == "jamais" and textes.il_y_a(m - 10, m) == "à l'instant"
    assert textes.il_y_a(m - 7200, m) == "il y a 2 h"
    assert textes.quand(local(2026, 10, 7, 7, 15), m) == "aujourd'hui à 7h15"
    assert textes.quand(local(2026, 10, 8, 7, 15), m) == "demain à 7h15"
    assert textes.quand(local(2026, 10, 6, 21), m) == "hier à 21h00"
    assert textes.quand(local(2026, 10, 10, 9), m) == "samedi à 9h00"
    assert textes.quand(local(2026, 11, 20, 9), m) == "20/11 à 9h00"
    assert textes.heure_texte("07:15") == "7h15" and textes.heure_texte("bof") == "bof"
    assert textes.dollars(0.4075) == "0,41 $" and textes.dollars(None) == "inconnu"
    assert textes.pourcent(12.345, 1) == "12,3 %" and textes.pourcent(None) == "inconnu"
    assert textes.mo(300) == "300 Mo" and textes.mo(2048) == "2,0 Go" and textes.mo(None) == "inconnu"
    assert textes.pluriel(1, "fichier") == "1 fichier" and textes.pluriel(3, "fichier") == "3 fichiers"


# --- temps : échéances, changement d'heure, veille -------------------------------------------------------------------


def test_echeance_locale_et_changement_d_heure() -> None:
    # 25 octobre 2026 : passage à l'heure d'hiver (journée de 25 h) ; 29 mars 2026 : heure d'été (23 h).
    hiver = planif.echeance_locale(local(2026, 10, 25, 3), "07:15")
    assert time.localtime(hiver)[3:5] == (7, 15) and time.localtime(hiver).tm_isdst == 0
    veille = planif.echeance_locale(local(2026, 10, 25, 3), "07:15", -1)
    assert hiver - veille == 25 * 3600
    ete = planif.echeance_locale(local(2026, 3, 29, 12), "07:15")
    assert time.localtime(ete)[3:5] == (7, 15) and ete - planif.echeance_locale(ete, "07:15", -1) == 23 * 3600
    assert planif.debut_du_jour(local(2026, 10, 7, 15)) == local(2026, 10, 7, 0)


def test_veille_detectee_par_les_deux_horloges(base: Base) -> None:
    mur, mono = [1000.0], [50.0]
    h = planif.Horloge(base, mur=lambda: mur[0], mono=lambda: mono[0], intervalle_s=60)
    assert h.tour().reveil is None
    mur[0] += 60
    mono[0] += 60
    assert h.tour().reveil is None
    # Le Mac dort 8 h : l'horloge murale avance, la monotone presque pas.
    mur[0] += 8 * 3600
    mono[0] += 61
    t = h.tour()
    assert t.reveil == mur[0] and planif.veilles(base, 0) == [(1060.0, mur[0])]
    assert planif.dernier_reveil(base) == mur[0]
    assert planif.temps_eveille(base, 1000.0, mur[0] + 60) == pytest.approx(120.0)
    assert planif.temps_eveille(base, 10, 5) == 0
    # Un trou sans explication (démon figé) : noté pareil.
    mur[0] += 1000
    mono[0] += 1000
    assert h.tour().reveil is not None
    # Redémarrage du tableau de bord après une longue absence : le trou est noté au premier tour.
    h2 = planif.Horloge(base, mur=lambda: mur[0] + 3600, mono=lambda: 0.0, intervalle_s=60)
    assert h2.tour().reveil == mur[0] + 3600
    h3 = planif.Horloge(base, mur=lambda: mur[0] + 3630, mono=lambda: 0.0, intervalle_s=60)
    assert h3.tour().reveil is None


def test_echeancier() -> None:
    e = planif.Echeancier()
    assert e.du("x", 600, 1000) and not e.du("x", 600, 1300) and e.du("x", 600, 1600)
    assert e.du("x", 600, 100), "horloge reculée (changement d'heure manuel) : dû"
    e.forcer("x")
    assert e.du("x", 600, 101)


# --- attentes --------------------------------------------------------------------------------------------------------

BRIEF = Attente("brief", "quotidienne", "brief chaque jour vers 7h15", heure="07:15", tolerance_min=20)
GMAIL = Attente("gmail", "periodique", "relève Gmail toutes les 5 min", toutes_les_min=5, tolerance_min=15)


def test_attente_quotidienne(base: Base) -> None:
    premier = local(2026, 10, 1, 0)
    a = attentes.quotidienne
    # 7h20 : pas encore de brief, encore dans la tolérance.
    v = a(base, BRIEF, local(2026, 10, 6, 7, 15), local(2026, 10, 7, 7, 20), premier)
    assert v.statut == "en_attente" and v.prochaine == local(2026, 10, 8, 7, 15)
    # 7h36 sans brief : manquée.
    v = a(base, BRIEF, local(2026, 10, 6, 7, 15), local(2026, 10, 7, 7, 36), premier)
    assert v.statut == "manquee" and "7h15" in v.detail
    # Parti à 7h15 : tenue (et toute la journée).
    v = a(base, BRIEF, local(2026, 10, 7, 7, 15), local(2026, 10, 7, 23, 59), premier)
    assert v.statut == "tenue"
    # À 6h : on juge l'échéance d'hier.
    v = a(base, BRIEF, local(2026, 10, 6, 7, 16), local(2026, 10, 7, 6), premier)
    assert v.statut == "tenue" and v.echeance == local(2026, 10, 6, 7, 15)
    # Fait un peu en avance (7h00) : tenu ; fait la veille au soir : non.
    assert a(base, BRIEF, local(2026, 10, 7, 7, 0), local(2026, 10, 7, 9), premier).statut == "tenue"
    assert a(base, BRIEF, local(2026, 10, 6, 22), local(2026, 10, 7, 9), premier).statut == "manquee"
    # Installé à 15 h : le brief de 7h15 du jour n'est pas jugé.
    assert a(base, BRIEF, None, local(2026, 10, 7, 16), local(2026, 10, 7, 15)).statut == "en_attente"


def test_attente_rattrapee_au_reveil(base: Base) -> None:
    """Le Mac dormait de 23 h à 9 h : le brief n'est pas en retard tant qu'il n'a pas eu 20 min après le réveil."""
    planif.noter_veille(base, local(2026, 10, 6, 23), local(2026, 10, 7, 9))
    premier = local(2026, 10, 1, 0)
    assert attentes.quotidienne(base, BRIEF, None, local(2026, 10, 7, 9, 10), premier).statut == "en_attente"
    assert attentes.quotidienne(base, BRIEF, local(2026, 10, 7, 9, 2), local(2026, 10, 7, 9, 30), premier).statut == "tenue"
    assert attentes.quotidienne(base, BRIEF, None, local(2026, 10, 7, 9, 21), premier).statut == "manquee"


def test_attente_le_jour_du_changement_d_heure(base: Base) -> None:
    premier = local(2026, 10, 1, 0)
    fait = local(2026, 10, 25, 7, 15)
    assert attentes.quotidienne(base, BRIEF, fait, local(2026, 10, 25, 7, 20), premier).statut == "tenue"
    v = attentes.quotidienne(base, BRIEF, local(2026, 10, 24, 7, 15), local(2026, 10, 25, 7, 40), premier)
    assert v.statut == "manquee" and time.localtime(v.echeance)[3:5] == (7, 15)


def test_attente_periodique_en_temps_eveille(base: Base) -> None:
    premier = local(2026, 10, 1, 0)
    m = local(2026, 10, 7, 10)
    assert attentes.periodique(base, GMAIL, m - 300, m, premier).statut == "tenue"
    assert attentes.periodique(base, GMAIL, m - 21 * 60, m, premier).statut == "manquee"
    # Dernière relève à 22h, Mac endormi de 22h05 à 9h55 : à 10h, 10 min éveillées seulement.
    planif.noter_veille(base, local(2026, 10, 6, 22, 5), local(2026, 10, 7, 9, 55))
    assert attentes.periodique(base, GMAIL, local(2026, 10, 6, 22), m, premier).statut == "tenue"
    # Jamais vu : on laisse le temps au module.
    assert attentes.periodique(base, GMAIL, None, m, m - 60).statut == "en_attente"
    v = attentes.periodique(base, GMAIL, None, m, m - 3600)
    assert v.statut == "manquee" and "jamais vu" in v.detail


def test_evaluer_reglages_du_module_et_historique(base: Base) -> None:
    defn = DefModule(id="quotidien", nom="Quotidien", attentes=[BRIEF, GMAIL])
    obs = Observation(preuves={"brief": local(2026, 10, 7, 7, 31)})
    obs.reglages_attentes = {"brief": {"heure": "07:30"}, "gmail": {"actif": False}}
    m = local(2026, 10, 7, 10)
    base.ecrire_meta("premier_vu:quotidien", str(m - 30 * 86400))
    verdicts = attentes.evaluer(base, defn, obs, m)
    assert [v.statut for v in verdicts] == ["tenue", "inactive"]
    assert verdicts[0].attente.heure == "07:30"
    assert attentes.historique(base, "quotidien", 0)[0]["statut"] == "tenue"
    assert attentes.evaluer(base, defn, Observation(installe=False), m) == []
    assert attentes.evaluer(base, defn, Observation(actif=False), m) == []
    nouveau = DefModule(id="neuf", nom="Neuf", attentes=[BRIEF])
    assert attentes.evaluer(base, nouveau, Observation(), m)[0].statut == "en_attente"
    assert base.lire_meta("premier_vu:neuf") == str(m)
    obs2 = Observation(preuves={"gmail": m - 60})
    obs2.reglages_attentes = {"gmail": {"toutes_les_min": 10}}
    assert attentes.evaluer(base, DefModule(id="b", nom="B", attentes=[GMAIL]), obs2, m)[0].attente.toutes_les_min == 10


# --- santé -----------------------------------------------------------------------------------------------------------


def module_launchd(**k: Any) -> DefModule:
    return DefModule(id="bouclier", nom="Bouclier", labels=["com.x.bouclier"], aide="bouclier doctor", **k)


def en_marche(pid: int | None = 42, depuis: float | None = 3 * 86400) -> Observation:
    return Observation(
        launchd=[EtatLaunchd("com.x.bouclier", True, pid=pid, dernier_code=0, lancements=1)],
        processus=StatsProcessus([pid], 0.4, 60.0, depuis) if pid else None,
        logs=StatsLogs(),
    )


def test_tout_va_bien(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    obs = en_marche()
    obs.activite = ("dernière relève Gmail", horloge() - 120)
    e = sante.evaluer(module_launchd(), obs, [], base, reglages, horloge())
    assert e.pastille == Pastille.VERT and e.phrase == "Tourne depuis 3 j · dernière relève Gmail il y a 2 min"
    assert e.cpu_pct == 0.4 and e.rss_mo == 60 and e.problemes == []
    assert sante.evaluer(module_launchd(), Observation(launchd=[EtatLaunchd("com.x.bouclier", True, pid=1)]),
                         [], base, reglages, horloge()).phrase == "Tout va bien"  # fmt: skip


def test_pas_installe_eteint_inconnu(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    gris = sante.evaluer(module_launchd(attendu=True), Observation(installe=False), [], base, reglages, horloge())
    assert gris.pastille == Pastille.GRIS and gris.phrase == "Pas installé" and gris.problemes == []
    parti = sante.evaluer(module_launchd(), Observation(installe=False), [], base, reglages, horloge())
    assert "désinstallé" in parti.phrase
    eteint = Observation(actif=False, raison_inactif="éteint dans l'assistant")
    e = sante.evaluer(module_launchd(), eteint, [], base, reglages, horloge())
    assert e.pastille == Pastille.GRIS and e.phrase == "Éteint : éteint dans l'assistant" and e.problemes == []
    inconnu = Observation(inconnus=["launchd"])
    e = sante.evaluer(module_launchd(), inconnu, [], base, reglages, horloge())
    assert e.pastille == Pastille.JAUNE and "inconnu" in e.phrase and e.problemes == []


def test_arrete_et_boucle(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    m = horloge()
    arrete = sante.evaluer(module_launchd(), en_marche(pid=None), [], base, reglages, m)
    assert arrete.pastille == Pastille.ROUGE and [p.genre for p in arrete.problemes] == ["arrete"]
    assert "Tape « bouclier doctor »" in arrete.problemes[0].message
    absent = sante.evaluer(module_launchd(), Observation(), [], base, reglages, m)
    assert absent.problemes[0].genre == "arrete"
    base.plusieurs("INSERT INTO relances VALUES ('bouclier', ?)", [(m - i * 60,) for i in range(4)])
    boucle = sante.evaluer(module_launchd(), en_marche(pid=None), [], base, reglages, m)
    p = boucle.problemes[0]
    assert p.genre == "boucle" and "4 fois en 10 min" in p.message and not p.nuit_permise
    assert boucle.phrase == "Bouclier s'est arrêté 4 fois depuis ce matin"
    base.plusieurs("INSERT INTO relances VALUES ('bouclier', ?)", [(m - 1 - i,) for i in range(4)])
    assert sante.problemes(module_launchd(), en_marche(pid=None), [], base, reglages, m)[0].nuit_permise


def test_supervise_arrete(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    defn = DefModule(id="trieur", nom="Trieur", superviseur="trieur")
    obs = Observation(superviseur={"superviseur_en_marche": False, "statut": "actif"})
    p = sante.problemes(defn, obs, [], base, reglages, horloge())
    assert p[0].genre == "arrete" and "le superviseur de l'assistant ne tourne pas" in p[0].message
    obs = Observation(superviseur={"superviseur_en_marche": True, "statut": "relance"})
    assert sante.problemes(defn, obs, [], base, reglages, horloge())[0].genre == "arrete"
    obs = Observation(superviseur={"superviseur_en_marche": True, "statut": None})
    assert sante.problemes(defn, obs, [], base, reglages, horloge()) == []
    obs = Observation(superviseur={"superviseur_en_marche": True, "statut": "actif"},
                      processus=StatsProcessus([1], 1.0, 30.0, 100))  # fmt: skip
    assert sante.problemes(defn, obs, [], base, reglages, horloge()) == []


def test_fige_en_temps_eveille(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    m = horloge()
    obs = en_marche()
    obs.battement_ts, obs.battement_periode_s = m - 600, 30.0
    p = sante.problemes(module_launchd(), obs, [], base, reglages, m)
    assert [x.genre for x in p] == ["fige"] and "10 min" in p[0].message
    planif.noter_veille(base, m - 590, m - 5)
    assert sante.problemes(module_launchd(), obs, [], base, reglages, m) == []


def test_files_attentes_erreurs_budget_donnees_cpu_integrite(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    m = horloge()
    obs = en_marche()
    obs.files = [FileAttente("iCloud/BoiteMac", 2, 45 * 60), FileAttente("documents en attente", 1, 16 * 60, seuil_min=15),
                 FileAttente("ok", 1, 10 * 60), FileAttente("vide", 0, 0)]  # fmt: skip
    obs.logs = StatsLogs(erreurs_1h=12, erreurs_24h=30)
    obs.technique["moyenne_erreurs_horaire_7j"] = 1.5
    obs.credits = Credits(1.7, 2.0)
    v = attentes.Verdict(BRIEF, "manquee", detail="pas fait (attendu vers 7h15)")
    v2 = attentes.Verdict(GMAIL, "manquee", detail="aucun passage depuis 40 min")
    from tableau.sondes import tailles as t

    t.noter(base, "bouclier", m - 8 * 86400, 100 * 1024 * 1024, 0)
    t.noter(base, "bouclier", m, 200 * 1024 * 1024, 0)
    base.plusieurs("INSERT INTO echantillons VALUES ('bouclier', ?, 'vert', 80, 10, 0, 0, 0)", [(m - i * 60,) for i in range(8)])
    p = sante.problemes(module_launchd(), obs, [v, v2], base, reglages, m, {"ecarts": [{"chemin": "a.py"}, {"chemin": "b"}]})
    genres = [(x.genre, x.sous_cle) for x in p]
    assert genres == [("attente", "brief"), ("attente", "gmail"), ("file", "iCloud/BoiteMac"),
                      ("file", "documents en attente"), ("pic_erreurs", ""), ("budget80", ""), ("donnees", ""),
                      ("cpu", ""), ("integrite", "")]  # fmt: skip
    texte = {x.genre + x.sous_cle: x.message for x in p}
    assert "2 documents attendent depuis 45 min dans « iCloud/BoiteMac »" in texte["fileiCloud/BoiteMac"]
    assert "attendu vers 7h15" in texte["attentebrief"] and "aucun passage depuis 40 min" in texte["attentegmail"]
    assert "12 dans la dernière heure (d'habitude 1,5 par heure)" in texte["pic_erreurs"]
    assert "85 %" in texte["budget80"] and "1,70 $ sur 2,00 $" in texte["budget80"]
    assert "+100 % en une semaine" in texte["donnees"]
    assert "2 fichiers modifiés. C'était voulu ?" in texte["integrite"]
    e = sante.evaluer(module_launchd(), obs, [v, v2], base, reglages, m)
    assert e.pastille == Pastille.JAUNE and "autres choses" in e.phrase
    obs.credits = Credits(2.05, 2.0)
    budget = [x for x in sante.problemes(module_launchd(), obs, [], base, reglages, m) if x.genre.startswith("budget")]
    assert [x.genre for x in budget] == ["budget100"] and budget[0].gravite == "grave"
    # Habituel : 12 erreurs/h quand la moyenne est 10/h n'est pas un pic.
    obs.technique["moyenne_erreurs_horaire_7j"] = 10.0
    assert not any(x.genre == "pic_erreurs" for x in sante.problemes(module_launchd(), obs, [], base, reglages, m))


def test_n8n_et_agent_periodique(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    n8n = DefModule(id="n8n", nom="n8n", adaptateur="n8n", conteneur="n8n", aide="docker ps")
    eteint = Observation(n8n={"docker": False, "etat": "docker éteint", "repond": False})
    p = sante.problemes(n8n, eteint, [], base, reglages, horloge())
    assert p[0].genre == "n8n" and "Docker est éteint" in p[0].message
    sourd = Observation(n8n={"docker": True, "etat": "running", "repond": False, "healthz": "HTTP 503"})
    assert "ne répond pas (HTTP 503)" in sante.problemes(n8n, sourd, [], base, reglages, horloge())[0].message
    arrete = Observation(n8n={"docker": True, "etat": "exited", "repond": False})
    assert "« exited »" in sante.problemes(n8n, arrete, [], base, reglages, horloge())[0].message
    ok = Observation(n8n={"docker": True, "etat": "running", "repond": True})
    assert sante.problemes(n8n, ok, [], base, reglages, horloge()) == []
    tache = DefModule(id="t", nom="Tâche", labels=["com.x.t"], doit_tourner=False)
    obs = Observation(launchd=[EtatLaunchd("com.x.t", True, pid=None, dernier_code=2)])
    p = sante.problemes(tache, obs, [], base, reglages, horloge())
    assert [x.genre for x in p] == ["echec"] and "code 2" in p[0].message


def test_prochaine_tache_et_details(base: Base, reglages: config.Reglages) -> None:
    m = local(2026, 10, 7, 10)
    defn = DefModule(id="q", nom="Quotidien", labels=["com.x.q"], attentes=[BRIEF])
    obs = Observation(launchd=[EtatLaunchd("com.x.q", True, pid=1)], preuves={"brief": local(2026, 10, 7, 7, 15)})
    obs.credits = Credits(0.5, 2.0, detail="x")
    obs.logs = StatsLogs(erreurs_24h=3, derniere_erreur="boum", derniere_erreur_ts=m - 5, derniere_ligne_ts=m - 30)
    obs.tailles = (10, 20)
    v = attentes.evaluer(base, defn, obs, m)
    e = sante.evaluer(defn, obs, v, base, reglages, m)
    assert e.prochaine == "brief demain à 7h15" and e.erreurs_24h == 3
    assert e.derniere_activite == "dernière ligne de journal à l'instant"
    assert e.technique["derniere_erreur"] == "boum" and e.technique["tailles"] == {"donnees": 10, "journaux": 20}
    assert e.credits_mois == 0.5 and e.projection_usd is not None


# --- crédits ---------------------------------------------------------------------------------------------------------


def test_tarifs_et_estimation() -> None:
    assert credits.tarif("haiku") == (0.10, 0.50) and credits.tarif("sonnet") == (2.0, 10.0)
    assert credits.tarif("claude-haiku-4-5-20251001") == (1.0, 5.0)
    assert credits.tarif("Claude Opus") == (4.0, 20.0) and credits.tarif("") is None and credits.tarif("gpt") is None
    total, inconnus = credits.estimer({"sonnet": (1_000_000, 100_000), "mystere": (5, 5)})
    assert total == pytest.approx(3.0) and inconnus == ["mystere"]
    assert credits.estimer({"mystere": (1, 1)}) == (None, ["mystere"])
    assert credits.estimer({}) == (0.0, [])


def test_projection() -> None:
    p = credits.projeter(1.0, 2.0, local(2026, 10, 11, 0))
    assert p.projection_usd == pytest.approx(1.0 / 10 * 31) and p.pct == 50
    assert credits.projeter(1.0, None, local(2026, 10, 2, 12)).projection_usd is None


def test_noter_et_synthese(base: Base) -> None:
    m = local(2026, 10, 7, 10)
    base.executer("INSERT INTO credits VALUES ('trieur', '2026-09', 0.80, 1.0, 0)")
    etats = [
        EtatModule("trieur", "Trieur", "🗂", Pastille.VERT, "", credits_mois=0.12, plafond_usd=1.0),
        EtatModule("bouclier", "Bouclier", "🛡️", Pastille.VERT, "", credits_mois=0.40, plafond_usd=2.0),
        EtatModule("assistant", "Assistant", "🤖", Pastille.VERT, "", credits_mois=0.41,
                   technique={"credits_source": "estimation", "credits_detail": "2 appels"}),  # fmt: skip
        EtatModule("n8n", "n8n", "🔗", Pastille.VERT, ""),
    ]
    credits.noter(base, etats, m)
    assert base.valeur("SELECT COUNT(*) FROM credits WHERE mois = '2026-10'") == 3
    s = credits.synthese(base, etats, m, reel_usd=0.6)
    assert s["total_usd"] == pytest.approx(0.52) and s["plafonds_usd"] == 3.0
    assert s["abonnement_equivalent_usd"] == pytest.approx(0.41) and s["reel_usd"] == 0.6
    assert s["mois_precedent_usd"] == pytest.approx(0.80) and [x["id"] for x in s["modules"]] == ["assistant",
                                                                                                   "bouclier", "trieur"]  # fmt: skip
    assert credits.mois_precedent(local(2026, 1, 5, 0)) == "2025-12"
    assert credits.synthese(base, [], m)["mois_precedent_usd"] is None


class FausseReponse(io.BytesIO):
    def __enter__(self) -> FausseReponse:
        return self

    def __exit__(self, *a: object) -> None:
        self.close()


def test_cout_reel_admin_api() -> None:
    pages = [
        {"data": [{"results": [{"amount": "123.45", "currency": "USD"}, {"amount": "x"}]}, "pas une case"],
         "has_more": True, "next_page": "page_2"},
        {"data": [{"results": [{"amount": "76.55"}]}], "has_more": False, "next_page": None},
    ]  # fmt: skip
    vues: list[urllib.request.Request] = []

    def ouvrir(requete: urllib.request.Request, delai: float) -> FausseReponse:
        vues.append(requete)
        return FausseReponse(json.dumps(pages[len(vues) - 1]).encode())

    total = credits_reels.cout_du_mois("sk-ant-admin01-x", local(2026, 10, 7, 10), ouvrir)
    assert total == pytest.approx(2.0)
    assert vues[0].full_url.startswith("https://api.anthropic.com/v1/organizations/cost_report?starting_at=2026-10-01T00")
    assert "limit=31" in vues[0].full_url and "page=page_2" in vues[1].full_url
    assert vues[0].get_header("X-api-key") == "sk-ant-admin01-x"
    assert vues[0].get_header("Anthropic-version") == "2023-06-01"

    def panne(requete: urllib.request.Request, delai: float) -> FausseReponse:
        raise OSError("réseau")

    with pytest.raises(credits_reels.CoutReelIndisponible):
        credits_reels.cout_du_mois("k", local(2026, 10, 7, 10), panne)
    monkey = credits_reels.URL
    credits_reels.URL = "https://evil.example/v1/x"
    try:
        with pytest.raises(credits_reels.CoutReelIndisponible, match="refusée"):
            credits_reels.cout_du_mois("k", local(2026, 10, 7, 10), ouvrir)
    finally:
        credits_reels.URL = monkey


def test_cle_admin_dans_le_trousseau() -> None:
    def trousseau(sortie: str, code: int = 0) -> Any:
        def executer(args: list[str]) -> systeme.Resultat:
            systeme.verifier(args)
            return systeme.Resultat(code, sortie)

        return executer

    assert credits_reels.lire_cle(trousseau("sk-ant-admin01-abc\n")) == "sk-ant-admin01-abc"
    assert credits_reels.lire_cle(trousseau("", 44)) is None
    assert credits_reels.lire_cle(trousseau("pas une clé")) is None


# --- ressources ------------------------------------------------------------------------------------------------------


def test_ressources_en_une_phrase(base: Base, reglages: config.Reglages, horloge: Any) -> None:
    etats = [
        EtatModule("trieur", "Trieur", "🗂", Pastille.VERT, "", cpu_pct=0.3, rss_mo=120),
        EtatModule("bouclier", "Bouclier", "🛡️", Pastille.VERT, "", cpu_pct=0.2, rss_mo=60),
        EtatModule("ambiance", "Ambiance", "🎶", Pastille.GRIS, ""),
    ]
    b = ressources.bilan(etats, {"cpu_pct": 50.0, "memoire_totale_mo": 8192.0}, reglages)
    assert b.cpu_pct == pytest.approx(0.5) and b.rss_mo == 180 and b.part_cpu_mac == pytest.approx(1.0)
    assert b.phrase.startswith("Non : tes modules utilisent 0,5 % d'un cœur et 180 Mo")
    assert b.minutes_batterie_jour == pytest.approx(0.5 / 100 * 2.5 * 8 / 4.5 * 60)
    gros = [EtatModule("corvees", "Corvées", "🔁", Pastille.VERT, "", cpu_pct=8.0, rss_mo=300)]
    assert ressources.bilan(gros, None, reglages).phrase.startswith("Un peu") and "surtout Corvées" in (
        ressources.bilan(gros, None, reglages).phrase)  # fmt: skip
    enorme = [EtatModule("x", "X", "", Pastille.VERT, "", cpu_pct=60.0, rss_mo=10)]
    assert ressources.bilan(enorme, {"cpu_pct": 0.0}, reglages).phrase.startswith("Oui")
    base.plusieurs("INSERT INTO echantillons VALUES ('trieur', ?, 'vert', ?, 100, 0, 0, 0)",
                   [(horloge() - 60, 1.0), (horloge() - 120, 3.0)])  # fmt: skip
    moy = ressources.moyennes(base, horloge() - 3600)
    assert moy["trieur"] == (pytest.approx(2.0), pytest.approx(100.0))
    assert ressources.bilan(etats, None, reglages, moy).par_module[0]["cpu_pct"] == pytest.approx(2.0)
    assert ressources._minutes(90) == "1 h 30"
