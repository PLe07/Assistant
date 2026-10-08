"""Le juge principal (§9.1) : le vrai démon du tableau de bord face à 7 faux modules (vrais processus) et 1 absent.

Réglages resserrés pour tenir en quelques minutes (tour toutes les 10 s, confirmation et résolution 30 s, processeur
élevé sur 1 min, boucle sur 3 min, file bloquée après 1 min pour le module « File ») ; quota et silence de nuit levés
(ils ont leurs propres tests). Critères :
- chaque état détecté en moins de 2 minutes (à compter du moment où il commence) ;
- chaque alerte attendue émise une fois et une seule, et sa résolution une fois quand le module est réparé ;
- 0 alerte pour le module sain ; le module absent est ⚪ sans alerte ;
- lecture seule : espion d'audit dans le démon vide, `lsof` sans fichier des modules, code des modules identique
  (empreinte et date) avant et après, aucun « database is locked » vu par les modules (bases WAL, délai nul) ;
- nettoyage dans un `finally` : plus aucun processus, plus de bac à sable.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

import psutil
import pytest

from tableau import caviardage
from tests.faux_ecosysteme.harnais import Ecosysteme

pytestmark = pytest.mark.complet

ALERTES = {
    "tdbtest-boucle:boucle": "🔴 Boucle s'est arrêté",
    "tdbtest-file:file": "🟡 File : 3 documents attendent",
    "tdbtest-erreurs:pic_erreurs": "🟡 Erreurs écrit beaucoup d'erreurs : 30",
    "tdbtest-budget:budget80": "🟡 Budget a utilisé 85 %",
    "tdbtest-budget:budget100": "🔴 Budget a dépassé son budget Claude du mois (1,02 $",
    "tdbtest-attente:attente:brief": "🟡 Attente : « brief chaque jour vers",
    "tdbtest-processeur:cpu": "🟡 Processeur utilise beaucoup le processeur",
    "tdbtest-processeur:integrite": "⚠️ Le code de Processeur a changé : 1 fichier modifié.",
}
RESOLUTIONS = {
    "tdbtest-boucle:boucle": "✅ Boucle tourne de nouveau sans s'arrêter.",
    "tdbtest-file:file": "✅ File : la file",
    "tdbtest-attente:attente:brief": "✅ Attente : « brief chaque jour vers",
    "tdbtest-processeur:cpu": "✅ Processeur est revenu à un usage normal du processeur.",
    "tdbtest-processeur:integrite": "✅ Le code de Processeur est de nouveau celui de la référence.",
}
REGLAGES = {
    "intervalles": {"sante_s": 10},
    "alertes": {"confirmation_s": 30, "resolution_s": 30, "regroupement_s": 30},
    "seuils": {"cpu_eleve_min": 1, "boucle_fenetre_min": 3},
}


def cle_attendue(cle: str) -> str:
    """La clé d'une file porte le nom du dossier : on la ramène à « tdbtest-file:file »."""
    return "tdbtest-file:file" if cle.startswith("tdbtest-file:file") else cle


def compter(notifications: list[Any]) -> dict[str, int]:
    vus: dict[str, int] = {}
    for n in notifications:
        for cle in json.loads(n["cles"]):
            vus[cle_attendue(cle)] = vus.get(cle_attendue(cle), 0) + 1
    return vus


def lignes(notifications: list[Any]) -> list[str]:
    return [ligne for n in notifications for ligne in n["texte"].splitlines()]


def test_le_faux_ecosysteme(tmp_path: Path) -> None:
    eco = Ecosysteme(tmp_path / "eco", reglages=REGLAGES)
    eco.racine.mkdir()
    eco.preparer()
    code_avant = eco.empreintes_code()
    pids: list[int] = []
    debuts: dict[str, float] = {cle: 0.0 for cle in ALERTES}
    detections: dict[str, float] = {}
    jamais: set[str] = set()  # toutes les clés de problème vues pendant le test
    ouverts_lsof: list[str] = []
    injection = eco.dossier("processeur") / "code" / "injecte.py"
    try:
        eco.demarrer()
        t0 = eco.t0
        echeance = time.mktime(time.strptime(time.strftime("%Y-%m-%d ", time.localtime(t0)) + eco.heure_brief,
                                             "%Y-%m-%d %H:%M"))  # fmt: skip
        debuts["tdbtest-attente:attente:brief"] = echeance - t0
        etat_vert: dict[str, float] = {}
        # --- phase 1 : tout est détecté, puis chaque alerte part ------------------------------------------------
        fin = t0 + 300
        while time.time() < fin:
            time.sleep(2)
            ecoule = time.time() - t0
            if ecoule > 30 and not injection.exists():
                injection.write_text("print('ajouté par quelqu'un')\n", encoding="utf-8")
                debuts["tdbtest-processeur:integrite"] = ecoule
            ouverts = {cle_attendue(r["cle"]) for r in eco.problemes() if r["resolu_le"] is None}
            jamais |= {cle_attendue(r["cle"]) for r in eco.problemes()}
            for cle in ouverts & set(ALERTES):
                detections.setdefault(cle, ecoule)
            # 102 % seulement une fois l'alerte des 80 % partie (sinon elle serait remplacée avant d'être dite).
            if "tdbtest-budget:budget80" in compter(eco.notifications()) and not debuts["tdbtest-budget:budget100"]:
                (eco.dossier("budget") / "budget_cible").write_text("1.02", encoding="utf-8")
                debuts["tdbtest-budget:budget100"] = ecoule
            for ident, etat in eco.etats().items():
                attendu = {"tdbtest-sain": "vert", "tdbtest-absent": "gris"}.get(ident)
                if attendu and etat["pastille"] == attendu:
                    etat_vert.setdefault(ident, ecoule)
            if int(ecoule) % 20 < 2:
                ouverts_lsof += eco.ouverts_chez_les_modules()
            if set(ALERTES) <= set(compter(eco.notifications())):
                break
        delais = {cle: round(detections[cle] - debuts[cle], 1) for cle in detections}
        assert set(detections) == set(ALERTES), f"non détectés : {set(ALERTES) - set(detections)} ; vus : {delais}"
        assert all(0 <= d < 120 for d in delais.values()), delais
        assert etat_vert.get("tdbtest-sain", 999) < 120 and etat_vert.get("tdbtest-absent", 999) < 120
        absent = eco.etats()["tdbtest-absent"]
        assert absent["phrase"] == "Pas installé" and not absent["problemes"]
        notes = eco.notifications()
        assert compter(notes) == dict.fromkeys(ALERTES, 1), compter(notes)
        for cle, debut_message in ALERTES.items():
            assert sum(ligne.startswith(debut_message) for ligne in lignes(notes)) <= 1, cle
        # La page locale et l'instantané iPhone suivent.
        jeton = (eco.support / "jeton").read_text(encoding="utf-8").strip()
        port = int(eco.lire("SELECT valeur FROM meta WHERE cle = 'port'")[0]["valeur"])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/?t={jeton}", timeout=10) as r:
            page = r.read().decode()
        assert page.count('class="carte ') == 8 and 'data-module="tdbtest-boucle" data-pastille="rouge"' in page
        instantane = (eco.racine / "icloud" / "Tableau" / "Etat.html").read_text(encoding="utf-8")
        assert caviardage.contient_sensible(instantane, (jeton,)) == [] and "Boucle" in instantane
        # --- phase 2 : on répare, chaque résolution part une fois ---------------------------------------------
        for nom in ("boucle", "file", "attente", "processeur"):
            (eco.dossier(nom) / "comportement").write_text("sain", encoding="utf-8")
        injection.unlink()
        fin = time.time() + 360
        while time.time() < fin:
            time.sleep(3)
            jamais |= {cle_attendue(r["cle"]) for r in eco.problemes()}
            vus = compter(eco.notifications())
            if all(vus.get(cle) == 2 for cle in RESOLUTIONS):
                break
        notes = eco.notifications()
        attendu = {cle: 2 if cle in RESOLUTIONS else 1 for cle in ALERTES}
        assert compter(notes) == attendu, compter(notes)
        for cle, debut_message in RESOLUTIONS.items():
            assert sum(ligne.startswith(debut_message) for ligne in lignes(notes)) <= 1, cle
        # --- ce qui ne doit jamais arriver --------------------------------------------------------------------
        assert jamais == set(ALERTES), f"problèmes en trop : {jamais - set(ALERTES)}"
        assert not any(json.loads(n["cles"]) and "tdbtest-sain" in n["cles"] for n in notes)
        assert eco.espion.read_text(encoding="utf-8") == "", eco.espion.read_text(encoding="utf-8")[:2000]
        assert ouverts_lsof == [] and eco.ouverts_chez_les_modules() == []
        assert eco.verrous_vus_par_les_modules() == []
        assert eco.demon is not None and eco.demon.poll() is None  # le démon a tenu tout du long
        resume = {
            "detections_s": delais,
            "notifications": len(notes),
            "alertes": {cle: compter(notes)[cle] for cle in ALERTES},
            "duree_s": round(time.time() - t0),
            "espion": "vide",
            "lsof": "aucun fichier des modules",
            "verrous_vus_par_les_modules": 0,
        }
        sortie = os.environ.get("TDB_JUGE_SORTIE")
        if sortie:
            Path(sortie).write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        pids = eco.arreter()
    assert not injection.exists()
    assert eco.empreintes_code() == code_avant
    journal = (eco.maison / "Library" / "Logs" / "TableauDeBord" / "tableau.log").read_text(encoding="utf-8")
    assert "arrêté proprement" in journal and "Traceback" not in journal
    shutil.rmtree(eco.racine)
    assert not eco.racine.exists()
    restants = [p for p in pids if psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE]
    assert restants == []
