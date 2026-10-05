"""Les exclusions : rien de ce qui touche une appli, un site ou un dossier exclu n'atteint la base."""

import os
import stat

from modules.corvees import config, privacy
from modules.corvees.db import Evenement


def evt(token, kind, **attrs):
    return Evenement(0.0, "test", kind, token, attrs)


def test_applis_exclues_par_nom_bundle_et_accents(gardien):
    for nom in ("1Password 7", "Bitwarden", "Trousseau d’accès", "Messages", "FaceTime", "Crédit Agricole", "LCL"):
        assert gardien.appli_exclue(nom), nom
    assert gardien.appli_exclue("Inconnu", "com.apple.MobileSMS")
    for nom in ("Numbers", "Safari", "Spotify", "Terminal", "Code", "Pages"):
        assert not gardien.appli_exclue(nom), nom


def test_domaines_exclus(gardien):
    for url in (
        "https://www.boursorama.com/x",
        "mabanque.bnpparibas/fr",
        "cfspart.impots.gouv.fr",
        "ameli.fr",
        "https://www.doctolib.fr/rdv",
        "particuliers.sg.fr",
        "www.lcl.fr",
    ):
        assert gardien.domaine_exclu(url), url
    for url in ("mail.google.com", "notion.so", "lcl-informatique.com", "wikipedia.org"):
        assert not gardien.domaine_exclu(url), url


def test_dossiers_exclus_reglables(tmp_path):
    r, _ = config.charger({"exclusions": {"dossiers": [str(tmp_path / "Perso")]}})
    g = privacy.Gardien(r, b"s" * 32)
    assert g.chemin_exclu(str(tmp_path / "Perso" / "journal.txt")) and not g.chemin_exclu(str(tmp_path / "Autre"))
    assert g.nettoyer(evt("fmove:x", "fmove", de=str(tmp_path / "Perso"), vers=str(tmp_path / "Autre"))) is None


def test_tout_evenement_touchant_une_exclusion_est_ecarte(gardien):
    ecartes = [
        evt("app:1Password", "app"),
        evt("app:Bidule", "app", bundle="com.1password.1password"),
        evt("clip:Safari→Messages", "clip"),
        evt("clip:Bitwarden→Safari", "clip", source="Bitwarden", destination="Safari"),
        evt("url:boursorama.com/compte", "url"),
        evt("url:x", "url", domaine="impots.gouv.fr"),
        evt("fen:Safari:Mon compte - Boursorama Banque", "fen"),
        evt("fen:Safari:Changer le mot de passe", "fen"),
        evt("fen:WhatsApp:Discussion", "fen"),
    ]
    for e in ecartes:
        assert gardien.nettoyer(e) is None, e.token
    garde = gardien.nettoyer(evt("fen:Numbers:Budget *", "fen", appli="Numbers"))
    assert garde is not None and garde.token == "fen:Numbers:Budget *"


def test_nettoyer_caviarde_le_token_et_les_attributs(gardien):
    e = gardien.nettoyer(evt("cmd:export TOKEN=abc", "cmd", cwd="~/x", note="moi@x.fr"))
    assert e.token == "cmd:export TOKEN=[secret]" and e.attrs["note"] == "[e-mail]"


def test_empreinte_salee_stable_et_courte(gardien):
    a = gardien.empreinte("contenu copié")
    assert a == gardien.empreinte(b"contenu copi\xc3\xa9") and len(a) == 16
    autre = privacy.Gardien(config.charger({})[0], b"x" * 32)
    assert autre.empreinte("contenu copié") != a


def test_sel_cree_une_fois_lisible_par_moi_seul(tmp_path):
    s1 = privacy.sel(tmp_path / "d")
    assert len(s1) == 32 and privacy.sel(tmp_path / "d") == s1
    assert stat.S_IMODE(os.stat(tmp_path / "d" / "sel").st_mode) == 0o600


def test_domaine_de():
    assert privacy.domaine_de("https://moi@www.Site.fr:8080/a?b") == "site.fr"
