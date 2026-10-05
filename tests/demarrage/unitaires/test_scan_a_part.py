"""D-46 : la surveillance fait son scan quotidien dans un processus fils, et ne charge jamais la pile du scan ; sa
mémoire ne grossit donc pas d'un scan à l'autre (sur le Mac : 39,9 Mo pour un budget de 40, avant)."""

import subprocess
import sys

from modules.demarrage import daemon, travail
from modules.demarrage.notifier import Notifieur
from modules.demarrage.systeme import Mac
from tests.demarrage.faux_mac.construire import construire

RACINE = travail.RACINE


def test_le_scan_quotidien_tourne_dans_un_processus_fils(reglages):
    """Le vrai fils, sur la machine qui fait tourner les tests (en lecture seule : sans launchctl, il se dégrade)."""
    base = travail.ouvrir_base(reglages)
    mac = Mac()
    demon = daemon.Demon(mac, base, reglages, Notifieur(base, reglages, lambda t, m: True), scan_a_part=True)
    assert demon.scanner(mac.maintenant()) == []  # premier scan : la référence, rien de « nouveau »
    assert demon.inventaire is not None and base.dernier_scan() is not None
    assert mac.couts()[sys.executable.rsplit("/", 1)[-1]]["appels"] == 1  # c'est bien le fils qui a scanné
    base.fermer()


def test_si_le_fils_echoue_le_scan_a_lieu_quand_meme(tmp_path, reglages):
    faux = construire(tmp_path / "mac")  # le faux Mac ne sait pas lancer python : le fils « échoue »
    base = travail.ouvrir_base(reglages)
    demon = daemon.Demon(faux.mac, base, reglages, Notifieur(base, reglages, lambda t, m: True), scan_a_part=True)
    demon.scanner(faux.mac.maintenant())
    assert any(c[1:3] == ["-m", "modules.demarrage.scan_fils"] for c in faux.mac.appels)
    assert demon.inventaire is not None and len(demon.inventaire.fiches) > 20  # scanné sur place
    base.fermer()


def test_le_demon_ne_charge_pas_la_pile_du_scan():
    script = (
        "import sys; import modules.demarrage.module, modules.demarrage.daemon\n"
        "lourds = ['hashlib', 'plistlib', 'concurrent.futures', 'modules.demarrage.scan',\n"
        "          'modules.demarrage.signatures', 'modules.demarrage.analyse', 'modules.demarrage.rapport']\n"
        "print([m for m in lourds if m in sys.modules])"
    )
    r = subprocess.run([sys.executable, "-c", script], cwd=RACINE, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


def test_moyenne_du_jour_separe_le_ponctuel_du_regime():
    """D-47 : 2,25 s en 602 s (le total du 3e passage sur le Mac) ; 0,30 s de régime en 450 s (un exemple)."""
    from tests.demarrage.e2e_mac.mesure_demon import moyenne_du_jour

    r = moyenne_du_jour(cpu_total_s=2.25, ecoule_s=602, regime_cpu_s=0.30, regime_duree_s=450, top_s=0.32,
                        top_pas_s=1800)  # fmt: skip
    assert r["regime_pct"] == 0.067  # 0,30 s en 450 s
    assert r["ponctuel_s"] == 1.85  # 2,25 − 602 × 0,30 / 450 : le lancement et le scan
    assert r["jour_pct"] == round(0.30 / 450 * 100 + 0.32 / 1800 * 100 + 1.85 / 86400 * 100, 3)
    # Rien de ponctuel : la moyenne du jour, c'est le régime (plus top).
    assert moyenne_du_jour(1.0, 100, 1.0, 100, 0.0, 1800)["jour_pct"] == 1.0
