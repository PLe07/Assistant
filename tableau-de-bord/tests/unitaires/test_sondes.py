"""Les sondes : launchd, processus, journaux, files d'attente, Docker et n8n, tailles."""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tableau import systeme
from tableau.db import Base
from tableau.sondes import docker_n8n, files_attente, launchd, logs, processus, tailles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def base(tmp_path: Path) -> Base:
    return Base(tmp_path / "tableau.db")


class FausseCommande:
    """Répond aux commandes de la liste blanche avec des sorties préparées, et note chaque appel."""

    def __init__(self, reponses: dict[tuple[str, ...], systeme.Resultat]) -> None:
        self.reponses = reponses
        self.appels: list[tuple[str, ...]] = []

    def __call__(self, args: list[str]) -> systeme.Resultat:
        systeme.verifier(args)  # même en test, rien hors liste blanche
        self.appels.append(tuple(args))
        for cle, r in self.reponses.items():
            if tuple(args[: len(cle)]) == cle:
                return r
        return systeme.Resultat(1, "", "inconnu")


# --- launchd -------------------------------------------------------------------------------------------------------


def test_lire_liste() -> None:
    liste = launchd.lire_liste((FIXTURES / "launchd" / "list.txt").read_text() + "mal formée\n\t\t\n1\tx\t\n")
    assert liste["com.exemple.bouclier"] == launchd.LigneListe(4242, 0)
    assert liste["com.exemple.quotidien"] == launchd.LigneListe(None, 1)
    assert liste["com.exemple.ambiance.audio"] == launchd.LigneListe(None, -9)
    assert len(liste) == 5
    assert launchd.lire_liste("PID\tStatus\tLabel\n12\t?\tcom.x\n")["com.x"].statut is None


def test_lire_print() -> None:
    e = launchd.lire_print("com.exemple.bouclier", (FIXTURES / "launchd" / "print_en_marche.txt").read_text())
    assert (e.etat, e.pid, e.lancements, e.dernier_code) == ("running", 4242, 1, None)
    assert e.programme and e.programme.endswith("/python")
    a = launchd.lire_print("com.exemple.quotidien", (FIXTURES / "launchd" / "print_arrete.txt").read_text())
    assert (a.etat, a.pid, a.lancements, a.dernier_code) == ("not running", None, 7, 1)
    vide = launchd.lire_print("x", "n'importe quoi")
    assert vide.charge and vide.pid is None and vide.lancements is None


def test_sonde_launchd_n_appelle_print_que_si_besoin(horloge: Any) -> None:
    liste = (FIXTURES / "launchd" / "list.txt").read_text()
    faux = FausseCommande(
        {
            ("launchctl", "list"): systeme.Resultat(0, liste),
            ("launchctl", "print", "gui/501/com.exemple.bouclier"): systeme.Resultat(
                0, (FIXTURES / "launchd" / "print_en_marche.txt").read_text()
            ),
        }
    )
    s = launchd.SondeLaunchd(faux, uid=501, horloge=horloge)
    e = s.etat("com.exemple.bouclier")
    assert e is not None and e.pid == 4242 and e.lancements == 1 and e.etat == "running"
    absent = s.etat("com.exemple.absent")
    assert absent is not None and absent.charge is False
    # Sans print qui réponde : on garde ce que dit list.
    q = s.etat("com.exemple.quotidien")
    assert q is not None and q.dernier_code == 1 and q.lancements is None
    assert faux.appels.count(("launchctl", "list")) == 1  # un seul list par tour
    s.nouveau_tour()
    horloge.avancer(60)
    s.etat("com.exemple.bouclier")
    prints = [a for a in faux.appels if a[:3] == ("launchctl", "print", "gui/501/com.exemple.bouclier")]
    assert len(prints) == 1, "rien n'a changé : pas de nouveau print"
    s.nouveau_tour()
    horloge.avancer(600)
    s.etat("com.exemple.bouclier")
    prints = [a for a in faux.appels if a[:3] == ("launchctl", "print", "gui/501/com.exemple.bouclier")]
    assert len(prints) == 2, "10 minutes : un print de rafraîchissement"
    # Le processus change : print aussitôt.
    faux.reponses[("launchctl", "list")] = systeme.Resultat(0, "PID\tStatus\tLabel\n999\t0\tcom.exemple.bouclier\n")
    s.nouveau_tour()
    e2 = s.etat("com.exemple.bouclier")
    assert e2 is not None and e2.pid == 999
    assert len([a for a in faux.appels if a[:2] == ("launchctl", "print")]) == 4
    # Arrêté d'après list alors que print (ancien) disait « running ».
    faux.reponses[("launchctl", "list")] = systeme.Resultat(0, "PID\tStatus\tLabel\n-\t1\tcom.exemple.bouclier\n")
    faux.reponses.pop(("launchctl", "print", "gui/501/com.exemple.bouclier"))
    s.nouveau_tour()
    e3 = s.etat("com.exemple.bouclier")
    assert e3 is not None and e3.pid is None and e3.etat == "not running" and e3.dernier_code == 1


def test_sonde_launchd_absent() -> None:
    s = launchd.SondeLaunchd(FausseCommande({}), uid=501)
    assert s.etat("com.x") is None and s.erreur
    assert s.liste() is None


# --- processus -----------------------------------------------------------------------------------------------------

BRULEUR = textwrap.dedent(
    """
    import os, subprocess, sys, time
    fils = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    fin = time.time() + float(sys.argv[1])
    while time.time() < fin:
        sum(i * i for i in range(20000))
    time.sleep(30)
    """
)


def test_processus_mesure_l_arbre_et_le_processeur(tmp_path: Path) -> None:
    p = subprocess.Popen([sys.executable, "-c", BRULEUR, "1.5"])
    try:
        time.sleep(0.4)
        sonde = processus.SondeProcessus()
        premiere = sonde.mesurer("bruleur", [p.pid])
        assert premiere is not None and premiere.cpu_pct is None and len(premiere.pids) == 2
        assert premiere.rss_mo > 1 and premiere.depuis_s is not None and premiere.depuis_s < 30
        time.sleep(1.0)
        deuxieme = sonde.mesurer("bruleur", [p.pid])
        assert deuxieme is not None and deuxieme.cpu_pct is not None and deuxieme.cpu_pct > 30
        assert sonde.mesurer("bruleur", [p.pid]).cpu_pct is None  # type: ignore[union-attr]  # trop rapproché
    finally:
        p.kill()
        p.wait()
    assert sonde.mesurer("bruleur", [p.pid]) is None
    assert sonde.mesurer("rien", [2**22 + 12345]) is None
    sonde.oublier("bruleur")


def test_fils_du_superviseur(tmp_path: Path) -> None:
    (tmp_path / "modules" / "trieur").mkdir(parents=True)
    (tmp_path / "modules" / "__init__.py").write_text("")
    (tmp_path / "modules" / "trieur" / "__init__.py").write_text("")
    (tmp_path / "modules" / "trieur" / "__main__.py").write_text("import time\ntime.sleep(30)\n")
    superviseur = subprocess.Popen(
        [sys.executable, "-c", "import subprocess, sys, time\n"
         "a = subprocess.Popen([sys.executable, '-m', 'modules.trieur'])\n"
         "b = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
         "time.sleep(30)\n"],
        cwd=tmp_path,
    )  # fmt: skip
    try:
        for _ in range(50):
            fils = processus.fils_du_superviseur(superviseur.pid)
            if fils:
                break
            time.sleep(0.1)
        assert list(fils) == ["trieur"] and len(fils["trieur"]) == 1
    finally:
        superviseur.kill()
        superviseur.wait()
    assert processus.fils_du_superviseur(2**22 + 999) == {}


def test_charge_du_mac_et_moi() -> None:
    c = processus.charge_du_mac()
    assert c["coeurs"] >= 1 and c["memoire_totale_mo"] > c["memoire_utilisee_mo"] > 0
    m = processus.moi()
    assert m["rss_mo"] > 5 and m["cpu_s"] > 0


# --- journaux ------------------------------------------------------------------------------------------------------


def test_analyser_les_formats_connus() -> None:
    texte = textwrap.dedent(
        """\
        2026-10-07 10:00:00 INFO    [trieur] facture.pdf → Factures/2026 (facture_achat, 0.86)
        2026-10-07 10:00:01 WARNING [superviseur] Module « trieur » tombé (code 1) : x · relance dans 60 s
        2026-10-07 10:00:02 ERROR   [trieur] Plantage : boum
        Traceback (most recent call last):
          File "x.py", line 1, in <module>
        ValueError: boum
        2026-10-07 10:00:03,123 ERROR [daemon] relève Gmail impossible
        2026-10-07 10:00:04,999 WARNING brief en retard
        2026-10-07T10:00:05Z CRITICAL disque plein
        2026-10-07 10:00:06 tout va bien
        2026-10-07 10:00:07 une Exception: inattendue sans niveau
        Traceback (most recent call last):
          File "y.py", line 2, in f
        KeyError: 'cle'
        suite du message daté
        """
    )
    lignes = logs.analyser(texte)
    niveaux = [(lg.niveau, lg.composant) for lg in lignes]
    assert niveaux[:3] == [("info", "trieur"), ("avertissement", "superviseur"), ("erreur", "trieur")]
    assert lignes[2].message == "Plantage : boum", "la pile d'appels est rattachée, pas recomptée"
    assert (lignes[3].niveau, lignes[3].composant) == ("erreur", "daemon")
    assert (lignes[4].niveau, lignes[4].message) == ("avertissement", "brief en retard")
    assert lignes[5].niveau == "erreur" and lignes[6].niveau == "info" and lignes[7].niveau == "erreur"
    assert lignes[7].message == "une Exception: inattendue sans niveau" and len(lignes) == 8
    assert lignes[0].ts == pytest.approx(1791360000.0)
    # Une sortie d'erreur brute (demon.erreurs.log) : des piles seules et des lignes libres.
    brute = logs.analyser(
        "Traceback (most recent call last):\n  File \"y.py\", line 2, in f\nKeyError: 'cle'\n"
        "ligne libre sans date\nErreur: autre ligne libre\nTraceback (most recent call last):\n"
    )
    assert [(lg.niveau, lg.message) for lg in brute] == [
        ("erreur", "KeyError: 'cle'"),
        ("info", "ligne libre sans date"),
        ("erreur", "Erreur: autre ligne libre"),
        ("erreur", "Traceback (most recent call last):"),
    ]
    assert all(lg.ts is None for lg in brute)


def test_analyser_l_echantillon_reel_de_l_assistant() -> None:
    texte = (FIXTURES / "reelles" / "conteneur" / "assistant-assistant.log").read_text()
    lignes = logs.analyser(texte)
    attendues = {
        "erreur": texte.count(" ERROR "),
        "avertissement": texte.count(" WARNING "),
    }
    assert sum(1 for lg in lignes if lg.niveau == "erreur") == attendues["erreur"] > 0
    assert sum(1 for lg in lignes if lg.niveau == "avertissement") == attendues["avertissement"] > 0
    assert all(lg.ts is not None for lg in lignes)
    assert {lg.composant for lg in lignes} >= {"trieur"}


def test_lecteur_reprend_la_ou_il_s_etait_arrete(tmp_path: Path, base: Base, horloge: Any) -> None:
    f = tmp_path / "x.log"
    f.write_text("2026-10-07 10:00:00 ERROR [a] un\n2026-10-07 10:00:01 INFO [a] deux\n")
    lecteur = logs.LecteurJournaux(base, horloge)
    assert [lg.message for lg in lecteur.nouvelles_lignes(f)] == ["un", "deux"]
    assert lecteur.nouvelles_lignes(f) == lecteur.nouvelles_lignes(f)  # une seule lecture par tour
    lecteur.nouveau_tour()
    assert lecteur.nouvelles_lignes(f) == []
    with open(f, "a") as sortie:
        sortie.write("2026-10-07 10:00:02 WARNING [a] trois\n2026-10-07 10:00:03 ERROR [a] incomplè")
    lecteur.nouveau_tour()
    assert [lg.message for lg in lecteur.nouvelles_lignes(f)] == ["trois"], "la ligne incomplète attend"
    # Un nouveau lecteur (redémarrage du tableau de bord) reprend au même endroit.
    autre = logs.LecteurJournaux(base, horloge)
    with open(f, "a") as sortie:
        sortie.write("te\n")
    assert [lg.message for lg in autre.nouvelles_lignes(f)] == ["incomplète"]
    autre.nouveau_tour()
    assert autre.nouvelles_lignes(tmp_path / "absent.log") == []


def test_lecteur_rotation_troncature_reecriture(tmp_path: Path, base: Base, horloge: Any) -> None:
    f = tmp_path / "assistant.log"
    f.write_text("2026-10-07 10:00:00 INFO [a] " + "x" * 300 + "\n")
    lecteur = logs.LecteurJournaux(base, horloge)
    assert len(lecteur.nouvelles_lignes(f)) == 1
    # Rotation : la fin de l'ancien fichier est lue sous son nouveau nom, puis le nouveau depuis le début.
    with open(f, "a") as sortie:
        sortie.write("2026-10-07 10:00:01 ERROR [a] fin de l'ancien\n")
    f.rename(tmp_path / "assistant.log.1")
    f.write_text("2026-10-07 10:00:02 ERROR [a] début du nouveau\n")
    lecteur.nouveau_tour()
    assert [lg.message for lg in lecteur.nouvelles_lignes(f)] == ["fin de l'ancien", "début du nouveau"]
    # Troncature.
    f.write_text("")
    lecteur.nouveau_tour()
    assert lecteur.nouvelles_lignes(f) == []
    f.write_text("2026-10-07 10:00:03 ERROR [a] après troncature\n")
    lecteur.nouveau_tour()
    assert [lg.message for lg in lecteur.nouvelles_lignes(f)] == ["après troncature"]
    # Réécrit sous le même numéro de fichier, plus long qu'avant : la tête a changé, relu depuis le début.
    contenu = "2026-10-07 10:00:04 ERROR [a] réécrit " + "y" * 300 + "\n"
    with open(f, "r+") as sortie:
        sortie.write(contenu)
    lecteur.nouveau_tour()
    assert [lg.message[:7] for lg in lecteur.nouvelles_lignes(f)] == ["réécrit"]
    # Rotation sans ancien fichier retrouvable.
    f.unlink()
    f.write_text("2026-10-07 10:00:05 INFO [a] tout neuf\n")
    lecteur.nouveau_tour()
    assert [lg.message for lg in lecteur.nouvelles_lignes(f)] == ["tout neuf"]


def test_premiere_lecture_limitee_a_la_fin(tmp_path: Path, base: Base, horloge: Any) -> None:
    f = tmp_path / "gros.log"
    ligne = "2026-10-07 10:00:00 ERROR [a] " + "z" * 90 + "\n"
    f.write_text(ligne * 5000)  # ~600 Ko
    lues = logs.LecteurJournaux(base, horloge).nouvelles_lignes(f)
    assert 2000 < len(lues) < 2700 and all(lg.message.startswith("zzz") for lg in lues)


def test_compter_et_statistiques(base: Base, horloge: Any) -> None:
    m = horloge()
    lignes = [
        logs.Ligne(m - 60, "erreur", "a", "envoi à jean@example.org refusé"),
        logs.Ligne(m - 120, "avertissement", "a", "lent"),
        logs.Ligne(m - 5 * 3600, "erreur", "a", "ancienne"),
        logs.Ligne(m - 40 * 86400, "erreur", "a", "trop vieille"),
        logs.Ligne(None, "erreur", "a", "sans date"),
        logs.Ligne(m + 3600, "erreur", "a", "dans le futur (horloge)"),
        logs.Ligne(m, "info", "a", "rien"),
    ]
    logs.compter(base, "trieur", lignes, m)
    logs.compter(base, "trieur", [logs.Ligne(m - 30, "erreur", "a", "encore")], m)
    s = logs.statistiques(base, "trieur", m)
    assert s["erreurs_1h"] == 4 and s["erreurs_24h"] == 5 and s["avert_1h"] == 1
    assert s["derniere_erreur"] in ("sans date", "dans le futur (horloge)")
    assert "jean" not in json.dumps(logs.dernieres_erreurs(base, "trieur"))
    vide = logs.statistiques(base, "autre", m)
    assert vide["erreurs_24h"] == 0 and vide["derniere_erreur"] is None and vide["moyenne_horaire_7j"] == 0
    for i in range(60):
        base.executer("INSERT INTO dernieres_erreurs VALUES ('x', ?, 'm')", (float(i),))
    logs.nettoyer_dernieres_erreurs(base, "x", garder=10)
    assert base.valeur("SELECT COUNT(*) FROM dernieres_erreurs WHERE module = 'x'") == 10


# --- files d'attente -----------------------------------------------------------------------------------------------


def test_file_d_attente(tmp_path: Path, base: Base, horloge: Any) -> None:
    boite = tmp_path / "BoiteMac"
    assert files_attente.mesurer(boite, base, horloge()) is None
    boite.mkdir()
    (boite / "Raccourcis").mkdir()
    for nom in ("Mon coffre.html", "Derniers classements.html", ".DS_Store", "~$brouillon.docx", "x.tmp",
                "Facture (Trieur).html", ".cache"):  # fmt: skip
        (boite / nom).write_text("x")
    vide = files_attente.mesurer(boite, base, horloge())
    assert vide is not None and vide.n == 0 and vide.plus_vieux_s == 0
    # Arrivé pendant qu'on regarde : l'âge part de « vu la première fois », pas de sa date de modification.
    (boite / "facture.pdf").write_text("x")
    os.utime(boite / "facture.pdf", (1, 1))
    (boite / ".releve.pdf.icloud").write_text("x")
    horloge.avancer(60)
    f = files_attente.mesurer(boite, base, horloge(), "BoiteMac (iPhone)")
    assert f is not None and f.n == 2 and f.pas_encore_telecharges == 1 and f.plus_vieux_s == 0
    assert f.nom == "BoiteMac (iPhone)"
    horloge.avancer(40 * 60)
    f = files_attente.mesurer(boite, base, horloge())
    assert f is not None and f.plus_vieux_s == 40 * 60
    # Parti puis revenu : repart de zéro.
    (boite / "facture.pdf").unlink()
    (boite / ".releve.pdf.icloud").unlink()
    files_attente.mesurer(boite, base, horloge())
    (boite / "facture.pdf").write_text("x")
    horloge.avancer(60)
    f = files_attente.mesurer(boite, base, horloge())
    assert f is not None and f.n == 1 and f.plus_vieux_s == 0


def test_file_deja_pleine_au_premier_regard(tmp_path: Path, base: Base) -> None:
    entree = tmp_path / "entree"
    entree.mkdir()
    (entree / "vieux.txt").write_text("x")
    maintenant = time.time() + 3600
    f = files_attente.mesurer(entree, base, maintenant)
    assert f is not None and f.n == 1 and 3500 < f.plus_vieux_s < 3700
    f = files_attente.mesurer(entree, base, maintenant + 60)
    assert f is not None and 3560 < f.plus_vieux_s < 3760


# --- Docker et n8n -------------------------------------------------------------------------------------------------


def test_docker_eteint() -> None:
    faux = FausseCommande({("docker", "ps"): systeme.Resultat(1, "", "Cannot connect to the Docker daemon at x\n")})
    e = docker_n8n.SondeDocker(faux).etat(["n8n"])
    assert not e.disponible and e.erreur and e.erreur.startswith("Cannot connect")
    assert docker_n8n.SondeDocker(FausseCommande({("docker", "ps"): systeme.Resultat(127, "", "")})).etat([]).erreur


def test_docker_n8n_en_marche(horloge: Any) -> None:
    ps = json.dumps({"Names": "n8n", "Image": "n8nio/n8n:1.80", "State": "running"}) + "\npas du json\n[1]\n"
    inspect = json.dumps(
        [{"State": {"Status": "running", "Health": {"Status": "healthy"}, "StartedAt": "2026-10-07T08:00:00Z"},
          "RestartCount": 2}]
    )  # fmt: skip
    stats = json.dumps({"CPUPerc": "1.50%", "MemUsage": "180.5MiB / 7.6GiB"})
    faux = FausseCommande(
        {
            ("docker", "ps"): systeme.Resultat(0, ps),
            ("docker", "inspect"): systeme.Resultat(0, inspect),
            ("docker", "stats"): systeme.Resultat(0, stats),
        }
    )
    sonde = docker_n8n.SondeDocker(faux, horloge=horloge)
    e = sonde.etat(["n8n", "absent"])
    c = e.conteneurs["n8n"]
    assert e.disponible and list(e.conteneurs) == ["n8n"]
    assert (c.etat, c.sante, c.relances, c.cpu_pct) == ("running", "healthy", 2, 1.5)
    assert c.memoire_mo == pytest.approx(180.5)
    sonde.etat(["n8n"])
    assert sum(1 for a in faux.appels if a[1] == "stats") == 1, "docker stats au plus toutes les 10 min"
    horloge.avancer(601)
    faux.reponses[("docker", "stats")] = systeme.Resultat(0, json.dumps({"CPUPerc": "?", "MemUsage": "beaucoup"}))
    c2 = sonde.etat(["n8n"]).conteneurs["n8n"]
    assert c2.cpu_pct is None and c2.memoire_mo is None
    faux.reponses[("docker", "inspect")] = systeme.Resultat(0, "pas du json")
    faux.reponses[("docker", "ps")] = systeme.Resultat(0, json.dumps({"Names": "n8n", "State": "exited"}))
    c3 = sonde.etat(["n8n"]).conteneurs["n8n"]
    assert c3.etat == "exited" and c3.cpu_pct is None
    faux.reponses[("docker", "inspect")] = systeme.Resultat(1, "", "")
    assert sonde.etat(["n8n"]).conteneurs["n8n"].relances is None
    assert docker_n8n._mo("1.5GiB") == pytest.approx(1536) and docker_n8n._mo("512kB") == pytest.approx(0.5)


class _Gestionnaire(http.server.BaseHTTPRequestHandler):
    code = 200

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(self.code)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args: Any) -> None:
        pass


def test_healthz_ok_erreur_injoignable() -> None:
    serveur = http.server.HTTPServer(("127.0.0.1", 0), _Gestionnaire)
    t = threading.Thread(target=serveur.serve_forever, daemon=True)
    t.start()
    try:
        ok, detail = docker_n8n.healthz(serveur.server_address[1])
        assert ok and "200" in detail
        _Gestionnaire.code = 503
        ok, detail = docker_n8n.healthz(serveur.server_address[1])
        assert not ok and "503" in detail
    finally:
        _Gestionnaire.code = 200
        serveur.shutdown()
        serveur.server_close()
    ok, detail = docker_n8n.healthz(serveur.server_address[1], delai=0.5)
    assert not ok and "injoignable" in detail


# --- tailles -------------------------------------------------------------------------------------------------------


def test_tailles_et_croissance(tmp_path: Path, base: Base, horloge: Any) -> None:
    d = tmp_path / "donnees"
    (d / "sous").mkdir(parents=True)
    (d / "a.db").write_bytes(b"x" * 1000)
    (d / "sous" / "b").write_bytes(b"x" * 500)
    (d / "lien").symlink_to(tmp_path)
    (tmp_path / "seul.log").write_bytes(b"x" * 10)
    (d / "exclu").mkdir()
    (d / "exclu" / "gros").write_bytes(b"x" * 9999)
    assert tailles.taille([d], exclure=[d / "exclu"]) == 1500
    assert tailles.taille([d, tmp_path / "seul.log", tmp_path / "absent"], exclure=[d / "exclu"]) == 1510
    assert tailles.taille([tmp_path / "absent"]) is None
    m = horloge()
    assert tailles.croissance_semaine(base, "trieur", m) == (None, None)
    tailles.noter(base, "trieur", m - 8 * 86400, 1000, 0)
    tailles.noter(base, "trieur", m, 1600, 200)
    assert tailles.croissance_semaine(base, "trieur", m) == (1800, pytest.approx(80.0))
    tailles.noter(base, "neuf", m, 10, None)
    assert tailles.croissance_semaine(base, "neuf", m) == (10, None)
