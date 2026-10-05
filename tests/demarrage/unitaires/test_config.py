from pathlib import Path

from modules.demarrage import config


def test_defauts_sans_erreur():
    r, erreurs = config.charger({})
    assert erreurs == []
    assert r == config.DEFAUTS
    assert r is not config.DEFAUTS


def test_valeur_valide_remplace_le_defaut_en_profondeur():
    r, erreurs = config.charger({"scores": {"poids": {"memoire": 0.3}}, "retention_jours": 30})
    assert erreurs == []
    assert r["scores"]["poids"]["memoire"] == 0.3
    assert r["scores"]["poids"]["cpu_session"] == 0.45
    assert r["retention_jours"] == 30


def test_entier_accepte_pour_un_reel():
    r, erreurs = config.charger({"calme": {"seuil_cpu_pct": 20}})
    assert erreurs == [] and r["calme"]["seuil_cpu_pct"] == 20


def test_mauvais_type_remplace_et_signale():
    r, erreurs = config.charger({"retention_jours": "soixante", "actif": 1, "verdicts": {"motifs_mise_a_jour": [3]}})
    assert r["retention_jours"] == 60 and r["actif"] is False
    assert r["verdicts"]["motifs_mise_a_jour"] == config.DEFAUTS["verdicts"]["motifs_mise_a_jour"]
    assert len(erreurs) == 3
    assert any("retention_jours" in e for e in erreurs)


def test_reglage_inconnu_ignore():
    r, erreurs = config.charger({"inconnu": 1, "zsh": {"bizarre": True}})
    assert "inconnu" not in r and "bizarre" not in r["zsh"]
    assert len(erreurs) == 2


def test_section_remplacee_par_autre_chose_que_un_dict():
    r, erreurs = config.charger({"scores": 3})
    assert r["scores"] == config.DEFAUTS["scores"] and erreurs


def test_perso_pas_un_dict():
    r, erreurs = config.charger(["pas", "un", "dict"])  # type: ignore[arg-type]
    assert r == config.DEFAUTS and erreurs == []


def test_lit_reglages_json_de_l_assistant(monkeypatch):
    from core import config as coeur

    monkeypatch.setattr(coeur, "charger", lambda: {"modules": {"demarrage": {"actif": True, "retention_jours": 10}}})
    r, erreurs = config.charger()
    assert r["actif"] is True and r["retention_jours"] == 10 and erreurs == []


def test_dossier_donnees(monkeypatch, tmp_path):
    assert config.dossier_donnees({"dossier": str(tmp_path / "x")}) == tmp_path / "x"
    monkeypatch.setenv("DEMARRAGE_DOSSIER", str(tmp_path / "env"))
    assert config.dossier_donnees({"dossier": ""}) == tmp_path / "env"
    monkeypatch.delenv("DEMARRAGE_DOSSIER")
    from core import config as coeur

    assert config.dossier_donnees({"dossier": ""}) == Path(coeur.DONNEES) / "demarrage"
