"""Les réglages : valeurs par défaut raisonnables, et un fichier mal rempli ne bloque jamais rien."""

from __future__ import annotations

from pathlib import Path

import pytest

from quotidien import config


def test_defauts_sans_aucun_fichier(tmp_path: Path) -> None:
    r = config.charger(tmp_path)
    assert r.avertissements == []
    assert r["repas"]["budget_semaine"] == 45.0
    assert r["semaine"]["jours_charges"] == ["mercredi", "jeudi", "vendredi"]
    assert r["trajets"]["depart"] == "08:00" and r["trajets"]["retour"] == "18:30"
    assert r["horaires"]["brief"] == "07:15"
    assert r["ia"]["budget_mensuel_usd"] == 2.0
    assert r["lieu"]["ville"] == "Bordeaux"


def test_chemins_dans_la_maison_imitee(maison: Path) -> None:
    assert config.dossier_support() == maison / "Library/Application Support/Quotidien"
    assert config.dossier_logs() == maison / "Library/Logs/Quotidien"
    assert config.dossier_icloud() == maison / "Library/Mobile Documents/com~apple~CloudDocs/Quotidien"
    assert config.dossier_icloud_raccourcis().parts[-3:] == ("iCloud~is~workflow~my~workflows", "Documents",
                                                             "Quotidien")  # fmt: skip
    assert config.chemin_base().name == "quotidien.db"
    assert (config.racine_projet() / "pyproject.toml").is_file()


def test_profil_rempli(tmp_path: Path) -> None:
    (tmp_path / "profil.toml").write_text(
        """
[repas]
regime = "Vegetarien"
allergies = ["Fruits à coque", "lait"]
deteste = ["coriandre"]
budget_semaine = 38
equipement = ["plaques", "micro-ondes"]
jour_courses = "Sam"
[semaine]
jours_charges = ["Lundi", "jeudi"]
[trajets]
depart = "7:45"
""",
        encoding="utf-8",
    )
    r = config.charger(tmp_path)
    assert r.avertissements == []
    assert r["repas"]["regime"] == "vegetarien"
    assert r["repas"]["allergies"] == ["fruits_a_coque", "lait"]
    assert r["repas"]["jour_courses"] == "samedi"
    assert r["semaine"]["jours_charges"] == ["lundi", "jeudi"]
    assert r["trajets"]["depart"] == "7:45"


def test_profil_mal_rempli_messages_clairs_et_defauts(tmp_path: Path) -> None:
    (tmp_path / "profil.toml").write_text(
        """
[repas]
regime = "carnivore"
allergies = ["noix de pécan", "gluten"]
portions = 0
budget_semaine = "beaucoup"
equipement = ["four", "thermomix"]
dejeuners = "oui"
jour_courses = "jamais"
deteste = "brocoli"
[semaine]
jours_charges = ["mercredi", "funday"]
[trajets]
depart = "25:00"
retour = "07:00"
moyen = "trottinette"
duree_minutes = 3.5
""",
        encoding="utf-8",
    )
    r = config.charger(tmp_path)
    texte = "\n".join(r.avertissements)
    assert "regime" in texte and "carnivore" in texte
    assert r["repas"]["regime"] == "omnivore"
    # Une allergie inconnue n'est jamais ignorée : elle devient un aliment interdit.
    assert r["repas"]["allergies"] == ["gluten"]
    assert "noix de pécan" in r["repas"]["deteste"]
    assert r["repas"]["portions"] == 1
    assert r["repas"]["budget_semaine"] == 45.0
    assert r["repas"]["equipement"] == ["plaques", "four", "micro-ondes"]
    assert r["repas"]["dejeuners"] is False
    assert r["repas"]["jour_courses"] == "lundi"
    assert r["semaine"]["jours_charges"] == ["mercredi", "jeudi", "vendredi"]
    assert r["trajets"]["depart"] == "08:00"
    assert r["trajets"]["moyen"] == "velo"
    assert r["trajets"]["duree_minutes"] == 30
    assert len(r.avertissements) >= 10


def test_retour_avant_depart(tmp_path: Path) -> None:
    (tmp_path / "profil.toml").write_text('[trajets]\ndepart = "09:00"\nretour = "08:00"\n', encoding="utf-8")
    r = config.charger(tmp_path)
    assert r["trajets"]["retour"] == "18:30"
    assert any("retour" in a for a in r.avertissements)


def test_toml_illisible(tmp_path: Path) -> None:
    (tmp_path / "profil.toml").write_text("[repas\nbudget = ", encoding="utf-8")
    (tmp_path / "reglages.toml").write_bytes(b"\xff\xfe")
    r = config.charger(tmp_path)
    assert sum("illisible" in a for a in r.avertissements) == 2
    assert r["repas"]["budget_semaine"] == 45.0


def test_section_qui_n_est_pas_une_section(tmp_path: Path) -> None:
    (tmp_path / "profil.toml").write_text('repas = "non"\n', encoding="utf-8")
    (tmp_path / "reglages.toml").write_text("ia = 3\n", encoding="utf-8")
    r = config.charger(tmp_path)
    assert r["repas"]["regime"] == "omnivore" and r["ia"]["modele"] == "claude-haiku-4-5"


def test_reglages_mal_remplis(tmp_path: Path) -> None:
    (tmp_path / "reglages.toml").write_text(
        """
[lieu]
latitude = 200
ville = ""
[horaires]
brief = "7h15"
menu_jour = "dimanchee"
[ia]
budget_mensuel_usd = -1
active = 1
modele = 3
[anniversaires]
date_29_fevrier = "29-02"
jours_avant_proches = 99
[installation]
prefixe_label = 5
""",
        encoding="utf-8",
    )
    r = config.charger(tmp_path)
    assert r["lieu"]["latitude"] == 44.8378 and r["lieu"]["ville"] == "Bordeaux"
    assert r["horaires"]["brief"] == "07:15" and r["horaires"]["menu_jour"] == "dimanche"
    assert r["ia"]["budget_mensuel_usd"] == 2.0 and r["ia"]["active"] is True
    assert r["ia"]["modele"] == "claude-haiku-4-5"
    assert r["anniversaires"]["date_29_fevrier"] == "28-02"
    assert r["anniversaires"]["jours_avant_proches"] == 7
    assert r["installation"]["prefixe_label"] == ""


def test_menu_jour_abrege(tmp_path: Path) -> None:
    (tmp_path / "reglages.toml").write_text('[horaires]\nmenu_jour = "Sam"\n', encoding="utf-8")
    assert config.charger(tmp_path)["horaires"]["menu_jour"] == "samedi"


@pytest.mark.parametrize("texte,attendu", [("07:15", 435), ("0:00", 0), ("23:59", 1439)])
def test_en_minutes(texte: str, attendu: int) -> None:
    assert config.en_minutes(texte) == attendu


def test_en_minutes_invalide() -> None:
    with pytest.raises(ValueError):
        config.en_minutes("24:00")


def test_normaliser_jour() -> None:
    assert config.normaliser_jour("Mercredi") == "mercredi"
    assert config.normaliser_jour("mer") == "mercredi"
    assert config.normaliser_jour(3) is None
    assert config.normaliser_jour("") is None


def test_defauts_independants() -> None:
    a = config.defauts()
    a["repas"]["allergies"].append("lait")
    assert config.defauts()["repas"]["allergies"] == []


def test_les_14_allergenes() -> None:
    assert len(config.ALLERGENES) == 14 and set(config.NOMS_ALLERGENES) == set(config.ALLERGENES)
