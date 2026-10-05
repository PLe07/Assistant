"""L'échantillonneur sur le faux Mac n° 1 : les secondes de processeur, la mémoire, l'énergie et la veille de
chaque élément, comparées à ce que les processus simulés ont vraiment consommé."""

import pytest

from modules.demarrage import scan
from modules.demarrage.db import Base, DisquePlein
from modules.demarrage.mesure import session
from modules.demarrage.mesure.echantillonneur import Echantillonneur
from tests.demarrage.faux_mac.construire import COEURS, construire


@pytest.fixture
def faux(tmp_path):
    return construire(tmp_path / "mac")


@pytest.fixture
def base(tmp_path):
    b = Base(tmp_path / "demarrage.db")
    yield b
    b.fermer()


def preparer(faux, base, reglages):
    faux.a_l_instant(0)
    inv = scan.scanner(faux.mac, reglages)
    ids = {(f.source, f.label): f.id for f in inv.fiches}
    return Echantillonneur(faux.mac, base, reglages, lambda: inv.fiches), ids


def consomme(faux, label, jusqua):
    return sum(p.cumul(jusqua) for p in faux.plante(label).processus)


def test_session_secondes_de_processeur_exactes(faux, base, reglages):
    ech, ids = preparer(faux, base, reglages)
    bilan = ech.suivre_session(faux.boot, faux.connexion)
    assert faux.mac.horloge == faux.connexion + 300
    par_fiche: dict[str, float] = {}
    for _, mode, fid, cpu, *_ in base.mesures():
        assert mode == "session"
        par_fiche[fid] = par_fiche.get(fid, 0.0) + cpu
    controles = [
        ("agent_global", "com.adobe.AdobeCreativeCloud"),
        ("agent_utilisateur", "com.docker.socket"),
        ("agent_utilisateur", "com.sauvegarde.express.agent"),
        ("ouverture", "us.zoom.xos"),
    ]
    for source, label in controles:
        attendu = consomme(faux, label, 295)  # le dernier relevé est à 295 s
        assert par_fiche[ids[(source, label)]] == pytest.approx(attendu, abs=0.1), label
    assert par_fiche[ids[("agent_global", "com.adobe.AdobeCreativeCloud")]] > 250  # Core Sync (fils) compris
    assert len(base.releves()) == 60 and bilan["releves"] == 60 and bilan["demarrage_s"] == 52.0
    # Le calme : recalculé à partir des processus simulés eux-mêmes.
    totaux = []
    for k in range(1, 60):
        t0, t1 = 5 * (k - 1), 5 * k
        coeurs = sum(p.cumul(t1) - p.cumul(t0) for p in faux.processus) / 5
        totaux.append((faux.connexion + t1, 100 * coeurs / COEURS))
    attendu = session.temps_jusquau_calme(totaux, faux.connexion)
    assert attendu is not None and 180 < attendu < 245
    assert bilan["calme_s"] == pytest.approx(attendu, abs=0.1)
    enregistree = base.session(faux.boot)
    assert enregistree["connexion"] == faux.connexion and enregistree["calme"] == pytest.approx(
        faux.connexion + attendu
    )


def test_mesure_memoire_energie_veille(faux, base, reglages):
    ech, ids = preparer(faux, base, reglages)
    faux.a_l_instant(600)
    assert ech.mesurer(minutes=2, pas_s=5) == 25
    lignes = base.mesures(modes=("mesure",))
    docker = [x for x in lignes if x[2] == ids[("agent_utilisateur", "com.docker.socket")]]
    assert len(docker) == 25 and docker[0][3] == 0.0  # le premier relevé sert de référence
    assert docker[-1][4] == (150 + 1500) * 1024
    assert sum(x[3] for x in docker) == pytest.approx(0.06 * 120, abs=0.1)
    avec_energie = [x for x in docker if x[5] is not None]
    assert len(avec_energie) == 3 and avec_energie[0][5] == pytest.approx(8.0)  # à 0, 60 et 120 s
    sauvegarde = [x for x in lignes if x[2] == ids[("agent_utilisateur", "com.sauvegarde.express.agent")]]
    assert all(x[6] == 1 for x in sauvegarde)
    adobe = [x for x in lignes if x[2] == ids[("agent_global", "com.adobe.AdobeCreativeCloud")]]
    assert not any(x[6] for x in adobe)
    assert all(c is not None and c < 15 for _, c in base.releves()[1:])  # en croisière, le Mac est calme


def test_pannes(faux, base, reglages, caplog):
    ech, _ = preparer(faux, base, reglages)
    faux.mac.repondre_debut(["ps"], "", code=1, erreur="ps: refusé")
    assert ech.prendre("mesure") is None
    faux.mac.repondre_debut(["ps"], "  1 0 0 0.0 10 00:10 0:00.01 /sbin/launchd\n")
    faux.mac.repondre(["pmset", "-g", "assertions"], "", code=1)
    faux.mac.repondre(["launchctl", "list"], "", code=1)
    faux.mac.repondre(["sysctl", "-n", "hw.ncpu"], "", code=1)

    def plein(*a, **k):
        raise DisquePlein("database or disk is full")

    base.enregistrer_releve = plein  # type: ignore[method-assign]
    assert ech.prendre("mesure") is not None and ech.disque_plein
    assert ech.prendre("mesure") is not None and ech.coeurs == 1
    assert sum("disque plein" in r.message for r in caplog.records) == 1  # dit une seule fois


def test_pid_reutilise(mac, tmp_path, reglages):
    b = Base(tmp_path / "d.db")
    sorties = iter([
        "  50 1 501 0.0 1000 01:00 0:10.00 /opt/a\n",
        "  50 1 501 0.0 1000 01:05 0:12.00 /opt/a\n",  # le même : +2 s
        "  50 1 501 0.0 1000 00:02 0:01.00 /opt/b\n",  # PID réutilisé par un nouveau venu : 1 s, en entier
    ])  # fmt: skip
    from modules.demarrage.modele import Fiche
    from modules.demarrage.systeme import Resultat

    mac.repondre_debut(["ps"], lambda c, m: Resultat(0, next(sorties)))
    fiches = [Fiche(id="a", label="a", source="agent_utilisateur", programme="/opt/a"),
              Fiche(id="b", label="b", source="agent_utilisateur", programme="/opt/b")]  # fmt: skip
    ech = Echantillonneur(mac, b, reglages, lambda: fiches)
    r1 = ech.prendre("mesure")
    mac.attendre(5)
    r2 = ech.prendre("mesure")
    mac.attendre(5)
    r3 = ech.prendre("mesure")
    assert r1.par_fiche["a"]["cpu_s"] == 0.0 and r2.par_fiche["a"]["cpu_s"] == pytest.approx(2.0)
    assert r3.par_fiche["b"]["cpu_s"] == pytest.approx(1.0) and "a" not in r3.par_fiche
    b.fermer()
