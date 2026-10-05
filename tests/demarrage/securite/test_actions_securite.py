"""§9.4 : Apple refusé ; /Library → instructions seules ; sans --confirmer, aucune commande de modification
(vérifié sur le faux Mac ET sur le vrai Mac en interceptant subprocess) ; aucun fichier touché."""

import hashlib
import subprocess

import pytest

from modules.demarrage.actions.desactiver import desactiver, est_lecture
from modules.demarrage.actions.journal import Journal
from modules.demarrage.actions.restaurer import restaurer
from modules.demarrage.analyse import Element
from modules.demarrage.analyse.scores import Metriques
from modules.demarrage.analyse.verdicts import Verdict
from modules.demarrage.db import Base
from modules.demarrage.modele import SOURCES_GLOBALES, Fiche
from modules.demarrage.systeme import Mac
from tests.demarrage.faux_mac.aleatoire import construire_aleatoire
from tests.demarrage.faux_mac.construire import construire
from tests.demarrage.faux_mac.juge import diagnostiquer
from tests.demarrage.faux_mac.launchd_simule import LaunchdSimule


def empreinte_de(racine):
    h = hashlib.sha256()
    for p in sorted(racine.rglob("*")):
        h.update(str(p.relative_to(racine)).encode())
        if p.is_file() and not p.is_symlink():
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(params=["n1", "aleatoire"])
def monde(request, tmp_path, reglages):
    faux = construire(tmp_path / "mac") if request.param == "n1" else construire_aleatoire(tmp_path / "mac", 7)
    bilan = diagnostiquer(faux, tmp_path, reglages)
    charges = {p.label: p.chemin_plist for p in faux.plantes if p.charge and p.source != "apple"}
    LaunchdSimule(faux.mac, charges, ouverture=dict(faux.login_items))
    base = Base(tmp_path / "actions.db")
    yield faux, bilan, Journal(base), tmp_path / "donnees"
    base.fermer()


def test_simulation_ne_modifie_rien(monde):
    faux, bilan, journal, dossier = monde
    avant, appels = empreinte_de(faux.mac.racine), len(faux.mac.appels)
    for e in bilan.elements:
        desactiver(e, faux.mac, journal, dossier)
        restaurer(e.fiche.id, faux.mac, journal)
    modifiantes = [c for c in faux.mac.appels[appels:] if not est_lecture(c)]
    assert modifiantes == []
    assert empreinte_de(faux.mac.racine) == avant and journal.toutes() == [] and not (dossier / "quarantaine").exists()


def test_apple_toujours_refuse(monde):
    faux, bilan, journal, dossier = monde
    appels = len(faux.mac.appels)
    apples = [e for e in bilan.elements if e.verdict.code == "apple"]
    assert len(apples) >= 15
    for e in apples:
        r = desactiver(e, faux.mac, journal, dossier, confirmer=True)
        assert r.plan.genre == "refus" and not r.fait and r.plan.commandes == []
    assert faux.mac.appels[appels:] == [] and journal.toutes() == []


def test_global_instructions_seulement(monde):
    faux, bilan, journal, dossier = monde
    avant, appels = empreinte_de(faux.mac.racine), len(faux.mac.appels)
    globaux = [e for e in bilan.elements if e.fiche.source in SOURCES_GLOBALES and e.verdict.code != "apple"]
    assert globaux
    for e in globaux:
        r = desactiver(e, faux.mac, journal, dossier, confirmer=True)
        assert not r.fait and r.plan.genre in ("instructions", "verifier", "rien") and r.plan.commandes == []
    assert all(est_lecture(c) for c in faux.mac.appels[appels:])
    assert empreinte_de(faux.mac.racine) == avant and journal.toutes() == []


def test_un_inconnu_n_est_jamais_supprime_ni_deplace(monde):
    """Un ⚠️ est d'abord à vérifier. Sur ta commande explicite, il peut être arrêté (réversible), mais jamais
    supprimé, déplacé en quarantaine ou modifié : aucun fichier ne bouge."""
    faux, bilan, journal, dossier = monde
    avant, appels = empreinte_de(faux.mac.racine), len(faux.mac.appels)
    inconnus = [e for e in bilan.elements if e.verdict.code == "inconnu"]
    assert inconnus
    for e in inconnus:
        assert e.verdict.action == "verifier"
        r = desactiver(e, faux.mac, journal, dossier, confirmer=True)
        assert r.plan.genre in ("verifier", "launchd", "instructions", "system_events", "rien")
        assert "Ne le supprime pas à l'aveugle" in r.plan.texte or r.plan.genre == "rien"
    permises = {("launchctl", "bootout"), ("launchctl", "disable")}
    for c in faux.mac.appels[appels:]:
        assert est_lecture(c) or tuple(c[:2]) in permises or (c[0] == "osascript" and "delete login item" in c[-1]), c
    assert empreinte_de(faux.mac.racine) == avant and not (dossier / "quarantaine").exists()
    assert all(a.genre != "quarantaine" for a in journal.toutes())


class Intercepteur:
    """Remplace subprocess.run : note chaque commande, répond comme un Mac où l'agent est chargé."""

    def __init__(self):
        self.commandes = []

    def __call__(self, commande, **kwargs):
        self.commandes.append(list(commande))
        sortie = "disabled services = {\n}\n" if commande[1:2] == ["print-disabled"] else "ok\n"
        return subprocess.CompletedProcess(commande, 0, sortie, "")


def element(source, verdict, action, label="com.exemple.agent"):
    f = Fiche(id="i", label=label, source=source, chemin_plist=f"/Users/x/Library/LaunchAgents/{label}.plist",
              programme="/opt/x", programme_existe=True, actif=True)  # fmt: skip
    return Element(f, Metriques(), 50.0, False, "faible", "", None, Verdict(verdict, "raison", action))


def test_vrai_mac_subprocess_intercepte(monkeypatch, tmp_path):
    intercepteur = Intercepteur()
    monkeypatch.setattr(subprocess, "run", intercepteur)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Popen interdit"))
    base = Base(tmp_path / "d.db")
    journal, mac = Journal(base), Mac()
    simulation = desactiver(element("agent_utilisateur", "inutile", "desactiver"), mac, journal, tmp_path)
    assert not simulation.fait and simulation.plan.genre == "launchd"
    assert intercepteur.commandes and all(est_lecture(c) for c in intercepteur.commandes)
    for source, verdict, action in [("apple", "apple", "aucune"), ("agent_global", "inutile", "instructions"),
                                    ("daemon_global", "orphelin", "instructions")]:  # fmt: skip
        avant = len(intercepteur.commandes)
        r = desactiver(element(source, verdict, action), mac, journal, tmp_path, confirmer=True)
        assert not r.fait and intercepteur.commandes[avant:] == []
    # La preuve que l'interception voit bien les vraies commandes : avec --confirmer, elles passent par elle.
    desactiver(element("agent_utilisateur", "inutile", "desactiver"), mac, journal, tmp_path, confirmer=True)
    assert ["launchctl", "disable", f"gui/{mac.uid}/com.exemple.agent"] in intercepteur.commandes
    assert not any(c[0] == "sudo" for c in intercepteur.commandes)
    base.fermer()
