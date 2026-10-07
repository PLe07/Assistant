"""`install.sh` et `uninstall.sh` pour de vrai, deux fois chacun, dans un Mac imité :

- un faux `launchctl` qui lance VRAIMENT le démon (`python -m bouclier demon`) et le relance après un `kill`
  (KeepAlive), comme launchd ;
- un dossier personnel jetable (iCloud Drive compris), `uname` = Darwin, `id -u` = 501 ;
- le réseau coupé dans chaque processus Python (sitecustomize) : toute tentative est notée puis refusée.

Sur ton Mac, `install.sh` fait la même chose avec le vrai launchd (P10).
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]

FAUX_LAUNCHCTL = r'''#!/usr/bin/env python3
"""launchd imité : bootstrap lance le programme du plist, print le relance s'il est mort (KeepAlive)."""
import json, os, plistlib, signal, subprocess, sys, time

ETAT = os.environ["FAUX_LAUNCHD"]


def lire():
    try:
        with open(ETAT) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def ecrire(e):
    with open(ETAT, "w") as f:
        json.dump(e, f)


def vivant(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def lancer(p):
    env = {**os.environ, **p.get("EnvironmentVariables", {}), "PATH": os.environ["PATH"]}
    sortie, erreurs = open(p["StandardOutPath"], "a"), open(p["StandardErrorPath"], "a")
    proc = subprocess.Popen(p["ProgramArguments"], cwd=p.get("WorkingDirectory"), env=env, stdout=sortie,
                            stderr=erreurs, stdin=subprocess.DEVNULL, start_new_session=True)
    with open(ETAT + ".pids", "a") as f:
        f.write(f"{proc.pid}\n")
    return proc.pid


args = sys.argv[1:]
with open(ETAT + ".appels", "a") as f:
    f.write(" ".join(args) + "\n")
e = lire()
commande = args[0] if args else ""
if commande == "list":
    print("PID\tStatus\tLabel")
    for label, s in e.items():
        print(f"{s['pid']}\t0\t{label}")
elif commande == "print":
    label = args[1].rsplit("/", 1)[-1]
    if label not in e:
        print(f'Could not find service "{label}" in domain', file=sys.stderr)
        sys.exit(113)
    s = e[label]
    if not vivant(s["pid"]):
        s["pid"], s["relances"] = lancer(s["plist"]), s.get("relances", 0) + 1
        ecrire(e)
    print(f"{args[1]} = {{\n\tstate = running\n\tpid = {s['pid']}\n\tlast exit code = 0\n}}")
elif commande == "bootstrap":
    with open(args[2], "rb") as f:
        p = plistlib.load(f)
    if p["Label"] in e:
        print("Bootstrap failed: 5: Input/output error", file=sys.stderr)
        sys.exit(5)
    e[p["Label"]] = {"plist": p, "pid": lancer(p)}
    ecrire(e)
elif commande == "bootout":
    label = args[1].rsplit("/", 1)[-1]
    if label not in e:
        sys.exit(3)
    pid = e.pop(label)["pid"]
    ecrire(e)
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    for _ in range(150):
        if not vivant(pid):
            break
        time.sleep(0.1)
elif commande not in ("enable", "disable"):
    sys.exit(64)
'''

SITECUSTOMIZE = r'''
"""Mac imité pour les processus Python lancés par install.sh : platform.system() = Darwin, réseau coupé et noté."""
import os, platform, socket

platform.system = lambda: "Darwin"
_JOURNAL = os.environ["BOUCLIER_TEST_RESEAU"]


def _noter(quoi):
    with open(_JOURNAL, "a") as f:
        f.write(f"{quoi}\n")


def _getaddrinfo(hote, *a, **k):
    _noter(hote)
    raise socket.gaierror(socket.EAI_NONAME, "réseau coupé par le test")


_connect = socket.socket.connect


def _connecter(self, adresse):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _noter(adresse[0])
        raise OSError("réseau coupé par le test")
    return _connect(self, adresse)


socket.getaddrinfo = _getaddrinfo
socket.socket.connect = _connecter
'''

CALES = {
    "launchctl": FAUX_LAUNCHCTL,
    "uname": '#!/bin/sh\n[ "$1" = "-s" ] && echo Darwin || echo "Darwin Kernel"\n',
    "id": '#!/bin/sh\ncase "$1" in -u) echo 501 ;; -un) echo camille ;; *) echo "uid=501(camille)" ;; esac\n',
    "osascript": '#!/bin/sh\necho "$@" >> "$FAUX_LAUNCHD.notifications"\n',
    "security": "#!/bin/sh\nexit 44\n",
    "brctl": "#!/bin/sh\nexit 0\n",
    "claude": '#!/bin/sh\necho "$@" >> "$FAUX_LAUNCHD.claude"\nexit 1\n',
    "open": "#!/bin/sh\nexit 0\n",
}


@pytest.fixture
def mac_imite(tmp_path: Path) -> dict[str, str]:
    if not (RACINE / ".venv" / "bin" / "python").exists():
        pytest.skip("pas de .venv : ce test lance les vrais scripts avec l'environnement de Bouclier")
    maison = tmp_path / "maison"
    (maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs").mkdir(parents=True)
    support = maison / "Library" / "Application Support" / "Bouclier"
    support.mkdir(parents=True)
    (support / "config.toml").write_text("[ia]\nactive = false\n", encoding="utf-8")
    cales = tmp_path / "cales"
    cales.mkdir()
    for nom, contenu in CALES.items():
        (cales / nom).write_text(contenu, encoding="utf-8")
        (cales / nom).chmod(0o755)
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    # Les paquets sont déjà installés dans .venv : install.sh ne repasse pas par pip (réseau).
    tampon = RACINE / ".venv" / ".bouclier-installe"
    empreinte = hashlib.sha256((RACINE / "pyproject.toml").read_bytes()).hexdigest()
    if not tampon.exists() or tampon.read_text().strip() != empreinte:
        tampon.write_text(empreinte + "\n")
    env = {
        "PATH": f"{cales}:{os.environ['PATH']}",
        "HOME": str(maison),
        "BOUCLIER_MAISON": str(maison),
        "USER": "camille",
        "LOGNAME": "camille",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(site),
        "FAUX_LAUNCHD": str(tmp_path / "launchd.json"),
        "BOUCLIER_TEST_RESEAU": str(tmp_path / "reseau.txt"),
        "BOUCLIER_INTEGRITE_MAC": str(tmp_path / "integrite"),
        "PYTHON": sys.executable,
    }
    yield env
    pids = Path(env["FAUX_LAUNCHD"] + ".pids")
    for ligne in pids.read_text().split() if pids.exists() else []:
        try:
            os.killpg(int(ligne), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _lancer(script: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(RACINE / script), *args], cwd=RACINE, env=env, capture_output=True, text=True,
                          timeout=300)  # fmt: skip


def _vivant(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def test_install_et_uninstall_pour_de_vrai_deux_fois(mac_imite: dict[str, str]) -> None:
    env = mac_imite
    maison = Path(env["HOME"])
    support = maison / "Library" / "Application Support" / "Bouclier"
    icloud = maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Bouclier"
    agent = maison / "Library" / "LaunchAgents" / "com.camille.bouclier.plist"

    premier = _lancer("install.sh", env)
    sortie = premier.stdout + premier.stderr
    assert premier.returncode == 0, sortie[-3000:]
    assert "launchctl print : com.camille.bouclier tourne (pid" in sortie
    assert "relancé par launchd en" in sortie  # kill puis relance
    assert "texte déposé dans iCloud : réponse du démon en" in sortie
    assert "fichiers de test retirés d'iCloud" in sortie
    assert "premier tour de surveillance terminé en" in sortie  # bilan de doctor fait après le premier tour
    assert "✅ démon : com.camille.bouclier tourne" in sortie  # doctor
    assert sortie.count("INTÉGRITÉ OK") >= 2 and "✅ Bouclier est installé" in sortie

    etat = json.loads(Path(env["FAUX_LAUNCHD"]).read_text())
    assert etat["com.camille.bouclier"]["relances"] == 1 and _vivant(etat["com.camille.bouclier"]["pid"])
    with agent.open("rb") as f:
        assert plistlib.load(f)["ProgramArguments"][1:] == ["-m", "bouclier", "demon"]
    assert (maison / ".local" / "bin" / "bouclier").exists()
    assert sorted(p.name for p in (icloud / "entree").iterdir()) == []  # rien ne reste des essais
    assert sorted(p.name for p in (icloud / "reponses").iterdir()) == []
    cx = sqlite3.connect(support / "bouclier.db")
    assert cx.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0  # ni trace dans l'historique
    cx.close()
    notifications = Path(env["FAUX_LAUNCHD"] + ".notifications")
    assert not notifications.exists() or "test" not in notifications.read_text()
    assert not Path(env["FAUX_LAUNCHD"] + ".claude").exists()  # IA coupée dans config.toml : jamais appelée
    reseau = Path(env["BOUCLIER_TEST_RESEAU"])
    hotes = set(reseau.read_text().split()) if reseau.exists() else set()
    from bouclier import reseau as liste_blanche

    assert all(liste_blanche.hote_autorise(h) for h in hotes), hotes  # seules des adresses permises sont tentées
    journaux = list((maison / "Library" / "Logs" / "Bouclier").glob("installation-*.log"))
    assert len(journaux) == 1 and "✅ Bouclier est installé" in journaux[0].read_text(encoding="utf-8")

    # Relancé : rien ne casse, l'ancienne version est arrêtée proprement.
    second = _lancer("install.sh", env)
    sortie2 = second.stdout + second.stderr
    assert second.returncode == 0, sortie2[-3000:]
    assert "déjà à jour" in sortie2 and "ancienne version arrêtée" in sortie2
    pid = json.loads(Path(env["FAUX_LAUNCHD"]).read_text())["com.camille.bouclier"]["pid"]

    # Désinstallation, deux fois ; les données restent ; puis --tout.
    for _ in range(2):
        r = _lancer("uninstall.sh", env)
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
        assert "INTÉGRITÉ OK" in r.stdout and "✅ Bouclier est retiré" in r.stdout
    deadline = time.time() + 10
    while _vivant(pid) and time.time() < deadline:
        time.sleep(0.1)
    assert not _vivant(pid) and json.loads(Path(env["FAUX_LAUNCHD"]).read_text()) == {}
    assert not agent.exists() and not (maison / ".local" / "bin" / "bouclier").exists()
    assert support.exists() and icloud.exists()
    r = _lancer("uninstall.sh", env, "--tout")
    assert r.returncode == 0 and not support.exists() and icloud.exists()
    assert _lancer("uninstall.sh", env, "--n-importe-quoi").returncode == 1


def test_install_refuse_root_et_linux(tmp_path: Path) -> None:
    cales = tmp_path / "cales"
    cales.mkdir()
    (cales / "id").write_text("#!/bin/sh\necho 0\n", encoding="utf-8")
    (cales / "id").chmod(0o755)
    env = {**os.environ, "PATH": f"{cales}:{os.environ['PATH']}", "HOME": str(tmp_path)}
    for script in ("install.sh", "uninstall.sh"):
        r = _lancer(script, env)
        assert r.returncode == 1 and "sudo" in r.stdout
    (cales / "id").write_text("#!/bin/sh\necho 501\n", encoding="utf-8")
    r = _lancer("install.sh", env)
    assert r.returncode == 1 and "Mac" in r.stdout and not (tmp_path / "Library").exists()
