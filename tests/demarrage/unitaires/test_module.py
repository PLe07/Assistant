from modules.demarrage import config, module, travail


def test_status_pour_l_assistant(reglages, monkeypatch):
    monkeypatch.setattr(config, "charger", lambda perso=None: (reglages, []))
    s = module.status(1000.0)
    assert s == {"actif": False, "vivant": False, "battement": None, "dernier_scan": None, "en_attente": None,
                 "sessions": 0, "releves": 0}  # fmt: skip
    base = travail.ouvrir_base(reglages)
    base.ecrire("battement", 990.0)
    base.fermer()
    assert module.status(1000.0)["vivant"]


def test_boucle_deleguee(monkeypatch):
    vus = []
    monkeypatch.setattr(module.daemon, "boucle", vus.append)
    module.boucle("ctx")
    assert vus == ["ctx"]
