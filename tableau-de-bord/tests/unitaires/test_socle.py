"""Le socle : réglages, liste blanche des commandes, caviardage, notre base."""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
from pathlib import Path

import pytest

from tableau import caviardage, config, db, systeme

# --- réglages ------------------------------------------------------------------------------------------------------


def test_reglages_absents_donnent_les_valeurs_par_defaut(maison: Path) -> None:
    r = config.charger()
    assert r.erreurs == []
    assert r["serveur"]["port"] == config.PORT_DEFAUT
    assert (
        r["alertes"]["max_par_jour"] == 3 and r["alertes"]["silence_debut"] == 23 and r["alertes"]["silence_fin"] == 8
    )


def test_valeur_fausse_remplacee_avec_un_message(tmp_path: Path) -> None:
    f = tmp_path / "reglages.toml"
    f.write_text(
        '[serveur]\nport = 5678\n[alertes]\nmax_par_jour = "trois"\nsilence_debut = 30\n[inconnu]\nx = 1\n'
        '[rapport]\nheure = "25h"\njour = 9\n[intervalles]\nsante_s = 1\n[credits]\napi_admin = "oui"\n'
        "[installation]\nprefixe_label = 3\n[seuils]\nfile_bloquee_min = -4\n[energie]\nwatts_par_coeur = 3\n"
        "[instantane]\nactif = 1\n"
    )
    r = config.charger(f)
    assert r["serveur"]["port"] == config.PORT_DEFAUT  # jamais le port de n8n
    assert r["alertes"]["max_par_jour"] == 3 and r["alertes"]["silence_debut"] == 23
    assert r["rapport"]["heure"] == "20:00" and r["rapport"]["jour"] == 6
    assert r["intervalles"]["sante_s"] == 60 and r["credits"]["api_admin"] is False
    assert r["seuils"]["file_bloquee_min"] == 30
    assert r["energie"]["watts_par_coeur"] == 3.0 and isinstance(r["energie"]["watts_par_coeur"], float)
    texte = " ".join(r.erreurs)
    for attendu in ("serveur.port", "max_par_jour", "inconnu", "rapport.heure", "rapport.jour", "sante_s",
                    "api_admin", "prefixe_label", "file_bloquee_min", "instantane.actif"):  # fmt: skip
        assert attendu in texte


def test_reglages_illisibles(tmp_path: Path) -> None:
    f = tmp_path / "reglages.toml"
    f.write_text("[serveur\nport = ")
    r = config.charger(f)
    assert "illisible" in r.erreurs[0] and r["serveur"]["port"] == config.PORT_DEFAUT


def test_section_attendue_mais_valeur_simple(tmp_path: Path) -> None:
    f = tmp_path / "reglages.toml"
    f.write_text("serveur = 3\n")
    assert "doit être une section" in config.charger(f).erreurs[0]


def test_label_et_prefixe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "reglages.toml"
    f.write_text('[installation]\nprefixe_label = "Jean-Paul!"\n')
    assert config.charger(f).label() == "com.jean-paul.tableau"
    monkeypatch.setattr(config.getpass, "getuser", lambda: "Moi")
    assert config.charger(tmp_path / "absent.toml").label() == "com.moi.tableau"
    monkeypatch.setattr(config.getpass, "getuser", lambda: "@@@")
    assert config.charger(tmp_path / "absent.toml").prefixe() == "moi"


@pytest.mark.parametrize(
    "avant, attendu",
    [
        ("", "[serveur]\nport = 47620\n"),
        ("[alertes]\nmax_par_jour = 2\n", "[alertes]\nmax_par_jour = 2\n\n[serveur]\nport = 47620\n"),
        ("[serveur]\nport = 47615\n# note\n", "[serveur]\nport = 47620\n# note\n"),
        ("[serveur]\n# rien\n[alertes]\nport = 3\n", "[serveur]\nport = 47620\n# rien\n[alertes]\nport = 3\n"),
    ],
)
def test_enregistrer_port_ne_touche_que_la_ligne_du_port(tmp_path: Path, avant: str, attendu: str) -> None:
    f = tmp_path / "reglages.toml"
    if avant:
        f.write_text(avant)
    config.enregistrer_port(47620, f)
    assert f.read_text() == attendu
    assert config.charger(f)["serveur"]["port"] == 47620
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_chemins_et_jeton(maison: Path) -> None:
    c = config.chemins()
    assert c.support == maison / "Library" / "Application Support" / "TableauDeBord"
    assert c.logs == maison / "Library" / "Logs" / "TableauDeBord"
    assert c.icloud.name == "Tableau" and "CloudDocs" in str(c.icloud)
    c.preparer()
    assert stat.S_IMODE(c.support.stat().st_mode) == 0o700
    j = config.jeton(c)
    assert len(j) >= 32 and config.jeton(c) == j
    assert stat.S_IMODE(c.jeton.stat().st_mode) == 0o600
    c.jeton.write_text("court")
    assert config.jeton(c) != "court"


def test_icloud_surchargeable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TABLEAU_ICLOUD", str(tmp_path / "nuage"))
    assert config.chemins().icloud == tmp_path / "nuage" / "Tableau"


# --- liste blanche des commandes -----------------------------------------------------------------------------------

PERMISES = [
    ["launchctl", "list"],
    ["launchctl", "list", "com.exemple.trieur"],
    ["launchctl", "print", "gui/501/com.exemple.trieur"],
    ["launchctl", "print", "gui/501"],
    ["/bin/ps", "-axo", "pid,ppid,rss,command"],
    ["docker", "ps", "-a", "--format", "{{json .}}"],
    ["docker", "inspect", "n8n"],
    ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
    ["git", "--no-optional-locks", "-C", "/x", "rev-parse", "HEAD"],
    ["git", "--no-optional-locks", "-C", "/x", "log", "-1", "--format=%H"],
    ["git", "--no-optional-locks", "status", "--porcelain"],
    ["lsof", "-p", "123"],
    ["pmset", "-g", "batt"],
    ["sysctl", "-n", "hw.ncpu"],
    ["osascript", "-e", 'display notification "x" with title "y"'],
    ["open", "http://127.0.0.1:47615/?t=abc"],
    ["open", "/Users/x/Library/Application Support/TableauDeBord/rapports/semaine.html"],
    ["security", "find-generic-password", "-s", systeme.SERVICE_TROUSSEAU, "-w"],
]

INTERDITES = [
    [],
    ["launchctl", "bootstrap", "gui/501", "/x.plist"],
    ["launchctl", "bootout", "gui/501/com.exemple.trieur"],
    ["launchctl", "kickstart", "-k", "gui/501/com.exemple.trieur"],
    ["launchctl", "kill", "TERM", "gui/501/com.exemple.trieur"],
    ["launchctl", "enable", "gui/501/com.exemple.trieur"],
    ["launchctl", "disable", "gui/501/com.exemple.trieur"],
    ["launchctl", "load", "/x.plist"],
    ["launchctl", "unload", "/x.plist"],
    ["launchctl", "print", "gui/501/com.x; rm -rf ~"],
    ["launchctl", "list", "a b"],
    ["docker", "restart", "n8n"],
    ["docker", "stop", "n8n"],
    ["docker", "exec", "n8n", "sh"],
    ["docker", "stats"],
    ["docker"],
    ["git", "status"],
    ["git", "--no-optional-locks", "checkout", "."],
    ["git", "--no-optional-locks", "-C", "/x", "reset", "--hard"],
    ["git", "--no-optional-locks", "log", "--output=/tmp/x"],
    ["git", "--no-optional-locks"],
    ["kill", "-9", "123"],
    ["pkill", "trieur"],
    ["rm", "-rf", "/"],
    ["sh", "-c", "launchctl list"],
    ["brctl", "download", "x"],
    ["pmset", "sleepnow"],
    ["sysctl", "-w", "x=1"],
    ["sysctl", "-n", "x=1"],
    ["osascript", "-e", 'tell application "Finder" to delete'],
    ["open", "https://evil.example/"],
    ["open", "/Applications/Calculator.app"],
    ["security", "find-generic-password", "-s", "autre-service", "-w"],
    ["ps", "-k"],
    ["python3", "trieur.py", "doctor"],
]


@pytest.mark.parametrize("commande", PERMISES)
def test_liste_blanche_permet_la_lecture(commande: list[str]) -> None:
    systeme.verifier(commande)


@pytest.mark.parametrize("commande", INTERDITES)
def test_liste_blanche_refuse_tout_le_reste(commande: list[str]) -> None:
    with pytest.raises(systeme.CommandeInterdite):
        systeme.verifier(commande)
    with pytest.raises(systeme.CommandeInterdite):
        systeme.executer(commande)


def test_executer_ne_leve_jamais_pour_une_panne(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dormir = shutil.which("sleep")
    r = systeme.executer(["ps", "-o", "pid=", "-p", str(os.getpid())])
    assert r.ok and str(os.getpid()) in r.sortie
    assert systeme.JOURNAL[-1][1][0] == "ps"
    monkeypatch.setenv("PATH", str(tmp_path))
    absent = systeme.executer(["launchctl", "list"])
    assert absent.code == 127 and "introuvable" in absent.erreur and not absent.ok
    lent = tmp_path / "pmset"
    lent.write_text(f"#!/bin/sh\n{dormir} 5\n")
    lent.chmod(0o755)
    assert systeme.executer(["pmset", "-g"], delai=0.2).code == 124
    casse = tmp_path / "sysctl"
    casse.write_text("pas un script")
    casse.chmod(0o644)
    assert systeme.executer(["sysctl", "-n", "hw.ncpu"]).code == 126


def test_diagnostic_seulement_sur_demande_explicite(tmp_path: Path) -> None:
    with pytest.raises(systeme.CommandeInterdite):
        systeme.executer_diagnostic(["echo", "x"], tmp_path, "page")  # type: ignore[arg-type]
    with pytest.raises(systeme.CommandeInterdite):
        systeme.executer_diagnostic(["echo", "x"], tmp_path, systeme.DemandeExplicite("automatique", "trieur"))
    with pytest.raises(systeme.CommandeInterdite):
        systeme.executer_diagnostic([], tmp_path, systeme.DemandeExplicite("page", "trieur"))
    r = systeme.executer_diagnostic(["echo", "bonjour"], tmp_path, systeme.DemandeExplicite("page", "trieur"))
    assert r.ok and r.sortie.strip() == "bonjour"
    assert systeme.DIAGNOSTICS[-1][1:3] == ("page", "trieur")
    assert (
        systeme.executer_diagnostic(["/introuvable/x"], tmp_path, systeme.DemandeExplicite("terminal", "t")).code == 127
    )
    assert (
        systeme.executer_diagnostic(["sleep", "3"], tmp_path, systeme.DemandeExplicite("terminal", "t"), 0.2).code
        == 124
    )
    pas_executable = tmp_path / "x.sh"
    pas_executable.write_text("echo")
    assert (
        systeme.executer_diagnostic([str(pas_executable)], tmp_path, systeme.DemandeExplicite("terminal", "t")).code
        == 126
    )


def test_est_un_mac() -> None:
    assert systeme.est_un_mac() == (os.uname().sysname == "Darwin")


# --- caviardage ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "brut, absent",
    [
        ("envoi à jean.dupont@example.org échoué", "jean.dupont@example.org"),
        ("fichier /Users/jean/Documents/impots.pdf introuvable", "/Users/jean"),
        ("fichier /home/jean/x introuvable", "/home/jean"),
        ("clé sk-ant-api03-AbCdEf123456_xyz refusée", "sk-ant-api03"),
        ("Authorization: Bearer abcdef0123456789zz", "abcdef0123456789zz"),
        ("token=ya29.a0AfH6SMBxyzxyzxyzxyzxyzxyz", "ya29.a0AfH6SMB"),
        ("http://127.0.0.1:47615/?t=AbCdEfGhIjKl0123", "AbCdEfGhIjKl0123"),
        ("IBAN FR76 3000 6000 0112 3456 7890 189 refusé", "3000 6000"),
        ("carte 4970 1012 3456 7890", "4970 1012"),
        ("appelle le 06 12 34 56 78", "06 12 34 56 78"),
        ("sécu 1 85 05 78 006 084 36", "78 006 084"),
        ("identifiant 7f3a9c0b1e2d4f5a6b7c8d9e0f1a2b3c4d5e6f7a", "7f3a9c0b1e2d"),
        ("mot de passe: hunter2hunter2", "hunter2hunter2"),
        ("/var/folders/ab/cd1234/T/tmpx", "/var/folders"),
    ],
)
def test_caviarder_retire_le_personnel(brut: str, absent: str) -> None:
    propre = caviardage.caviarder(brut)
    assert absent not in propre
    assert not caviardage.contient_sensible(propre)


def test_caviarder_garde_le_sens_et_coupe() -> None:
    assert caviardage.caviarder("") == ""
    assert caviardage.caviarder("tour en échec : 'NoneType'   object") == "tour en échec : 'NoneType' object"
    assert caviardage.caviarder("a   b", compacter=False) == "a   b"
    long = caviardage.caviarder("x " * 500, longueur_max=50)
    assert len(long) == 50 and long.endswith("…")


def test_contient_sensible() -> None:
    assert caviardage.contient_sensible("Trieur 🟢 3 erreurs") == []
    assert "e-mail" in caviardage.contient_sensible("a@b.fr")
    assert "chemin personnel" in caviardage.contient_sensible("/Users/x")
    assert "jeton du tableau de bord" in caviardage.contient_sensible("abc JETONSECRET", ("JETONSECRET",))


# --- notre base ----------------------------------------------------------------------------------------------------


def test_base_creee_en_600_et_meta(tmp_path: Path) -> None:
    b = db.Base(tmp_path / "t" / "tableau.db")
    assert stat.S_IMODE((tmp_path / "t" / "tableau.db").stat().st_mode) == 0o600
    assert b.lire_meta("x") is None and b.lire_meta("x", "d") == "d"
    b.ecrire_meta("x", "1")
    b.ecrire_meta("x", "2")
    assert b.lire_meta("x") == "2"
    b.effacer_meta("x")
    assert b.lire_meta("x") is None
    b.noter_evenement(10.0, "trieur", "boucle", "grave", "message")
    b.noter_evenement(20.0, "corvees", "ok", "ok", "fini")
    assert [e["module"] for e in b.evenements(0)] == ["corvees", "trieur"]
    assert [e["module"] for e in b.evenements(0, "trieur")] == ["trieur"]
    b.ecrire_etat_module("trieur", {"pastille": "vert"}, 5.0)
    b.executer("INSERT INTO etat_modules VALUES ('casse', '{pas du json', 1)")
    assert b.etats_modules() == {"trieur": {"pastille": "vert"}}
    assert b.valeur("SELECT 1 WHERE 0", defaut="rien") == "rien"
    b.fermer()


def test_base_abimee_mise_de_cote(tmp_path: Path) -> None:
    chemin = tmp_path / "tableau.db"
    chemin.write_bytes(b"ceci n'est pas une base SQLite" * 100)
    b = db.Base(chemin)
    b.ecrire_meta("ok", "1")
    assert b.lire_meta("ok") == "1"
    assert list(tmp_path.glob("tableau.db.abimee-*"))


def test_transaction_annulee_sur_erreur(tmp_path: Path) -> None:
    b = db.Base(tmp_path / "tableau.db")
    with pytest.raises(RuntimeError):
        with b.transaction():
            b.db.execute("INSERT INTO meta VALUES ('a', 'b')")
            raise RuntimeError("panne")
    assert b.lire_meta("a") is None


def test_disque_plein_devient_une_exception_douce(tmp_path: Path) -> None:
    b = db.Base(tmp_path / "tableau.db")

    class Plein:
        def execute(self, *a: object) -> None:
            raise sqlite3.OperationalError("database or disk is full")

        executemany = execute

        def close(self) -> None:
            pass

    b.db = Plein()  # type: ignore[assignment]
    with pytest.raises(db.DisquePlein):
        b.executer("INSERT INTO meta VALUES ('a', 'b')")
    with pytest.raises(db.DisquePlein):
        b.plusieurs("INSERT INTO meta VALUES (?, ?)", [("a", "b")])

    class Autre(Plein):
        def execute(self, *a: object) -> None:
            raise sqlite3.OperationalError("no such table")

        executemany = execute

    b.db = Autre()  # type: ignore[assignment]
    with pytest.raises(sqlite3.OperationalError):
        b.executer("x")
    with pytest.raises(sqlite3.OperationalError):
        b.plusieurs("x", [])


def test_commit_disque_plein(tmp_path: Path) -> None:
    b = db.Base(tmp_path / "tableau.db")
    vraie = b.db

    class Enveloppe:
        def execute(self, sql: str, *a: object) -> object:
            if sql == "COMMIT":
                raise sqlite3.OperationalError("database or disk is full")
            return vraie.execute(sql, *a)

    b.db = Enveloppe()  # type: ignore[assignment]
    with pytest.raises(db.DisquePlein):
        with b.transaction():
            pass

    class Enveloppe2(Enveloppe):
        def execute(self, sql: str, *a: object) -> object:
            if sql == "COMMIT":
                raise sqlite3.OperationalError("autre chose")
            return vraie.execute(sql, *a)

    b.db = Enveloppe2()  # type: ignore[assignment]
    with pytest.raises(sqlite3.OperationalError):
        with b.transaction():
            pass


def test_entretien_agrege_et_purge(tmp_path: Path) -> None:
    b = db.Base(tmp_path / "tableau.db")
    maintenant = 100 * 86400.0
    vieux = maintenant - 3 * 86400
    lignes = [("trieur", vieux + i * 60, "vert" if i % 2 else "rouge", 1.0 + i, 50.0, 2, 1, 0) for i in range(10)]
    b.plusieurs("INSERT INTO echantillons VALUES (?, ?, ?, ?, ?, ?, ?, ?)", lignes)
    b.executer("INSERT INTO echantillons VALUES ('trieur', ?, 'vert', 1, 1, 0, 0, 0)", (maintenant - 60,))
    b.noter_evenement(maintenant - 95 * 86400, "trieur", "x", "info", "ancien")
    b.entretenir(maintenant)
    assert b.valeur("SELECT COUNT(*) FROM echantillons") == 1
    h = b.lignes("SELECT * FROM agregats WHERE periode = 'h'")
    assert sum(r["n"] for r in h) == 10 and sum(r["rouge"] for r in h) == 5 and sum(r["vert"] for r in h) == 5
    assert b.evenements(0) == []
    # Un second entretien n'agrège rien deux fois.
    b.entretenir(maintenant)
    assert sum(r["n"] for r in b.lignes("SELECT n FROM agregats WHERE periode = 'h'")) == 10
    # 90 jours plus tard : les heures deviennent des jours.
    b.entretenir(maintenant + 92 * 86400)
    j = b.lignes("SELECT * FROM agregats WHERE periode = 'j'")
    assert sum(r["n"] for r in j) == 11
    assert b.valeur("SELECT COUNT(*) FROM agregats WHERE periode = 'h'") == 0
