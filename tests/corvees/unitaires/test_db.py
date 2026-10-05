import os
import sqlite3
import stat
from unittest import mock

import pytest

from modules.corvees.db import Base, DisquePlein, Evenement
from modules.corvees.normalize import jour_de

T0 = 1_790_000_000.0  # un instant fixe


def evt(ts=T0, token="app:Numbers", kind="app", source="apps", **attrs):
    return Evenement(ts, source, kind, token, attrs, 1)


def test_ecrire_et_relire_dans_l_ordre(base):
    assert base.ajouter([evt(T0 + 2, "app:Mail"), evt(T0, "app:Numbers")]) == 2
    lus = base.evenements(T0 - 1)
    assert [e.token for e in lus] == ["app:Numbers", "app:Mail"] and base.compter() == 2
    assert base.evenements(T0 - 1, T0 + 1)[0].token == "app:Numbers"
    jour = base.db.execute("SELECT jour FROM events LIMIT 1").fetchone()[0]
    assert jour == jour_de(T0)


def test_base_lisible_par_moi_seul(base):
    assert stat.S_IMODE(os.stat(base.chemin).st_mode) == 0o600


def test_ses_fichiers_de_journal_aussi(tmp_path, gardien):
    """Le journal d'écriture de SQLite (-wal, -shm) contient les mêmes données : lisible par toi seul aussi
    (trouvé en faisant tourner le vrai démon : il était en 644)."""
    ancien = os.umask(0o022)
    try:
        b = Base(tmp_path / "corvees.db", gardien)
        b.ajouter([evt()])
        b.ecrire("battement", 1.0)
        fichiers = sorted(tmp_path.glob("corvees.db*"))
        assert {f.name for f in fichiers} >= {"corvees.db", "corvees.db-wal", "corvees.db-shm"}
        assert {f.name: oct(stat.S_IMODE(f.stat().st_mode)) for f in fichiers} == {f.name: "0o600" for f in fichiers}
        b.fermer()
        for f in tmp_path.glob("corvees.db-*"):
            os.chmod(f, 0o644)  # une base d'avant ce correctif : remise à 600 à l'ouverture
        b = Base(tmp_path / "corvees.db", gardien)
        assert all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in tmp_path.glob("corvees.db*"))
        b.fermer()
    finally:
        os.umask(ancien)


def test_rien_d_exclu_ni_de_secret_n_est_ecrit(base):
    n = base.ajouter(
        [
            evt(token="app:1Password", appli="1Password"),
            evt(token="url:boursorama.com/compte", kind="url", source="navigateur", domaine="boursorama.com"),
            evt(token="cmd:mysql -u root -pS3cret!", kind="cmd", source="shell"),
        ]
    )
    assert n == 1
    contenu = base.chemin.read_bytes() + (base.chemin.with_name(base.chemin.name + "-wal").read_bytes())
    assert b"1Password" not in contenu and b"boursorama" not in contenu and b"S3cret" not in contenu
    assert base.evenements(0)[0].token == "cmd:mysql -u root -p [secret]"


def test_purge_garde_seulement_des_comptes(base):
    vieux, recent = T0 - 40 * 86400, T0 - 86400
    base.ajouter([evt(vieux), evt(vieux + 10), evt(recent)])
    assert base.purger(30, maintenant=T0) == 2
    assert base.compter() == 1
    assert base.db.execute("SELECT jour, token, n FROM agregats").fetchall() == [(jour_de(vieux), "app:Numbers", 2)]
    base.ajouter([evt(vieux + 20)])
    base.purger(30, maintenant=T0)
    assert base.db.execute("SELECT n FROM agregats").fetchone()[0] == 3


def test_etat_cles_simples(base):
    assert base.lire("x", 7) == 7
    base.ecrire("x", {"curseur": 12})
    assert base.lire("x") == {"curseur": 12}
    base.effacer("x")
    assert base.lire("x") is None


def test_decisions(base):
    base.decider("sig", "abc123", "reject", None, 4.0)
    base.decider("sig", "abc123", "snooze", T0, 4.0)
    assert base.decisions()["sig"]["statut"] == "snooze" and base.decisions()["sig"]["jusqua"] == T0


def test_candidats_gardent_leur_premiere_apparition(base):
    c = {"id": "abc123", "signature": "s1", "type": "fichiers", "score": 5.0}
    base.enregistrer_candidats([c], analyse=100.0)
    base.enregistrer_candidats([dict(c, score=7.0)], analyse=200.0)
    lus = base.candidats()
    assert len(lus) == 1 and lus[0]["score"] == 7.0 and lus[0]["premier_vu"] == 100.0
    assert base.candidat("ABC123")["signature"] == "s1" and base.candidat("zzz") is None
    assert base.candidats(analyse=100.0) == []


def test_aucun_candidat_avant_la_premiere_analyse(base):
    assert base.candidats() == []


def test_couts_par_mois_et_appels_du_jour(base):
    base.noter_cout("2026-10", "haiku", 1000, 200, 0.002, True)
    base.noter_cout("2026-10", "haiku", 1000, 200, 0.003, False)
    assert base.cout_du_mois("2026-10") == pytest.approx(0.005) and base.cout_du_mois("2026-09") == 0
    assert base.appels_du_jour(0) == 2


def test_base_corrompue_mise_de_cote_et_reconstruite(tmp_path, gardien):
    chemin = tmp_path / "corvees.db"
    chemin.write_bytes(b"ceci n'est pas une base SQLite" * 100)
    messages = []
    b = Base(chemin, gardien, journal=messages.append)
    assert b.ajouter([evt()]) == 1
    sauvegardes = list(tmp_path.glob("corvees.db.corrompue-*"))
    assert sauvegardes and sauvegardes[0].read_bytes().startswith(b"ceci n'est pas")
    assert messages and "reconstruite" in messages[0]
    assert stat.S_IMODE(os.stat(chemin).st_mode) == 0o600
    b.fermer()


def test_disque_plein_devient_une_erreur_claire(base):
    faux = mock.MagicMock()
    faux.__enter__.return_value = faux
    faux.executemany.side_effect = sqlite3.OperationalError("database or disk is full")
    base.db = faux
    with pytest.raises(DisquePlein):
        base.ajouter([evt()])
    faux.executemany.side_effect = sqlite3.OperationalError("no such table: events")
    with pytest.raises(sqlite3.OperationalError):
        base.ajouter([evt()])


def test_taille_sur_le_disque(base):
    base.ajouter([evt(T0 + i) for i in range(50)])
    assert base.taille() > 0


def test_rien_a_ecrire_quand_tout_est_exclu(base):
    assert base.ajouter([evt(token="app:1Password")]) == 0 and base.compter() == 0


def test_controle_d_integrite_en_echec(tmp_path, gardien):
    from modules.corvees import db as module_db

    vraie = module_db._ouvrir

    class Mefiante:
        def __init__(self, chemin):
            self.c = vraie(chemin)

        def execute(self, requete, *a):
            if "quick_check" in requete:
                return self.c.execute("SELECT '*** page 3: btree mal formé'")
            return self.c.execute(requete, *a)

        def close(self):
            self.c.close()

    (tmp_path / "corvees.db").write_bytes(b"")
    appels = []

    def ouvrir(chemin):
        appels.append(chemin)
        return Mefiante(chemin) if len(appels) == 1 else vraie(chemin)

    with mock.patch.object(module_db, "_ouvrir", side_effect=ouvrir):
        b = Base(tmp_path / "corvees.db", gardien)
    assert len(appels) == 2 and list(tmp_path.glob("corvees.db.corrompue-*"))
    b.fermer()
