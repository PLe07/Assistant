"""§9.5 — le bout en bout sur ton vrai Mac, avec SEULEMENT deux éléments de test créés ici (D-03, D-09) :
com.assistant.nettoyeur.test.charge (≈ 25 % d'un cœur + caffeinate) et com.assistant.nettoyeur.test.orphelin
(programme inexistant, jamais chargé). Rien d'autre n'est désactivé ni modifié. Le nettoyage tourne même si le test
échoue, puis une recherche automatique vérifie qu'il ne reste aucune trace.

    cd ~/Assistant && .venv/bin/python -m pytest tests/demarrage/e2e_mac -q -s

Ce n'est pas dans check.sh : il faut le vrai launchd. Ailleurs que sur macOS, il échoue franchement (jamais sauté).
"""

from __future__ import annotations

import os
import plistlib
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from modules.demarrage import cli, config, travail
from modules.demarrage.systeme import Mac

PREFIXE = "com.assistant.nettoyeur.test."
CHARGE, ORPHELIN = PREFIXE + "charge", PREFIXE + "orphelin"
AGENTS = Path.home() / "Library" / "LaunchAgents"
AGENT = Path(__file__).with_name("agent_charge.py")
UID = os.getuid()


def launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=20)


def charge(label: str) -> bool:
    return launchctl("print", f"gui/{UID}/{label}").returncode == 0


def desactive(label: str) -> bool:
    sortie = launchctl("print-disabled", f"gui/{UID}").stdout
    return any(f'"{label}" => disabled' in ligne or f'"{label}" => true' in ligne for ligne in sortie.splitlines())


def etat_brut(label: str) -> str:
    """Ce que launchd dit vraiment (affiché seulement si une vérification échoue)."""
    service = launchctl("print", f"gui/{UID}/{label}")
    desactives = [ligne.strip() for ligne in launchctl("print-disabled", f"gui/{UID}").stdout.splitlines()
                  if PREFIXE in ligne]  # fmt: skip
    debut = "\n".join(service.stdout.splitlines()[:12]) or service.stderr.strip()
    return f"\nprint (code {service.returncode}) :\n{debut}\nprint-disabled : {desactives}\n"


def traces() -> list[str]:
    """Tout ce qui resterait de nos éléments de test : fichiers, launchd, désactivations."""
    restes = [str(p) for p in AGENTS.glob(PREFIXE + "*")]
    restes += [f"chargé : {ligne}" for ligne in launchctl("list").stdout.splitlines() if PREFIXE in ligne]
    restes += [f"désactivé : {ligne.strip()}" for ligne in launchctl("print-disabled", f"gui/{UID}").stdout.splitlines()
               if PREFIXE in ligne and ("disabled" in ligne or "true" in ligne)]  # fmt: skip
    return restes


def nettoyer(trace: Path) -> None:
    launchctl("bootout", f"gui/{UID}/{CHARGE}")
    for label in (CHARGE, ORPHELIN):
        launchctl("enable", f"gui/{UID}/{label}")
        (AGENTS / f"{label}.plist").unlink(missing_ok=True)
    if trace.exists():
        for pid in trace.read_text().split():
            try:
                os.kill(int(pid), signal.SIGTERM)  # l'agent et son caffeinate, s'ils tournent encore
            except (ProcessLookupError, ValueError, PermissionError):
                pass


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMARRAGE_DOSSIER", str(tmp_path / "donnees"))  # tes vraies données ne sont pas touchées
    reglages, _ = config.charger({})
    lignes: list[str] = []
    contexte = cli.Contexte(reglages, Mac(), lambda m: (lignes.append(m), print(m)))
    return contexte, lignes, reglages


def test_bout_en_bout_sur_le_mac(ctx, tmp_path):
    assert sys.platform == "darwin", "Ce test demande le vrai launchd de macOS."
    contexte, lignes, reglages = ctx
    trace = tmp_path / "pids.txt"
    assert not traces(), f"Des restes d'un essai précédent : {traces()}"
    try:
        AGENTS.mkdir(parents=True, exist_ok=True)
        (AGENTS / f"{CHARGE}.plist").write_bytes(plistlib.dumps({
            "Label": CHARGE, "RunAtLoad": True,
            "ProgramArguments": ["/usr/bin/nice", "-n", "10", sys.executable, str(AGENT), str(trace)],
        }))  # fmt: skip
        (AGENTS / f"{ORPHELIN}.plist").write_bytes(plistlib.dumps({
            "Label": ORPHELIN, "Program": str(tmp_path / "programme-qui-n-existe-pas"),
        }))  # fmt: skip
        r = launchctl("bootstrap", f"gui/{UID}", str(AGENTS / f"{CHARGE}.plist"))
        assert r.returncode == 0, r.stderr
        time.sleep(3)
        assert charge(CHARGE)

        debut = time.perf_counter()
        assert cli.scan(contexte, None) == 0  # premier passage : cache codesign vide
        duree_scan = time.perf_counter() - debut
        debut = time.perf_counter()
        assert cli.scan(contexte, None) == 0  # avec le cache
        duree_cache = time.perf_counter() - debut
        print(f"\n   scan : {duree_scan:.1f} s, puis {duree_cache:.1f} s avec le cache codesign")
        assert duree_scan < 15 and duree_cache < 5
        assert cli.mesurer(contexte, type("A", (), {"minutes": 3.0})()) == 0
        bilan = travail.bilan(contexte.systeme, contexte.base, reglages)
        premier = bilan.classement[0]
        print(f"   en tête : {premier.nom} (impact {premier.impact:.0f}) {premier.drapeaux}")
        assert "c'est moi" not in premier.nom, premier.nom  # un élément de test n'est pas l'Assistant (D-44)
        assert premier.fiche.label == CHARGE, [(e.fiche.label, e.impact) for e in bilan.classement[:5]]
        assert "empêche la veille" in premier.drapeaux
        orphelin = next(e for e in bilan.elements if e.fiche.label == ORPHELIN)
        assert orphelin.verdict.code == "orphelin" and orphelin.verdict.action == "quarantaine"

        # Désactiver pour de vrai (notre élément de test), vérifier, puis restaurer.
        args = type("A", (), {"id": premier.fiche.id, "confirmer": True})()
        assert cli.desactiver(contexte, args) == 0
        assert not charge(CHARGE) and desactive(CHARGE), etat_brut(CHARGE)
        assert cli.restaurer(contexte, args) == 0
        assert not desactive(CHARGE) and charge(CHARGE), etat_brut(CHARGE)
    finally:
        nettoyer(trace)
        contexte.fermer()
    time.sleep(1)
    assert traces() == [], f"Il reste des traces : {traces()}"
    vivants = [pid for pid in (trace.read_text().split() if trace.exists() else []) if vivant(int(pid))]
    assert vivants == [], f"Des processus de test tournent encore : {vivants}"


def vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
