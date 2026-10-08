"""Le harnais du faux écosystème (§9.1) : un bac à sable, 7 faux modules (vrais processus) et un module absent, un
launchd (faux ici, le vrai sur ton Mac avec `TDB_VRAI_LAUNCHD=1`), et le **vrai démon** du tableau de bord lancé
comme sur ton Mac (`tableau demon`), avec un espion d'audit dans son processus.

Le nettoyage (`arreter`) est appelé dans un bloc `finally` : démon arrêté, faux modules arrêtés (ou `bootout` des
agents `com.<toi>.tdbtest.*`), puis le test supprime le bac à sable et vérifie qu'il ne reste aucun processus.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau import registre
from tableau.module import Attente, DefModule

ICI = Path(__file__).resolve().parent
RACINE_PROJET = ICI.parents[1]
# Comme les vrais agents : com.<ta session>.tdbtest.* (le vrai tableau de bord, s'il est installé, les ignore).
PREFIXE = re.sub(r"[^a-z0-9_-]", "", getpass.getuser().lower()) or "moi"
NOMS = {
    "sain": "Sain",
    "boucle": "Boucle",
    "file": "File",
    "erreurs": "Erreurs",
    "budget": "Budget",
    "attente": "Attente",
    "processeur": "Processeur",
}
COMPORTEMENT_INITIAL = {"sain": "sain", "boucle": "boucle", "file": "file", "erreurs": "erreurs", "budget": "sain",
                        "attente": "attente", "processeur": "cpu"}  # fmt: skip


def label(nom: str) -> str:
    return f"com.{PREFIXE}.tdbtest.{nom}"


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class Agent:
    label: str
    programme: list[str]
    garder_en_vie: bool
    sortie: Path
    proc: subprocess.Popen[bytes] | None = None
    runs: int = 0
    statut: int = 0
    relance_a: float | None = None


class FauxLaunchd:
    """KeepAlive et ThrottleInterval comme launchd ; l'état est publié pour le faux `launchctl` (lecture seule)."""

    def __init__(self, fichier_etat: Path, delai_relance_s: float = 2.0) -> None:
        self.fichier_etat = fichier_etat
        self.delai = delai_relance_s
        self.agents: dict[str, Agent] = {}
        self._verrou = threading.Lock()
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._surveiller, daemon=True)
        self._publier()

    def charger(self, plist: Path) -> None:
        d = plistlib.loads(plist.read_bytes())
        a = Agent(d["Label"], list(d["ProgramArguments"]), bool(d.get("KeepAlive")), Path(d["StandardErrorPath"]))
        with self._verrou:
            self.agents[a.label] = a
            self._lancer(a)
            self._publier()
        if not self._fil.is_alive():
            self._fil.start()

    def _lancer(self, a: Agent) -> None:
        a.sortie.parent.mkdir(parents=True, exist_ok=True)
        with open(a.sortie, "ab") as sortie:
            a.proc = subprocess.Popen(a.programme, stdout=sortie, stderr=sortie, stdin=subprocess.DEVNULL,
                                      start_new_session=True)  # fmt: skip
        a.runs += 1
        a.relance_a = None

    def _surveiller(self) -> None:
        while not self._arret.wait(0.2):
            with self._verrou:
                change = False
                for a in self.agents.values():
                    if a.proc is not None and a.proc.poll() is not None:
                        a.statut = a.proc.returncode
                        a.proc = None
                        a.relance_a = time.monotonic() + self.delai if a.garder_en_vie else None
                        change = True
                    elif a.proc is None and a.relance_a is not None and time.monotonic() >= a.relance_a:
                        self._lancer(a)
                        change = True
                if change:
                    self._publier()

    def _publier(self) -> None:
        etat = {
            a.label: {"pid": a.proc.pid if a.proc else None, "statut": a.statut, "runs": a.runs}
            for a in self.agents.values()
        }
        temporaire = self.fichier_etat.with_suffix(".tmp")
        temporaire.write_text(json.dumps(etat), encoding="utf-8")
        temporaire.replace(self.fichier_etat)

    def pids(self) -> list[int]:
        with self._verrou:
            return [a.proc.pid for a in self.agents.values() if a.proc is not None]

    def arreter_tout(self) -> None:
        self._arret.set()
        if self._fil.is_alive():
            self._fil.join(timeout=5)
        for a in self.agents.values():
            if a.proc is not None and a.proc.poll() is None:
                try:
                    os.killpg(a.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for a in self.agents.values():
            if a.proc is not None:
                try:
                    a.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(a.proc.pid, signal.SIGKILL)
                    a.proc.wait(timeout=10)


class VraiLaunchd:  # pragma: no cover - sur ton Mac seulement (TDB_VRAI_LAUNCHD=1)
    """De vrais LaunchAgents de test `com.<toi>.tdbtest.*` : bootstrap au départ, bootout dans le `finally`."""

    def __init__(self) -> None:
        self.domaine = f"gui/{os.getuid()}"
        self.labels: list[str] = []

    def charger(self, plist: Path) -> None:
        d = plistlib.loads(plist.read_bytes())
        subprocess.run(["launchctl", "bootstrap", self.domaine, str(plist)], check=True, capture_output=True)
        self.labels.append(d["Label"])

    def pids(self) -> list[int]:
        pids = []
        for lab in self.labels:
            r = subprocess.run(["launchctl", "list", lab], capture_output=True, text=True)
            for ligne in r.stdout.splitlines():
                if '"PID"' in ligne:
                    pids.append(int(ligne.split("=")[1].strip(" ;")))
        return pids

    def arreter_tout(self) -> None:
        for lab in self.labels:
            subprocess.run(["launchctl", "bootout", f"{self.domaine}/{lab}"], capture_output=True)
        fin = time.monotonic() + 20
        while time.monotonic() < fin and any(
            subprocess.run(["launchctl", "print", f"{self.domaine}/{lab}"], capture_output=True).returncode == 0
            for lab in self.labels
        ):
            time.sleep(0.5)


@dataclass
class Ecosysteme:
    racine: Path
    reglages: dict[str, dict[str, Any]] = field(default_factory=dict)
    demon: subprocess.Popen[bytes] | None = None
    launchd: Any = None
    t0: float = 0.0
    heure_brief: str = ""

    @property
    def maison(self) -> Path:
        return self.racine / "maison"

    @property
    def modules(self) -> Path:
        return self.maison / "Modules"

    @property
    def support(self) -> Path:
        return self.maison / "Library" / "Application Support" / "TableauDeBord"

    @property
    def espion(self) -> Path:
        return self.racine / "espion.txt"

    def dossier(self, nom: str) -> Path:
        return self.modules / nom

    # --- préparation -----------------------------------------------------------------------------------------------

    def preparer(self) -> None:
        agents = self.maison / "Library" / "LaunchAgents"
        agents.mkdir(parents=True)
        (self.racine / "icloud").mkdir()
        self.support.mkdir(parents=True)
        for nom in NOMS:
            d = self.dossier(nom)
            (d / "code").mkdir(parents=True)
            shutil.copy(ICI / "faux_module.py", d / "code" / "faux_module.py")
            (d / "code" / "config.toml").write_text(f'nom = "{nom}"\n', encoding="utf-8")
            (d / "comportement").write_text(COMPORTEMENT_INITIAL[nom], encoding="utf-8")
            for sous in ("donnees", "logs", "entree"):
                (d / sous).mkdir()
            with open(agents / f"{label(nom)}.plist", "wb") as f:
                plistlib.dump({
                    "Label": label(nom), "ProgramArguments": [sys.executable, str(d / "code" / "faux_module.py"),
                                                                str(d)],
                    "KeepAlive": True, "RunAtLoad": True, "ThrottleInterval": 2, "ProcessType": "Background",
                    "StandardErrorPath": str(d / "logs" / "launchd.erreurs.log"),
                    "StandardOutPath": str(d / "logs" / "launchd.erreurs.log"),
                }, f)  # fmt: skip
        (self.dossier("budget") / "budget_cible").write_text("0.85", encoding="utf-8")
        # Le brief « attendu » à la minute qui suit le départ (au moins 15 s après) : il ne viendra jamais.
        echeance = time.localtime(time.time() + 75)
        self.heure_brief = f"{echeance.tm_hour:02d}:{echeance.tm_min:02d}"
        (self.support / "modules.toml").write_text(registre.ecrire(self.definitions()), encoding="utf-8")
        (self.support / "reglages.toml").write_text(self.reglages_toml(), encoding="utf-8")

    def definitions(self) -> list[DefModule]:
        defs = []
        for nom, titre in NOMS.items():
            base = f"~/Modules/{nom}"
            attentes = [Attente("travail", "periodique", "travail chaque minute", toutes_les_min=1, tolerance_min=2)]
            if nom == "attente":
                attentes.append(Attente("brief", "quotidienne", f"brief chaque jour vers {self.heure_brief}",
                                        heure=self.heure_brief, tolerance_min=0))  # fmt: skip
            defs.append(DefModule(
                id=f"tdbtest-{nom}", nom=titre, emoji="🧪", adaptateur="tolerant", labels=[label(nom)],
                dossier_projet=base, dossier_donnees=f"{base}/donnees", dossier_logs=f"{base}/logs",
                files=[f"{base}/entree"] if nom == "file" else [], file_max_min=1 if nom == "file" else None,
                perimetre_code=["code"], doit_tourner=True, plafond_usd=1.0, attentes=attentes, attendu=True,
                aide=f"tdbtest {nom} doctor",
            ))  # fmt: skip
        defs.append(DefModule(id="tdbtest-absent", nom="Absent", emoji="🧪", adaptateur="tolerant",
                              labels=[label("absent")], attendu=True))  # fmt: skip
        return defs

    def reglages_toml(self) -> str:
        valeurs: dict[str, dict[str, Any]] = {
            "installation": {"prefixe_label": PREFIXE},
            "serveur": {"port": port_libre()},
            "alertes": {"max_par_jour": 100, "silence_debut": 0, "silence_fin": 0},
        }
        for section, cles in self.reglages.items():
            valeurs.setdefault(section, {}).update(cles)
        lignes = []
        for section, cles in valeurs.items():
            lignes.append(f"[{section}]")
            lignes += [f"{k} = {json.dumps(v)}" for k, v in cles.items()]
            lignes.append("")
        return "\n".join(lignes)

    # --- marche et arrêt -------------------------------------------------------------------------------------------

    def demarrer(self) -> None:
        etat = self.racine / "etat_launchd.json"
        vrai = os.environ.get("TDB_VRAI_LAUNCHD") == "1" and sys.platform == "darwin"
        self.launchd = VraiLaunchd() if vrai else FauxLaunchd(etat)
        for plist in sorted((self.maison / "Library" / "LaunchAgents").glob("*.plist")):
            self.launchd.charger(plist)
        env = {
            **os.environ,
            "TABLEAU_MAISON": str(self.maison),
            "TABLEAU_ICLOUD": str(self.racine / "icloud"),
            "TABLEAU_NOTIFICATIONS": "coupees",
            "TABLEAU_INCLURE_TESTS": "1",
            "TDB_ETAT_LAUNCHD": str(etat),
            "TDB_ESPION_RACINE": str(self.modules),
            "TDB_ESPION_SORTIE": str(self.espion),
            "PYTHONPATH": str(RACINE_PROJET),
            "PATH": (os.environ.get("PATH", "") if vrai else f"{ICI / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"),
        }
        self.espion.write_text("", encoding="utf-8")
        with open(self.racine / "demon.sortie.log", "ab") as sortie:
            self.demon = subprocess.Popen([sys.executable, str(ICI / "demon_espionne.py")], cwd=RACINE_PROJET,
                                          env=env, stdout=sortie, stderr=sortie, start_new_session=True)  # fmt: skip
        self.t0 = time.time()

    def arreter(self) -> list[int]:
        """Arrête tout ; rend les pids qui étaient en vie (pour vérifier qu'il n'en reste aucun)."""
        pids: list[int] = []
        if self.demon is not None:
            pids.append(self.demon.pid)
            if self.demon.poll() is None:
                self.demon.send_signal(signal.SIGTERM)
                try:
                    self.demon.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(self.demon.pid, signal.SIGKILL)
                    self.demon.wait(timeout=10)
        if self.launchd is not None:
            pids += self.launchd.pids()
            self.launchd.arreter_tout()
        return pids

    # --- lectures --------------------------------------------------------------------------------------------------

    def lire(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Notre base, en lecture seule (le démon l'écrit pendant ce temps : mode WAL)."""
        chemin = self.support / "tableau.db"
        if not chemin.exists():
            return []
        db = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            return list(db.execute(sql, params).fetchall())
        except sqlite3.OperationalError:
            return []
        finally:
            db.close()

    def etats(self) -> dict[str, dict[str, Any]]:
        return {r["module"]: json.loads(r["json"]) for r in self.lire("SELECT module, json FROM etat_modules")}

    def problemes(self) -> list[sqlite3.Row]:
        return self.lire("SELECT * FROM problemes")

    def notifications(self) -> list[sqlite3.Row]:
        return self.lire("SELECT * FROM notifications ORDER BY id")

    def empreintes_code(self) -> dict[str, tuple[str, int]]:
        """sha256 et date de chaque fichier de code et de chaque plist des faux modules."""
        fichiers = [*self.modules.glob("*/code/**/*"), *(self.maison / "Library" / "LaunchAgents").glob("*.plist")]
        return {
            str(p.relative_to(self.maison)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(fichiers)
            if p.is_file()
        }

    def ouverts_chez_les_modules(self) -> list[str]:
        """`lsof` sur le démon : ses fichiers ouverts sous les dossiers des faux modules (doit être vide)."""
        if self.demon is None or self.demon.poll() is not None:
            return []
        r = subprocess.run(["lsof", "-nP", "-p", str(self.demon.pid)], capture_output=True, text=True, timeout=30)
        return [ligne for ligne in r.stdout.splitlines() if str(self.modules) in ligne]

    def verrous_vus_par_les_modules(self) -> list[str]:
        return [f.read_text(encoding="utf-8") for f in self.modules.glob("*/logs/verrous.txt")]
