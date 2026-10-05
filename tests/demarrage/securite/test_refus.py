"""Le vrai Mac refuse toute commande d'administrateur avant même de la lancer."""

import subprocess

import pytest

from modules.demarrage.systeme import Mac, RefusAdministrateur


@pytest.mark.parametrize(
    "commande", [["sudo", "launchctl", "bootout", "system/x"], ["/usr/bin/sudo", "-v"], ["su"], ["doas", "x"]]
)
def test_refus_sans_lancer(monkeypatch, commande):
    def interdit(*a, **k):
        raise AssertionError("subprocess lancé alors qu'il fallait refuser")

    monkeypatch.setattr(subprocess, "run", interdit)
    monkeypatch.setattr(subprocess, "Popen", interdit)
    with pytest.raises(RefusAdministrateur):
        Mac().executer(commande)
