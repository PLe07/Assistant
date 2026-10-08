"""Un faux Mac pour les tests : ton écosystème (assistant, Corvées, Nettoyeur, Trieur, Bouclier, Quotidien), avec les
schémas exacts de leurs bases (recopiés de leur code, `tests/fixtures/deduites/`, ou capturés pour de vrai,
`tests/fixtures/reelles/`), leurs journaux au bon format, leurs plists et leurs réglages.

Les bases sont écrites en mode WAL et laissées comme un module qui tourne les laisserait.
"""

from __future__ import annotations

import json
import plistlib
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau import config, systeme
from tableau.adaptateurs.contexte import Contexte
from tableau.db import Base
from tableau.decouverte import decouvrir
from tableau.module import DefModule
from tableau.registre import synchroniser
from tableau.sondes.docker_n8n import SondeDocker
from tableau.sondes.launchd import SondeLaunchd
from tableau.sondes.logs import LecteurJournaux
from tableau.sondes.processus import SondeProcessus
from tableau.sondes.sqlite_copie import LecteurBases

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PREFIXE = "exemple"


def base_depuis(chemin: Path, *scripts: str) -> sqlite3.Connection:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(chemin, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    for s in scripts:
        db.executescript(s)
    return db


def schema(nom: str) -> str:
    return (FIXTURES / "deduites" / f"{nom}.schema.sql").read_text()


def reel(nom: str) -> str:
    return (FIXTURES / "reelles" / "conteneur" / nom).read_text()


def ecrire_plist(dossier: Path, label: str, **extra: Any) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{label}.plist"
    with open(chemin, "wb") as f:
        plistlib.dump({"Label": label, **extra}, f)
    return chemin


@dataclass
class FauxLaunchd:
    """`launchctl list` et `print`, au format de macOS, à partir d'un état qu'on change à la main."""

    agents: dict[str, dict[str, Any]] = field(default_factory=dict)  # label → {pid, statut, runs}
    appels: list[tuple[str, ...]] = field(default_factory=list)
    en_panne: bool = False

    def __call__(self, args: list[str]) -> systeme.Resultat:
        systeme.verifier(args)
        self.appels.append(tuple(args))
        if self.en_panne:
            return systeme.Resultat(1, "", "launchctl: panne")
        if args[1] == "list":
            lignes = ["PID\tStatus\tLabel"]
            for label, a in self.agents.items():
                lignes.append(f"{a.get('pid') or '-'}\t{a.get('statut', 0)}\t{label}")
            return systeme.Resultat(0, "\n".join(lignes) + "\n")
        label = args[2].split("/", 2)[-1]
        a = self.agents.get(label)
        if a is None:
            return systeme.Resultat(113, "", f'Could not find service "{label}" in domain for port')
        pid = a.get("pid")
        texte = f"gui/501/{label} = {{\n\tstate = {'running' if pid else 'not running'}\n\truns = {a.get('runs', 1)}\n"
        if pid:
            texte += f"\tpid = {pid}\n"
        texte += (
            f"\tlast exit code = {a.get('statut', 0) if a.get('runs', 1) > 1 or not pid else '(never exited)'}\n}}\n"
        )
        return systeme.Resultat(0, texte)


@dataclass
class FauxDocker:
    conteneurs: dict[str, dict[str, Any]] = field(default_factory=dict)
    eteint: bool = False

    def __call__(self, args: list[str]) -> systeme.Resultat:
        systeme.verifier(args)
        if self.eteint:
            return systeme.Resultat(1, "", "Cannot connect to the Docker daemon at unix:///var/run/docker.sock.")
        if args[1] == "ps" and "{{json .}}" in args:
            return systeme.Resultat(
                0, "".join(json.dumps({"Names": n, **c}) + "\n" for n, c in self.conteneurs.items())
            )
        if args[1] == "ps":
            return systeme.Resultat(0, "".join(f"{n}\t{c.get('Image', '')}\n" for n, c in self.conteneurs.items()))
        if args[1] == "inspect":
            c = self.conteneurs.get(args[2], {})
            return systeme.Resultat(
                0, json.dumps([{"State": {"Status": c.get("State", "running")}, "RestartCount": 0}])
            )
        return systeme.Resultat(0, json.dumps({"CPUPerc": "0.80%", "MemUsage": "200MiB / 8GiB"}))


@dataclass
class FauxMac:
    maison: Path
    maintenant: float
    launchd: FauxLaunchd
    docker: FauxDocker
    ecrivains: list[sqlite3.Connection] = field(default_factory=list)
    bases: dict[str, sqlite3.Connection] = field(default_factory=dict)

    def vivre(self, maintenant: float) -> None:
        """Les modules font leur travail à `maintenant` : battements, relève Gmail, relevés du Nettoyeur."""
        b = self.bases
        if "etat" in b:
            b["etat"].execute("UPDATE cles SET valeur = ?, maj = ? WHERE cle = 'superviseur_vivant'",
                              (str(maintenant), maintenant))  # fmt: skip
            b["etat"].execute("UPDATE modules SET maj = ?", (maintenant,))
        if "corvees" in b:
            b["corvees"].execute("UPDATE etat SET valeur = ?, maj = ? WHERE cle = 'battement'",
                                 (json.dumps(maintenant), maintenant))  # fmt: skip
        if "nettoyeur" in b:
            b["nettoyeur"].execute("UPDATE etat SET valeur = ? WHERE cle = 'battement'", (json.dumps(maintenant),))
            b["nettoyeur"].execute("INSERT OR IGNORE INTO releves VALUES (?, 'normal', 3.5)", (maintenant,))
        for nom in ("bouclier", "quotidien"):
            if nom in b:
                b[nom].execute("UPDATE meta SET valeur = ? WHERE cle = 'demon_battement'", (str(maintenant),))
        if "bouclier" in b:
            b["bouclier"].execute("UPDATE meta SET valeur = ? WHERE cle = 'gmail_releve_le'", (str(maintenant),))

    @property
    def assistant(self) -> Path:
        return self.maison / "Assistant"

    @property
    def support(self) -> Path:
        return self.maison / "Library" / "Application Support"

    @property
    def journaux(self) -> Path:
        return self.maison / "Library" / "Logs"

    @property
    def icloud(self) -> Path:
        return self.maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs"

    def fermer(self) -> None:
        for e in self.ecrivains:
            e.close()


def date(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def faux_mac(maison: Path, maintenant: float, complet: bool = True) -> FauxMac:
    """L'écosystème installé, en bonne santé, à `maintenant`."""
    m = FauxMac(maison, maintenant, FauxLaunchd(), FauxDocker())
    a = m.assistant
    for nom in ("mails", "corvees", "demarrage", "trieur"):
        (a / "modules" / nom).mkdir(parents=True, exist_ok=True)
    (a / "modules" / "mails" / "tri.py").write_text("# tri\n")
    (a / "modules" / "trieur" / "config.py").write_text("SEUIL = 0.75\n")
    (a / "trieur.py").write_text("# trieur\n")
    (a / "assistant.py").write_text("# assistant\n")
    (a / ".git").mkdir()
    reglages = {
        "claude": {"appels_max_par_jour": 60},
        "modules": {
            "mails": {"actif": True},
            "corvees": {"actif": True, "ia": {"budget_mensuel_usd": 2.0}, "analyse": {"heure": "21:00"}},
            "demarrage": {"actif": True},
            "trieur": {"actif": True, "ia": {"budget_mensuel_usd": 1.0}},
        },
    }
    (a / "reglages.json").write_text(json.dumps(reglages))
    (a / "logs").mkdir()
    (a / "logs" / "assistant.log").write_text(
        f"{date(maintenant - 300)} INFO    [superviseur] Superviseur démarré (pid 512)\n"
        f"{date(maintenant - 200)} INFO    [trieur] facture.pdf → Factures/2026 (facture_achat, 0.86)\n"
        f"{date(maintenant - 100)} INFO    [corvees] Détecteur de corvées : 6 capteurs\n"
        f"{date(maintenant - 90)} INFO    [demarrage] relevé fait\n"
        f"{date(maintenant - 60)} INFO    [mails] Passage terminé : 2 mail(s) trié(s)\n"
    )
    agents = m.maison / "Library" / "LaunchAgents"
    py = str(a / ".venv" / "bin" / "python")
    ecrire_plist(agents, "com.assistant.superviseur", ProgramArguments=[py, str(a / "superviseur.py")],
                 WorkingDirectory=str(a), KeepAlive=True, RunAtLoad=True,
                 StandardErrorPath=str(a / "logs" / "superviseur.launchd.log"))  # fmt: skip
    ecrire_plist(agents, "com.assistant.icone", ProgramArguments=[py, str(a / "menubar.py")],
                 WorkingDirectory=str(a), KeepAlive={"SuccessfulExit": False})  # fmt: skip
    m.launchd.agents["com.assistant.superviseur"] = {"pid": 2**22 + 512, "statut": 0, "runs": 1}
    m.launchd.agents["com.assistant.icone"] = {"pid": 2**22 + 513, "statut": 0, "runs": 1}
    # etat.db : le schéma réel capturé, et ce que le superviseur y écrit.
    etat = base_depuis(a / "donnees" / "etat.db", "\n".join(
        ligne for ligne in reel("assistant-etat.sql").splitlines() if not ligne.startswith("INSERT")))  # fmt: skip
    etat.execute("INSERT INTO cles VALUES ('superviseur_vivant', ?, ?)", (str(maintenant - 2), maintenant - 2))
    for nom in ("mails", "corvees", "demarrage", "trieur", "battement"):
        etat.execute("INSERT INTO modules VALUES (?, 'actif', '', ?, 0, ?)", (nom, 2**22 + 600, maintenant - 2))
    etat.execute("INSERT INTO appels_claude (quand, module, modele, ok, tokens_entree, tokens_sortie, erreur) VALUES "
                 "(?, 'mails', 'sonnet', 1, 100000, 20000, ''), (?, 'mails', 'haiku', 1, 50000, 5000, ''), "
                 "(?, 'mails', 'sonnet', 0, 999999, 0, 'panne')",
                 (maintenant - 3600, maintenant - 60, maintenant - 30))  # fmt: skip
    m.ecrivains.append(etat)
    m.bases["etat"] = etat
    mails = base_depuis(a / "donnees" / "mails" / "memoire.db", schema("mails"))
    mails.execute("INSERT INTO mails (id, statut, traite_le) VALUES ('m1', 'trie', ?)",
                  (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(maintenant - 120)),))  # fmt: skip
    m.ecrivains.append(mails)
    # Trieur : le schéma réel capturé.
    trieur = base_depuis(a / "donnees" / "trieur" / "trieur.db", "\n".join(
        ligne for ligne in reel("trieur-trieur.sql").splitlines() if not ligne.startswith("INSERT")))  # fmt: skip
    trieur.execute("INSERT INTO elements (chemin, nom, source, etat, ajoute, traite, type) VALUES "
                   "('/x/a.pdf', 'a.pdf', 'boite', 'classe', ?, ?, 'facture_achat')", (maintenant - 7300, maintenant - 7200))  # fmt: skip
    trieur.execute("INSERT INTO depenses_ia (quand, mois, cout_usd) VALUES (?, ?, 0.12), (?, '2020-01', 5)",
                   (maintenant - 50, time.strftime("%Y-%m", time.localtime(maintenant)), maintenant - 10**8))  # fmt: skip
    m.ecrivains.append(trieur)
    m.bases["trieur"] = trieur
    corvees = base_depuis(a / "donnees" / "corvees" / "corvees.db", schema("corvees"))
    corvees.execute("INSERT INTO etat VALUES ('battement', ?, ?)", (json.dumps(maintenant - 30), maintenant - 30))
    corvees.execute("INSERT INTO etat VALUES ('derniere_analyse', ?, ?)", (json.dumps(maintenant - 13 * 3600), 0))
    corvees.execute("INSERT INTO couts (quand, mois, cout_usd, ok) VALUES (?, ?, 0.30, 1)",
                    (maintenant - 86400, time.strftime("%Y-%m", time.localtime(maintenant))))  # fmt: skip
    m.ecrivains.append(corvees)
    m.bases["corvees"] = corvees
    nettoyeur = base_depuis(a / "donnees" / "demarrage" / "demarrage.db", schema("nettoyeur"))
    nettoyeur.execute("INSERT INTO etat VALUES ('battement', ?)", (json.dumps(maintenant - 40),))
    nettoyeur.execute("INSERT INTO releves VALUES (?, 'normal', 3.5)", (maintenant - 60,))
    nettoyeur.execute("INSERT INTO scans VALUES (1, ?, '{}')", (maintenant - 5 * 3600,))
    m.ecrivains.append(nettoyeur)
    m.bases["nettoyeur"] = nettoyeur
    for d in ("BoiteMac", "Bouclier/entree", "Quotidien/entree"):
        (m.icloud / d).mkdir(parents=True, exist_ok=True)
    if complet:
        _bouclier(m, agents)
        _quotidien(m, agents)
    return m


def _bouclier(m: FauxMac, agents: Path) -> None:
    projet = m.assistant / "bouclier"
    (projet / "bouclier").mkdir(parents=True)
    (projet / "bouclier" / "daemon.py").write_text("# démon\n")
    logs = m.journaux / "Bouclier"
    logs.mkdir(parents=True)
    ecrire_plist(agents, f"com.{PREFIXE}.bouclier",
                 ProgramArguments=[str(projet / ".venv" / "bin" / "python"), "-m", "bouclier", "demon"],
                 KeepAlive=True, RunAtLoad=True, StandardOutPath=str(logs / "demon.sortie.log"),
                 StandardErrorPath=str(logs / "demon.erreurs.log"))  # fmt: skip
    m.launchd.agents[f"com.{PREFIXE}.bouclier"] = {"pid": 2**22 + 700, "statut": 0, "runs": 1}
    (logs / "bouclier.log").write_text(f"{date(m.maintenant - 50)},123 INFO [daemon] relève Gmail : 3 messages\n")
    (logs / "demon.erreurs.log").write_text("")
    support = m.support / "Bouclier"
    support.mkdir(parents=True)
    (support / "config.toml").write_text(
        "[ia]\nbudget_mensuel_usd = 2.0\n[gmail]\nactive = true\nintervalle_minutes = 5\n"
    )
    (support / "etat.json").write_text(json.dumps({"hygiene": {"score": 72}, "arnaques_7_jours": 1}))
    db = base_depuis(support / "bouclier.db", schema("bouclier"))
    db.execute("INSERT INTO meta VALUES ('demon_battement', ?)", (str(m.maintenant - 20),))
    db.execute("INSERT INTO meta VALUES ('gmail_releve_le', ?)", (str(m.maintenant - 120),))
    db.execute("INSERT INTO depenses_ia (date, mois, cout_usd, jetons_entree, jetons_sortie, usage) VALUES "
               "(?, ?, 0.40, 1000, 100, 'arnaque')", (m.maintenant - 3600, time.strftime("%Y-%m", time.localtime(m.maintenant))))  # fmt: skip
    m.ecrivains.append(db)
    m.bases["bouclier"] = db


def _quotidien(m: FauxMac, agents: Path) -> None:
    projet = m.assistant / "quotidien"
    (projet / "quotidien").mkdir(parents=True)
    (projet / "quotidien" / "brief.py").write_text("# brief\n")
    logs = m.journaux / "Quotidien"
    logs.mkdir(parents=True)
    ecrire_plist(agents, f"com.{PREFIXE}.quotidien",
                 ProgramArguments=[str(projet / ".venv" / "bin" / "python"), "-m", "quotidien", "demon"],
                 KeepAlive=True, StandardErrorPath=str(logs / "demon.erreurs.log"))  # fmt: skip
    m.launchd.agents[f"com.{PREFIXE}.quotidien"] = {"pid": 2**22 + 800, "statut": 0, "runs": 1}
    (logs / "quotidien.log").write_text(f"{date(m.maintenant - 40)},500 INFO brief envoyé\n")
    support = m.support / "Quotidien"
    support.mkdir(parents=True)
    (support / "reglages.toml").write_text('[heures]\nbrief = "07:15"\n[ia]\nbudget_mensuel_usd = 2.0\n')
    db = base_depuis(support / "quotidien.db", schema("quotidien"))
    db.execute("INSERT INTO meta VALUES ('demon_battement', ?)", (str(m.maintenant - 10),))
    db.execute("INSERT INTO taches VALUES ('brief', '2026-10-07', ?, 'ok')", (m.maintenant - 3 * 3600,))
    db.execute("INSERT INTO depenses_ia (date, mois, cout_usd, jetons_entree, jetons_sortie, usage) VALUES "
               "(?, ?, 0.05, 100, 10, 'frigo')", (m.maintenant - 60, time.strftime("%Y-%m", time.localtime(m.maintenant))))  # fmt: skip
    m.ecrivains.append(db)
    m.bases["quotidien"] = db


def contexte(
    mac: FauxMac,
    base: Base,
    horloge: Callable[[], float],
    modules: list[DefModule] | None = None,
    healthz: Callable[[int], tuple[bool, str]] = lambda port: (True, "HTTP 200 ok"),
) -> Contexte:
    chemins = config.Chemins(mac.maison)
    reglages = config.charger(chemins.reglages)
    reglages.valeurs["installation"]["prefixe_label"] = PREFIXE
    docker = SondeDocker(mac.docker, horloge=horloge)
    if modules is None:
        decouverte = decouvrir(chemins, docker)
        modules, _, _ = synchroniser(chemins.registre, PREFIXE, decouverte, chemins.maison)
    ctx = Contexte(
        chemins=chemins,
        reglages=reglages,
        base=base,
        launchd=SondeLaunchd(mac.launchd, uid=501, horloge=horloge),
        processus=SondeProcessus(),
        journaux=LecteurJournaux(base, horloge),
        bases=LecteurBases(chemins.copies, intervalle_s=0, horloge=horloge, dormir=lambda _s: None),
        docker=docker,
        horloge=horloge,
        healthz=healthz,
        modules=modules,
    )
    ctx.nouveau_tour(mesurer_tailles=True)
    return ctx
