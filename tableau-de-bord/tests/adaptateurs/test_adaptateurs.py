"""Découverte, registre et adaptateurs, sur un faux Mac aux schémas exacts (réels ou recopiés du code des modules).

Tolérance (§9.2) : table absente, colonne renommée, fichier illisible, format inattendu → « inconnu », jamais une
exception.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tableau import adaptateurs, config, registre
from tableau.adaptateurs import assistant as ad_assistant
from tableau.adaptateurs import base as ad_base
from tableau.adaptateurs import bouclier as ad_bouclier
from tableau.adaptateurs import corvees as ad_corvees
from tableau.adaptateurs import nettoyeur as ad_nettoyeur
from tableau.adaptateurs import quotidien as ad_quotidien
from tableau.adaptateurs import trieur as ad_trieur
from tableau.db import Base
from tableau.decouverte import decouvrir, projet_du_programme
from tableau.module import DefModule, Observation
from tests import fabrique
from tests.fabrique import PREFIXE

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def base(tmp_path: Path) -> Base:
    return Base(tmp_path / "nous" / "tableau.db")


@pytest.fixture
def mac(maison: Path, horloge: Any) -> Any:
    m = fabrique.faux_mac(maison, horloge())
    yield m
    m.fermer()


def observer(ctx: Any, ident: str) -> Any:
    defn = ctx.module(ident)
    assert defn is not None, ident
    return adaptateurs.obtenir(defn.adaptateur).observer(defn, ctx)


# --- découverte et registre ----------------------------------------------------------------------------------------


def test_decouverte(mac: Any) -> None:
    fabrique.ecrire_plist(mac.maison / "Library" / "LaunchAgents", "com.exemple.casse")
    (mac.maison / "Library" / "LaunchAgents" / "pas_un_plist.plist").write_text("n'importe quoi")
    mac.docker.conteneurs["n8n"] = {"Image": "n8nio/n8n", "State": "running"}
    mac.docker.conteneurs["autre"] = {"Image": "postgres", "State": "running"}
    from tableau.sondes.docker_n8n import SondeDocker

    d = decouvrir(config.Chemins(mac.maison), SondeDocker(mac.docker))
    assert d.assistant == mac.assistant
    assert d.agents[f"com.{PREFIXE}.bouclier"].projet == mac.assistant / "bouclier"
    assert d.agents["com.assistant.superviseur"].garde_en_vie and d.agents["com.assistant.icone"].garde_en_vie
    assert d.agents["com.exemple.casse"].programme == []
    assert d.conteneurs == ["n8n"] and d.docker is True
    mac.docker.eteint = True
    assert decouvrir(config.Chemins(mac.maison), SondeDocker(mac.docker)).docker is False


def test_assistant_retrouve_par_son_tri_gmail_sans_superviseur(maison: Path) -> None:
    (maison / "Projets" / "assistant" / "modules" / "mails").mkdir(parents=True)
    (maison / "Projets" / "assistant" / "modules" / "mails" / "tri.py").write_text("")
    assert decouvrir(config.Chemins(maison)).assistant == maison / "Projets" / "assistant"
    assert decouvrir(config.Chemins(maison / "vide")).assistant is None


@pytest.mark.parametrize(
    "programme, travail, attendu",
    [
        (["/Users/x/Assistant/bouclier/.venv/bin/python", "-m", "bouclier"], None, "/Users/x/Assistant/bouclier"),
        (["/usr/bin/python3", "/opt/projet/scripts/lancer.py"], None, "/opt/projet/scripts"),
        (["/bin/zsh", "-c", "x"], "/Users/x/Projets/y", "/Users/x/Projets/y"),
        (["relatif"], None, None),
    ],
)
def test_projet_du_programme(programme: list[str], travail: str | None, attendu: str | None) -> None:
    resultat = projet_du_programme(programme, travail)
    assert (str(resultat) if resultat else None) == attendu


def test_projet_remonte_jusqu_au_depot(tmp_path: Path) -> None:
    (tmp_path / "depot" / ".git").mkdir(parents=True)
    (tmp_path / "depot" / "outils").mkdir()
    assert projet_du_programme([str(tmp_path / "depot" / "outils" / "x.py")], None) == tmp_path / "depot"


def test_registre_genere_puis_complete_sans_toucher_au_reste(mac: Any, base: Base, horloge: Any) -> None:
    chemins = config.Chemins(mac.maison)
    agents = mac.maison / "Library" / "LaunchAgents"
    fabrique.ecrire_plist(agents, f"com.{PREFIXE}.mystere", ProgramArguments=["/opt/mystere/run.sh"], KeepAlive=True,
                          StandardErrorPath=str(mac.maison / "Library" / "Logs" / "Mystere" / "err.log"))  # fmt: skip
    fabrique.ecrire_plist(agents, f"com.{PREFIXE}.tableau")
    fabrique.ecrire_plist(agents, f"com.{PREFIXE}.tdbtest.1")
    d = decouvrir(chemins)
    modules, ajoutes, erreurs = registre.synchroniser(chemins.registre, PREFIXE, d, mac.maison)
    ids = [m.id for m in modules]
    assert ids == ["assistant", "corvees", "nettoyeur", "trieur", "bouclier", "quotidien", "ambiance", "n8n", "mystere"]
    assert erreurs == [] and ajoutes == ids
    mystere = modules[-1]
    assert (
        mystere.adaptateur == "generique" and mystere.doit_tourner and mystere.dossier_logs == "~/Library/Logs/Mystere"
    )
    assert oct(chemins.registre.stat().st_mode & 0o777) == "0o600"
    par_id = {m.id: m for m in modules}
    assert (
        par_id["trieur"].dossier_projet == "~/Assistant" and par_id["bouclier"].dossier_projet == "~/Assistant/bouclier"
    )
    assert par_id["ambiance"].dossier_projet is None  # pas installé : rien à déduire
    # Tu modifies le registre ; un nouveau module apparaît : il est ajouté à la fin, le reste ne bouge pas.
    texte = chemins.registre.read_text().replace('nom = "Trieur"', 'nom = "Mon Trieur"')
    texte = texte.replace('id = "n8n"', 'id = "n8n"\nactif = false')
    chemins.registre.write_text(texte)
    fabrique.ecrire_plist(agents, f"com.{PREFIXE}.ambiance", ProgramArguments=["/opt/ambiance/.venv/bin/python"])
    fabrique.ecrire_plist(agents, f"com.{PREFIXE}.futur")
    modules, ajoutes, erreurs = registre.synchroniser(chemins.registre, PREFIXE, decouvrir(chemins), mac.maison)
    assert ajoutes == ["futur"] and erreurs == []
    assert chemins.registre.read_text().startswith(texte)
    par_id = {m.id: m for m in modules}
    assert par_id["trieur"].nom == "Mon Trieur" and "n8n" not in par_id
    assert par_id["ambiance"].dossier_projet == "/opt/ambiance"
    # Une seconde synchronisation n'ajoute rien.
    assert registre.synchroniser(chemins.registre, PREFIXE, decouvrir(chemins), mac.maison)[1] == []


def test_un_module_connu_retire_puis_installe_revient(mac: Any) -> None:
    chemins = config.Chemins(mac.maison)
    registre.synchroniser(chemins.registre, PREFIXE, decouvrir(chemins), mac.maison)
    texte = chemins.registre.read_text()
    debut = texte.index('[[module]]\nid = "ambiance"')
    fin = texte.index("[[module]]", debut + 5)
    chemins.registre.write_text(texte[:debut] + texte[fin:])
    fabrique.ecrire_plist(mac.maison / "Library" / "LaunchAgents", f"com.{PREFIXE}.ambiance.audio")
    modules, ajoutes, _ = registre.synchroniser(chemins.registre, PREFIXE, decouvrir(chemins), mac.maison)
    assert ajoutes == ["ambiance"] and next(m for m in modules if m.id == "ambiance").adaptateur == "ambiance"


def test_aide_tapable_sur_un_mac_meme_dans_un_ancien_registre(mac: Any) -> None:
    # Sur un Mac, `python` n'existe pas : l'aide passe par le `.venv` de l'assistant, même si ton registre a été
    # écrit avant (il n'est pas réécrit pour autant). Une aide que tu as changée toi-même reste la tienne.
    chemins = config.Chemins(mac.maison)
    registre.synchroniser(chemins.registre, PREFIXE, decouvrir(chemins), mac.maison)
    neuf = chemins.registre.read_text()
    assert 'aide = "python ' not in neuf
    ancien = neuf.replace(
        'aide = "cd ~/Assistant && .venv/bin/python assistant.py etat"',
        'aide = "python assistant.py etat (dans ~/Assistant)"',
    ).replace(
        'aide = "cd ~/Assistant && .venv/bin/python trieur.py doctor"',
        'aide = "python3 trieur.py doctor --mon-option"',
    )
    assert ancien != neuf
    chemins.registre.write_text(ancien)
    modules, _, _ = registre.synchroniser(chemins.registre, PREFIXE, decouvrir(chemins), mac.maison)
    par_id = {m.id: m for m in modules}
    assert par_id["assistant"].aide == "cd ~/Assistant && .venv/bin/python assistant.py etat"
    assert par_id["corvees"].aide == "cd ~/Assistant && .venv/bin/python corvees.py doctor"
    assert par_id["trieur"].aide == "python3 trieur.py doctor --mon-option"
    assert chemins.registre.read_text() == ancien
    assert registre.aide_a_jour("bouclier doctor") == "bouclier doctor"


def test_registre_tolerant(tmp_path: Path) -> None:
    modules, erreurs = registre.lire("ceci n'est pas du TOML [")
    assert modules == [] and "illisible" in erreurs[0]
    texte = """
[[module]]
nom = "sans id"
[[module]]
id = "a"
plafond_usd = -3
labels = [1, 2]
doit_tourner = "oui"
file_max_min = 15
port = 0
inconnu = 3
[[module.attente]]
id = "brief"
genre = "quotidienne"
heure = "vers 7h"
[[module.attente]]
id = "x"
genre = "periodique"
[[module.attente]]
genre = "autre"
[[module.attente]]
id = "ok"
genre = "periodique"
toutes_les_min = 5
[[module]]
id = "a"
"""
    modules, erreurs = registre.lire(texte)
    assert [m.id for m in modules] == ["a"] and modules[0].file_max_min == 15 and modules[0].port is None
    assert [a.id for a in modules[0].attentes] == ["ok"]
    texte_erreurs = " ".join(erreurs)
    for attendu in ("sans « id »", "plafond_usd", "labels", "doit_tourner", "port", "HH:MM", "toutes_les_min",
                    "mal écrite", "deux fois"):  # fmt: skip
        assert attendu in texte_erreurs, attendu
    # Fichier cassé : les modules connus quand même, et le fichier n'est pas réécrit.
    f = tmp_path / "modules.toml"
    f.write_text("[[module]\n")
    modules, ajoutes, erreurs = registre.synchroniser(f, "x", fabrique.decouvrir(config.Chemins(tmp_path)), tmp_path)
    assert [m.id for m in modules][:2] == ["assistant", "corvees"] and erreurs and f.read_text() == "[[module]\n"


def test_registre_aller_retour() -> None:
    modules = registre.connus("moi")
    relus, erreurs = registre.lire(registre.ecrire(modules))
    assert erreurs == [] and relus == modules
    bizarre = DefModule(id="b", nom='Avec "guillemets" et \\', labels=["com.moi.b"], plafond_usd=1.5)
    assert registre.lire(registre.ecrire([bizarre]))[0] == [bizarre]


def test_exemple_du_depot_est_valide() -> None:
    modules, erreurs = registre.lire((Path(__file__).resolve().parents[2] / "modules.example.toml").read_text())
    assert erreurs == [] and {m.id for m in modules} >= {"trieur", "bouclier", "quotidien"}


# --- l'écosystème en bonne santé -----------------------------------------------------------------------------------


def test_tous_les_modules_en_bonne_sante(mac: Any, base: Base, horloge: Any) -> None:
    ctx = fabrique.contexte(mac, base, horloge)
    a = observer(ctx, "assistant")
    assert a.installe and [e.label for e in a.launchd] == ["com.assistant.superviseur", "com.assistant.icone"]
    assert a.battement_ts is not None and horloge() - a.battement_ts < 5
    assert a.superviseur["modules"]["trieur"]["statut"] == "actif" and a.superviseur["tri_gmail_actif"] is True
    # sonnet 100k/20k + haiku 50k/5k (l'appel en échec ne compte pas) : 0,2 + 0,2 + 0,005 + 0,0025
    assert a.credits.source == "estimation" and a.credits.mois_usd == pytest.approx(0.4075)
    assert "1 appel(s) aujourd'hui sur 60 permis" in a.credits.detail or "2 appel(s)" in a.credits.detail
    assert a.activite[0] == "dernier mail trié"
    assert a.logs is not None and a.logs.erreurs_24h == 0
    t = observer(ctx, "trieur")
    assert t.installe and t.actif is True and t.superviseur["statut"] == "actif"
    assert t.credits.mois_usd == pytest.approx(0.12) and t.credits.plafond_usd == 1.0
    assert t.activite == ("dernière facture classée", horloge() - 7200)
    file = next(f for f in t.files if f.nom.startswith("documents"))
    assert file.n == 0 and file.seuil_min == 15
    assert {f.nom for f in t.files} >= {"iCloud/BoiteMac", "documents en attente de classement"}
    c = observer(ctx, "corvees")
    assert c.actif is True and c.credits.mois_usd == pytest.approx(0.30) and c.credits.plafond_usd == 2.0
    assert c.preuves["analyse"] == pytest.approx(horloge() - 13 * 3600) and c.battement_periode_s == 60
    assert c.reglages_attentes["analyse"] == {"heure": "21:00"}
    n = observer(ctx, "nettoyeur")
    assert n.preuves["releve"] == pytest.approx(horloge() - 60) and n.credits is None
    b = observer(ctx, "bouclier")
    assert b.installe and b.launchd[0].pid and b.preuves["gmail"] == pytest.approx(horloge() - 120)
    assert b.credits.mois_usd == pytest.approx(0.40) and b.reglages_attentes["gmail"] == {"toutes_les_min": 5}
    assert b.technique["etat_public"]["hygiene"]["score"] == 72
    assert b.logs.derniere_ligne_ts == pytest.approx(horloge() - 50)
    q = observer(ctx, "quotidien")
    assert (
        q.preuves["brief"] == pytest.approx(horloge() - 3 * 3600) and q.reglages_attentes["brief"]["heure"] == "07:15"
    )
    assert q.credits.mois_usd == pytest.approx(0.05) and q.battement_periode_s == 30
    assert observer(ctx, "ambiance").installe is False
    assert observer(ctx, "n8n").installe is False
    for o in (a, t, c, n, b, q):
        assert o.inconnus == [] or o.inconnus == ["processus"], o.technique.get("erreurs")
        assert o.tailles is not None


def test_taille_de_l_assistant_sans_modeles_telecharges_ni_doublons(mac: Any, base: Base, horloge: Any) -> None:
    # Les modèles de traduction (~1,4 Go, téléchargés une fois) et les données de Corvées, Nettoyeur, Trieur (comptées
    # chez eux) ne font pas « gonfler » l'assistant ; ses vraies données, si.
    ctx = fabrique.contexte(mac, base, horloge)
    avant = observer(ctx, "assistant").tailles[0]
    donnees = mac.assistant / "donnees"
    gros = 3 * 1024 * 1024
    for dossier in ("traduction/nllb", "traduction/modele", "oreilles/modeles", "corvees", "demarrage", "trieur"):
        (donnees / dossier).mkdir(parents=True, exist_ok=True)
        (donnees / dossier / "gros.bin").write_bytes(b"0" * gros)
    ctx.nouveau_tour(mesurer_tailles=True)
    assert observer(ctx, "assistant").tailles[0] == avant
    assert observer(ctx, "corvees").tailles[0] >= gros and observer(ctx, "trieur").tailles[0] >= gros
    (donnees / "memoire-en-plus.bin").write_bytes(b"0" * gros)
    ctx.nouveau_tour(mesurer_tailles=True)
    assert observer(ctx, "assistant").tailles[0] == avant + gros


def test_journal_partage_reparti_entre_les_modules(mac: Any, base: Base, horloge: Any) -> None:
    ctx = fabrique.contexte(mac, base, horloge)
    with open(mac.assistant / "logs" / "assistant.log", "a") as f:
        f.write(f"{fabrique.date(horloge())} ERROR   [trieur] tour en échec : x\n"
                f"{fabrique.date(horloge())} WARNING [superviseur] Module « trieur » tombé (code 1) : x\n"
                f"{fabrique.date(horloge())} ERROR   [mails] Gmail a répondu une erreur (500)\n"
                f"{fabrique.date(horloge())} ERROR   [corvees] Plantage : boum\nTraceback (most recent call last):\n"
                f"  File \"x\", line 1\nValueError: boum\n")  # fmt: skip
    ctx.nouveau_tour()
    t, c, a = observer(ctx, "trieur"), observer(ctx, "corvees"), observer(ctx, "assistant")
    assert t.logs.erreurs_1h == 1 and t.relances and t.logs.derniere_erreur == "tour en échec : x"
    assert c.logs.erreurs_1h == 1 and c.logs.derniere_erreur == "Plantage : boum"
    assert a.logs.erreurs_1h == 1 and a.logs.avert_1h == 1  # [mails] et [superviseur] sont à l'assistant
    assert base.valeur("SELECT COUNT(*) FROM relances WHERE module = 'trieur'") == 1


def test_relances_vues_par_launchd(mac: Any, base: Base, horloge: Any) -> None:
    ctx = fabrique.contexte(mac, base, horloge)
    label = f"com.{PREFIXE}.bouclier"
    observer(ctx, "bouclier")
    mac.launchd.agents[label] = {"pid": None, "statut": 1, "runs": 4}
    horloge.avancer(60)
    ctx.nouveau_tour()
    b = observer(ctx, "bouclier")
    assert len(b.relances) == 3 and b.launchd[0].dernier_code == 1 and b.launchd[0].pid is None
    # Compteur remis à zéro (Mac redémarré) : pas de relance comptée.
    mac.launchd.agents[label] = {"pid": 2**22 + 701, "statut": 0, "runs": 1}
    horloge.avancer(60)
    ctx.nouveau_tour()
    assert observer(ctx, "bouclier").relances == []


# --- éteints, en pause, désinstallés -------------------------------------------------------------------------------


def test_module_eteint_ou_en_pause_n_est_pas_une_panne(mac: Any, base: Base, horloge: Any) -> None:
    reglages = json.loads((mac.assistant / "reglages.json").read_text())
    reglages["modules"]["demarrage"]["actif"] = False
    (mac.assistant / "reglages.json").write_text(json.dumps(reglages))
    etat = mac.ecrivains[0]
    etat.execute("UPDATE modules SET statut = 'désactivé' WHERE nom = 'demarrage'")
    etat.execute("UPDATE modules SET statut = 'en pause', detail = 'micro coupé' WHERE nom = 'trieur'")
    etat.execute("DELETE FROM modules WHERE nom = 'mails'")
    corvees = mac.ecrivains[3]
    corvees.execute("INSERT INTO etat VALUES ('pause', ?, 0)", (json.dumps({"jusqua": horloge() + 3600}),))
    ctx = fabrique.contexte(mac, base, horloge)
    n = observer(ctx, "nettoyeur")
    assert n.actif is False and ".venv/bin/python assistant.py activer demarrage" in n.raison_inactif
    t = observer(ctx, "trieur")
    assert t.actif is False and "micro coupé" in t.raison_inactif
    c = observer(ctx, "corvees")
    assert c.actif is False and "en pause jusqu'au" in c.raison_inactif
    corvees.execute("UPDATE etat SET valeur = 'true' WHERE cle = 'pause'")
    horloge.avancer(10_000)
    ctx.nouveau_tour()
    c = observer(ctx, "corvees")
    assert c.actif is False and "corvees resume" in c.raison_inactif


def test_module_desinstalle_en_cours_de_route(mac: Any, base: Base, horloge: Any) -> None:
    import shutil

    ctx = fabrique.contexte(mac, base, horloge)
    assert observer(ctx, "quotidien").installe
    (mac.maison / "Library" / "LaunchAgents" / f"com.{PREFIXE}.quotidien.plist").unlink()
    del mac.launchd.agents[f"com.{PREFIXE}.quotidien"]
    shutil.rmtree(mac.support / "Quotidien")
    ctx.nouveau_tour()
    assert observer(ctx, "quotidien").installe is False
    shutil.rmtree(mac.assistant / "modules" / "trieur")
    ctx.nouveau_tour()
    assert observer(ctx, "trieur").installe is False


def test_n8n_docker_eteint_puis_rallume(mac: Any, base: Base, horloge: Any) -> None:
    mac.docker.conteneurs["n8n"] = {"Image": "n8nio/n8n", "State": "running"}
    ctx = fabrique.contexte(mac, base, horloge)
    o = observer(ctx, "n8n")
    assert o.installe and o.n8n["repond"] and o.n8n["etat"] == "running" and o.processus.rss_mo == pytest.approx(200)
    mac.docker.eteint = True
    ctx.healthz = lambda port: (False, "injoignable (ConnectionRefusedError)")
    ctx.nouveau_tour()
    o = observer(ctx, "n8n")
    assert o.installe and not o.n8n["repond"] and o.n8n["etat"] == "docker éteint"
    mac.docker.eteint = False
    mac.docker.conteneurs["n8n"]["State"] = "exited"
    ctx.nouveau_tour()
    o = observer(ctx, "n8n")
    assert o.n8n["etat"] == "running" or o.n8n["etat"] == "exited"


def test_launchd_qui_ne_repond_plus(mac: Any, base: Base, horloge: Any) -> None:
    ctx = fabrique.contexte(mac, base, horloge)
    mac.launchd.en_panne = True
    ctx.nouveau_tour()
    b = observer(ctx, "bouclier")
    assert b.installe and "launchd" in b.inconnus and b.launchd == []


# --- tolérance : formats inattendus --------------------------------------------------------------------------------


def _remplacer_base(chemin: Path, script: str) -> None:
    for suffixe in ("", "-wal", "-shm"):
        Path(f"{chemin}{suffixe}").unlink(missing_ok=True)
    db = sqlite3.connect(chemin)
    db.executescript(script)
    db.close()


@pytest.mark.parametrize(
    "ident, relatif, script",
    [
        ("trieur", "Assistant/donnees/trieur/trieur.db", "CREATE TABLE autre (x);"),
        ("trieur", "Assistant/donnees/trieur/trieur.db",
         "CREATE TABLE elements (id, statut_renomme, arrivee); CREATE TABLE depenses_ia (quand, montant);"),
        ("corvees", "Assistant/donnees/corvees/corvees.db", "CREATE TABLE etat (k, v); CREATE TABLE couts (x);"),
        ("corvees", "Assistant/donnees/corvees/corvees.db",
         "CREATE TABLE etat (cle, valeur); INSERT INTO etat VALUES ('battement', 'pas un nombre');"
         "CREATE TABLE couts (quand REAL, cout_usd REAL); INSERT INTO couts VALUES (1, 'x');"),
        ("nettoyeur", "Assistant/donnees/demarrage/demarrage.db", "CREATE TABLE releves (horodatage);"),
        ("bouclier", "Library/Application Support/Bouclier/bouclier.db", "CREATE TABLE meta (cle, valeur, en_plus);"),
        ("quotidien", "Library/Application Support/Quotidien/quotidien.db",
         "CREATE TABLE taches (nom); CREATE TABLE depenses_ia (date REAL, cout_usd REAL);"),
        ("assistant", "Assistant/donnees/etat.db", "CREATE TABLE modules (x); CREATE TABLE appels_claude (quand);"),
        ("assistant", "Assistant/donnees/mails/memoire.db", "CREATE TABLE mails (id, traite_le);"
         "INSERT INTO mails VALUES (1, 'pas une date');"),
    ],
)  # fmt: skip
def test_format_inattendu_donne_inconnu_jamais_une_exception(
    mac: Any, base: Base, horloge: Any, ident: str, relatif: str, script: str
) -> None:
    mac.fermer()
    _remplacer_base(mac.maison / relatif, script)
    ctx = fabrique.contexte(mac, base, horloge)
    o = observer(ctx, ident)
    assert o.installe
    assert "erreurs" not in o.technique or "base" not in o.technique["erreurs"], o.technique
    if o.credits is not None and ident != "assistant":
        assert o.credits.mois_usd in (None, 0.0) or isinstance(o.credits.mois_usd, float)


@pytest.mark.parametrize("ident", ["trieur", "corvees", "nettoyeur", "bouclier", "quotidien", "assistant"])
def test_base_illisible_ou_absente(mac: Any, base: Base, horloge: Any, ident: str) -> None:
    mac.fermer()
    chemins = {
        "trieur": "Assistant/donnees/trieur/trieur.db",
        "corvees": "Assistant/donnees/corvees/corvees.db",
        "nettoyeur": "Assistant/donnees/demarrage/demarrage.db",
        "bouclier": "Library/Application Support/Bouclier/bouclier.db",
        "quotidien": "Library/Application Support/Quotidien/quotidien.db",
        "assistant": "Assistant/donnees/etat.db",
    }
    chemin = mac.maison / chemins[ident]
    for suffixe in ("-wal", "-shm"):
        Path(f"{chemin}{suffixe}").unlink(missing_ok=True)
    chemin.write_bytes(b"SQLite format 3\x00" + b"\x00" * 50 + b"abime" * 300)
    ctx = fabrique.contexte(mac, base, horloge)
    o = observer(ctx, ident)
    assert o.installe and ("base" in o.inconnus or "statuts du superviseur" in o.inconnus)
    chemin.unlink()
    ctx.nouveau_tour()
    o = observer(ctx, ident)
    assert o.installe


def test_reglages_illisibles_des_autres(mac: Any, base: Base, horloge: Any) -> None:
    (mac.assistant / "reglages.json").write_text("{pas du json")
    (mac.support / "Bouclier" / "config.toml").write_text("[ia\n")
    (mac.support / "Quotidien" / "reglages.toml").write_text("[[[")
    (mac.assistant / "reglages.json").chmod(0o000)
    ctx = fabrique.contexte(mac, base, horloge)
    for ident in ("trieur", "corvees", "bouclier", "quotidien", "assistant"):
        o = observer(ctx, ident)
        assert o.installe and "erreurs" not in o.technique, (ident, o.technique)
    t = observer(ctx, "trieur")
    assert t.credits.plafond_usd == 1.0  # le plafond du registre (README) quand les réglages sont illisibles
    (mac.assistant / "reglages.json").chmod(0o600)


def test_une_etape_qui_plante_n_emporte_pas_les_autres(mac: Any, base: Base, horloge: Any, monkeypatch) -> None:
    ctx = fabrique.contexte(mac, base, horloge)

    def boum(*a: Any) -> None:
        raise RuntimeError("jean@example.org /Users/jean/x")

    monkeypatch.setattr(ad_trieur.Trieur, "lire_files", boum)
    monkeypatch.setattr(ad_trieur.Trieur, "est_installe", lambda *a: True)
    o = observer(ctx, "trieur")
    assert "files" in o.inconnus and o.credits is not None
    assert "jean" not in json.dumps(o.technique)
    monkeypatch.setattr(ad_trieur.Trieur, "est_installe", boum)
    o = observer(ctx, "trieur")
    assert o.installe is False and "installation" in o.technique["erreurs"]


def test_generique_lit_les_journaux_de_son_plist(mac: Any, base: Base, horloge: Any) -> None:
    logs = mac.maison / "Library" / "Logs" / "Mystere"
    logs.mkdir(parents=True)
    (logs / "err.log").write_text(f"{fabrique.date(horloge())} ERROR boum\n")
    fabrique.ecrire_plist(mac.maison / "Library" / "LaunchAgents", f"com.{PREFIXE}.mystere",
                          ProgramArguments=["/bin/true"], StandardErrorPath=str(logs / "err.log"))  # fmt: skip
    mac.launchd.agents[f"com.{PREFIXE}.mystere"] = {"pid": None, "statut": 78}
    ctx = fabrique.contexte(mac, base, horloge)
    o = observer(ctx, "mystere")
    assert o.installe and o.logs.erreurs_1h == 1 and o.launchd[0].dernier_code == 78 and o.processus is None


def test_ambiance_tolerante(mac: Any, base: Base, horloge: Any) -> None:
    support = mac.support / "Ambiance"
    support.mkdir()
    fabrique.ecrire_plist(mac.maison / "Library" / "LaunchAgents", f"com.{PREFIXE}.ambiance")
    db = fabrique.base_depuis(support / "ambiance.db", "CREATE TABLE meta (cle TEXT, valeur TEXT);"
                              "CREATE TABLE depenses_ia (date REAL, cout_usd REAL);")  # fmt: skip
    db.execute("INSERT INTO meta VALUES ('battement', ?)", (str(horloge() - 5),))
    db.execute("INSERT INTO depenses_ia VALUES (?, 0.07)", (horloge() - 60,))
    db.close()
    (support / "autre.db").write_bytes(b"pas une base")
    ctx = fabrique.contexte(mac, base, horloge)
    o = observer(ctx, "ambiance")
    assert o.installe and o.battement_ts == pytest.approx(horloge() - 5) and o.credits.mois_usd == pytest.approx(0.07)


# --- échantillons réels de ton Mac (capturés par install.sh, jamais sur GitHub) ------------------------------------

LECTURES = {
    "assistant-etat": lambda: ad_assistant.lire_appels(0, 0),
    "trieur-trieur": lambda: ad_trieur.lire("2026-10", 0),
    "corvees-corvees": lambda: ad_corvees.lire("2026-10", 0),
    "nettoyeur-demarrage": lambda: ad_nettoyeur.lire,
    "bouclier-bouclier": lambda: ad_bouclier.lire("2026-10", 0),
    "quotidien-quotidien": lambda: ad_quotidien.lire("2026-10", 0),
}


def _echantillons() -> list[Path]:
    trouves: list[Path] = []
    for dossier in ("conteneur", "mac"):
        trouves += sorted((FIXTURES / "reelles" / dossier).glob("*.sql"))
    return trouves


@pytest.mark.parametrize("echantillon", _echantillons(), ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_lectures_sur_les_echantillons_reels(echantillon: Path) -> None:
    lecture = LECTURES.get(echantillon.stem)
    if lecture is None:
        pytest.skip("pas d'adaptateur de base pour cet échantillon")
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(echantillon.read_text())
    resultat = lecture()(db)
    assert isinstance(resultat, dict)
    assert ad_assistant.lire_mails(db) is None or isinstance(ad_assistant.lire_mails(db), float)


def test_outils_communs(tmp_path: Path) -> None:
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE etat (cle, valeur); INSERT INTO etat VALUES ('a', '{\"x\": 1}'), ('b', 'brut'),"
                     "('c', NULL); CREATE TABLE d (date REAL, cout_usd REAL); INSERT INTO d VALUES (5, 1.5), (1, 9);"
                     "CREATE TABLE sans (x); CREATE TABLE sans_date (cout_usd);")  # fmt: skip
    assert ad_base.valeur_cle(db, "etat", "a") == {"x": 1} and ad_base.valeur_cle(db, "etat", "b") == "brut"
    assert ad_base.valeur_cle(db, "etat", "c") is None and ad_base.valeur_cle(db, "absente", "a") is None
    assert ad_base.valeur_cle(db, "d", "a") is None
    assert ad_base.somme_couts(db, "d", "2026-10", 2) == 1.5
    assert (
        ad_base.somme_couts(db, "sans", "2026-10", 2) is None and ad_base.somme_couts(db, "sans_date", "x", 0) is None
    )
    assert ad_base.en_nombre("3.5") == 3.5 and ad_base.en_nombre(True) is None and ad_base.en_nombre("x") is None
    assert ad_base.lire_plist(tmp_path / "absent.plist") == {}
    (tmp_path / "liste.plist").write_bytes(b'<?xml version="1.0"?><plist version="1.0"><array/></plist>')
    assert ad_base.lire_plist(tmp_path / "liste.plist") == {}
    assert ad_base.nom_de_file("~/Desktop/À trier", tmp_path) == "~/Desktop/À trier"
    assert ad_base.nom_de_file("/x/y", Path("/x/y")) == "y"


def test_seuil_de_file_propre_au_module(mac: Any, base: Base, horloge: Any) -> None:
    """`file_max_min` du registre s'applique à toutes les files du module (sinon le seuil général des réglages)."""
    entree = mac.maison / "Entree"
    entree.mkdir()
    (entree / "a.pdf").write_text("x")
    propre = DefModule(id="m", nom="M", files=["~/Entree"], file_max_min=5)
    general = DefModule(id="n", nom="N", files=["~/Entree"])
    ctx = fabrique.contexte(mac, base, horloge, [propre, general])
    a, b = Observation(), Observation()
    ad_base.Adaptateur().lire_files(propre, ctx, a)
    ad_base.Adaptateur().lire_files(general, ctx, b)
    assert a.files[0].seuil_min == 5 and a.files[0].n == 1
    assert b.files[0].seuil_min is None


def test_agent_periodique_ses_passages_ne_sont_pas_des_plantages(mac: Any, base: Base, horloge: Any) -> None:
    label = f"com.{PREFIXE}.releve"
    fabrique.ecrire_plist(mac.maison / "Library" / "LaunchAgents", label, StartInterval=120)
    mac.launchd.agents[label] = {"pid": None, "statut": 0, "runs": 5}
    periodique = DefModule(id="releve", nom="Relevé", labels=[label], doit_tourner=False)
    permanent = DefModule(id="permanent", nom="Permanent", labels=[label], doit_tourner=True)
    ctx = fabrique.contexte(mac, base, horloge, [periodique, permanent])
    for defn in (periodique, permanent):
        ad_base.Adaptateur().observer(defn, ctx)
    mac.launchd.agents[label].update(runs=9, statut=1)  # 4 passages de plus (le dernier en échec)
    ctx.nouveau_tour()
    assert ad_base.Adaptateur().observer(periodique, ctx).relances == []
    assert len(ad_base.Adaptateur().observer(permanent, ctx).relances) == 4


def test_jamais_de_journal_lu_dans_icloud(mac: Any, base: Base, horloge: Any) -> None:
    dans = mac.icloud / "Module" / "logs"
    dans.mkdir(parents=True)
    (dans / "m.log").write_text("2026-10-07 10:00:00 ERROR secret\n")
    defn = DefModule(id="m", nom="M", logs=[str(dans / "m.log")], dossier_logs=str(dans))
    ctx = fabrique.contexte(mac, base, horloge, [defn])
    assert ad_base.Adaptateur().fichiers_journaux(defn, ctx) == []


def test_bouclier_releve_gmail_en_echec_dit_pourquoi(mac: Any, base: Base, horloge: Any) -> None:
    """Bouclier n'avance `gmail_releve_le` qu'après une relève réussie, et note la raison d'un échec : l'alerte la cite
    (caviardée)."""
    from tableau.analyse import attentes

    db = mac.bases["bouclier"]
    db.execute("UPDATE meta SET valeur = ? WHERE cle = 'gmail_releve_le'", (str(horloge() - 86400),))
    db.execute("INSERT INTO meta VALUES ('gmail_erreur', 'Gmail refuse la connexion de alice@example.com (mot de "
               "passe d''application révoqué)')")  # fmt: skip
    ctx = fabrique.contexte(mac, base, horloge)
    defn = ctx.module("bouclier")
    assert defn is not None
    base.ecrire_meta("premier_vu:bouclier", str(horloge() - 2 * 86400))
    obs = adaptateurs.obtenir(defn.adaptateur).observer(defn, ctx)
    gmail = next(v for v in attentes.evaluer(base, defn, obs, horloge()) if v.attente.id == "gmail")
    assert gmail.statut == "manquee"
    assert gmail.detail == (
        "aucun passage depuis 1 j ; Bouclier dit : Gmail refuse la connexion de [e-mail] (mot de passe d'application "
        "révoqué)"
    )
