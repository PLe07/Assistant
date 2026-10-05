from pathlib import Path
from unittest import mock

from modules.corvees import config


def test_valeurs_par_defaut_completes():
    r, erreurs = config.charger({})
    assert erreurs == []
    assert r["actif"] is False
    assert r["detection"]["fichiers"]["occurrences_min"] == 4
    assert r["detection"]["ponts"] == {"occurrences_min": 5, "jours_min": 3}
    assert r["ia"]["budget_mensuel_usd"] == 2.0 and r["ia"]["max_candidats"] == 8
    assert r["analyse"]["heure"] == "21:00" and r["retention_jours"] == 30


def test_mes_valeurs_remplacent_les_defauts_en_profondeur():
    r, erreurs = config.charger({"detection": {"ponts": {"jours_min": 4}}, "capteurs": {"pressepapiers": False}})
    assert erreurs == []
    assert r["detection"]["ponts"] == {"occurrences_min": 5, "jours_min": 4}
    assert r["capteurs"]["pressepapiers"] is False and r["capteurs"]["apps"] is True


def test_une_valeur_invalide_est_remplacee_et_signalee():
    r, erreurs = config.charger({"retention_jours": "trente", "capteurs": {"apps": "oui"}, "ia": 3, "inconnu": 1})
    assert r["retention_jours"] == 30 and r["capteurs"]["apps"] is True and isinstance(r["ia"], dict)
    assert len(erreurs) == 4 and any("inconnu" in e for e in erreurs)
    assert any("retention_jours" in e and "'trente'" in e for e in erreurs)


def test_entiers_et_decimaux_sont_interchangeables_mais_pas_les_booleens():
    r, erreurs = config.charger({"ia": {"budget_mensuel_usd": 3}, "retention_jours": True})
    assert r["ia"]["budget_mensuel_usd"] == 3 and r["retention_jours"] == 30 and len(erreurs) == 1


def test_listes_de_textes_seulement():
    r, erreurs = config.charger({"exclusions": {"applis": ["Slack", 3]}})
    assert r["exclusions"]["applis"] == [] and erreurs


def test_on_peut_ajouter_un_type_de_corvee_au_scoring():
    r, erreurs = config.charger({"scoring": {"automatisabilite": {"nouveau": 0.5}}})
    assert erreurs == [] and r["scoring"]["automatisabilite"]["nouveau"] == 0.5


def test_reglages_lus_dans_le_fichier_de_l_assistant():
    with mock.patch("core.config.charger", return_value={"modules": {"corvees": {"retention_jours": 10}}}):
        r, _ = config.charger()
    assert r["retention_jours"] == 10


def test_dossier_des_donnees(tmp_path, monkeypatch):
    r, _ = config.charger({"dossier": str(tmp_path / "ici")})
    assert config.dossier_donnees(r) == tmp_path / "ici"
    r, _ = config.charger({})
    monkeypatch.setenv("CORVEES_DOSSIER", str(tmp_path / "env"))
    assert config.dossier_donnees(r) == tmp_path / "env"
    monkeypatch.delenv("CORVEES_DOSSIER")
    assert config.dossier_donnees(r) == Path(__import__("core.config", fromlist=["x"]).DONNEES) / "corvees"


def test_listes_d_exclusion_completees_par_les_miennes():
    r, _ = config.charger({"exclusions": {"applis": ["Slack"], "domaines": ["intranet.ecole.fr"]}})
    assert "1Password" in config.applis_exclues(r) and "Slack" in config.applis_exclues(r)
    assert "impots.gouv.fr" in config.domaines_exclus(r) and "intranet.ecole.fr" in config.domaines_exclus(r)
