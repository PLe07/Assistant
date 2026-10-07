"""L'inventaire de bout en bout (Gmail imité + navigateurs), le rapport HTML, l'option IA, la ligne de commande."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from bouclier import cli, config, db, gmail, tableau_de_bord
from bouclier.arnaque.ia import Budget, ReponseBrute
from bouclier.comptes import ia_categories, inventaire, lancer, rapport
from bouclier.systeme import Resultat, Systeme
from tests.comptes.boite_simulee import FauxImap, generer
from tests.comptes.test_inventaire import _login_data


def _mac(secrets: dict[str, str]) -> Systeme:
    def executer(args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        a = list(args)
        if a[:2] == ["security", "find-generic-password"]:
            valeur = secrets.get(a[a.index("-s") + 1])
            return Resultat(0, valeur + "\n") if valeur else Resultat(44, "", "introuvable")
        return Resultat(0, "")

    return Systeme(executer, mac=True)


def _reglages(adresse: str = "camille@example.org") -> dict[str, object]:
    r = config.charger()
    r["gmail"]["adresse"] = adresse
    return r


def test_inventaire_complet(maison: Path, tmp_path: Path) -> None:
    messages, comptes, _ = generer()
    faux = FauxImap(messages)
    _login_data(maison / "Library/Application Support/Google/Chrome/Default/Login Data",
                [("https://www.vinted.fr/", "moi"), ("https://compte.petit-site.fr/", "moi")])  # fmt: skip
    base = db.Base(tmp_path / "b.db")
    r = lancer.lancer(config.chemins(), _reglages(), base, _mac({"bouclier-gmail": "bon"}), fabrique=lambda s: faux)
    assert r.gmail.startswith(f"Gmail : {len(messages)} nouveaux en-têtes lus") and r.navigateurs == ["Chrome"]
    assert r.comptes >= 37 and r.abonnements >= 18 and "petit-site.fr" in r.nouveaux
    assert faux.violations == []
    html = tableau_de_bord.construire(base)
    assert "Tes comptes en ligne" in html and "page de suppression" in html and "https://www.vinted.fr" in html
    assert not re.search(r"<(script|link|img)\b", html) and "http://" not in html
    r2 = lancer.lancer(config.chemins(), _reglages(), base, _mac({"bouclier-gmail": "bon"}), fabrique=lambda s: faux)
    assert r2.gmail.startswith("Gmail : 0 nouveaux") and r2.nouveaux == [] and r2.comptes == r.comptes


def test_gmail_non_relie_mode_degrade(tmp_path: Path) -> None:
    base = db.Base(tmp_path / "b.db")
    r = lancer.lancer(config.chemins(), _reglages(""), base, _mac({}), avec_navigateurs=False)
    assert "pas encore relié" in r.gmail and r.comptes == 0
    r = lancer.lancer(config.chemins(), _reglages(), base, _mac({}), avec_navigateurs=False)
    assert "mot de passe d'application Gmail absent" in r.gmail
    faux = FauxImap(generer()[0])
    faux.mot_de_passe = "autre"
    r = lancer.lancer(config.chemins(), _reglages(), base, _mac({"bouclier-gmail": "mauvais"}),
                      fabrique=lambda s: faux, avec_navigateurs=False)  # fmt: skip
    assert "refuse la connexion" in r.gmail
    reglages = _reglages()
    reglages["gmail"]["active"] = False  # type: ignore[index]
    assert gmail.etat(reglages, _mac({}))[0] is False


def test_le_domaine_perso_n_est_pas_un_compte(tmp_path: Path) -> None:
    messages = generer()[0]
    import datetime as dt

    from tests.comptes.boite_simulee import Message, _entetes

    perso = _entetes('"Moi" <moi@famille-exemple.fr>', "Bienvenue chez nous", dt.datetime(2024, 1, 1), False)
    messages.append(Message(99999, perso))
    faux = FauxImap(messages)
    base = db.Base(tmp_path / "b.db")
    lancer.lancer(config.chemins(), _reglages("moi@famille-exemple.fr"), base, _mac({"bouclier-gmail": "bon"}),
                  fabrique=lambda s: faux, avec_navigateurs=False)  # fmt: skip
    assert "famille-exemple.fr" not in {
        ligne.id for ligne in inventaire.lignes(base, ("compte", "abonnement", "autre"))
    }


def test_option_ia_ne_recoit_que_des_domaines(tmp_path: Path) -> None:
    base = db.Base(tmp_path / "b.db")
    reglages = _reglages()
    recus: list[str] = []

    class Client:
        nom = "faux"

        def envoyer(self, systeme: str, utilisateur: str, max_jetons: int, delai: float) -> ReponseBrute:
            recus.append(utilisateur)
            return ReponseBrute(json.dumps({"petit-site.fr": "achats", "autre.fr": "inventée"}), 50, 20)

    budget = Budget(base, reglages)  # type: ignore[arg-type]
    assert ia_categories.categoriser(["petit-site.fr", "autre.fr", "<script>"], Client(), budget) == {
        "petit-site.fr": "achats"}  # fmt: skip
    assert recus == ["autre.fr\npetit-site.fr"]
    assert (
        ia_categories.categoriser([], Client(), budget) == {}
        and ia_categories.categoriser(["a.fr"], None, budget) == {}
    )


def test_rapport_html_echappe_et_conseils(tmp_path: Path) -> None:
    base = db.Base(tmp_path / "b.db")
    inv = inventaire.Inventaire()
    for brut in (b"From: <a@labanquepostale.fr>\r\nSubject: Bienvenue\r\n\r\n",
                 b"From: <a@impots.gouv.fr>\r\nSubject: Nouveau mot de passe\r\n\r\n",
                 b"From: <a@x--<b>pirate</b>.fr>\r\nSubject: Welcome\r\n\r\n"):  # fmt: skip
        obs = inventaire.observer(brut)
        if obs:
            inv.ajouter_mail(obs)
    inventaire.enregistrer(base, inv)
    html = rapport.section(inventaire.lignes(base))
    assert "fermeture : demande-la à ta banque" in html and "il ne se supprime pas" in html
    assert "<b>pirate</b>" not in html
    assert "Pas encore d'inventaire" in rapport.section([])


def test_cli_inventaire_comptes_compte(maison: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _login_data(maison / "Library/Application Support/Google/Chrome/Default/Login Data",
                [("https://www.vinted.fr/", "moi")])  # fmt: skip
    mac = Systeme(lambda a, e, d: Resultat(0, ""), mac=False)
    assert cli.main(["comptes"], mac) == 0 and "Pas encore d'inventaire" in capsys.readouterr().out
    assert cli.main(["inventaire", "--sans-gmail"], mac) == 0
    sortie = capsys.readouterr().out
    assert "1 comptes probables" in sortie and config.chemins().tableau_de_bord.exists()
    assert (config.chemins().tableau_de_bord.stat().st_mode & 0o777) == 0o600
    assert cli.main(["comptes", "--tous"], mac) == 0 and "Vinted" in capsys.readouterr().out
    assert cli.main(["compte", "vinted", "supprimer"], mac) == 0 and "vinted : supprimer" in capsys.readouterr().out
    assert cli.main(["compte", "inconnu", "garder"], mac) == 1


def test_cli_gmail_relier(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    secrets: dict[str, str] = {}
    mac = _mac(secrets)
    monkeypatch.setattr(
        Systeme, "interactif", lambda self, args: (secrets.update({"bouclier-gmail": "abcd efgh"}), 0)[1]
    )
    boite = FauxImap(generer()[0])
    boite.mot_de_passe = "abcdefgh"  # collé avec les espaces de l'affichage de Google : ils sont retirés
    monkeypatch.setattr(cli, "FABRIQUE_IMAP", lambda serveur: boite)
    assert cli.main(["gmail-relier", "pas-une-adresse"], mac) == 1
    # « ADRESSE » tapé tel quel, dans le Terminal : l'adresse est demandée.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda invite: "Camille@Example.org")
    assert cli.main(["gmail-relier", "ADRESSE"], mac) == 0
    assert 'adresse = "camille@example.org"' in config.chemins().config.read_text(encoding="utf-8")
    sortie = capsys.readouterr().out
    assert "✅ Gmail relié en lecture seule" in sortie and "connexion réussie" in sortie
    assert boite.violations == [] and not any(c[0] in ("STORE", "SELECT") for c in boite.commandes)
    base = db.ouvrir(config.chemins().base)
    assert base.lire_meta("prochain:gmail") == "0" and base.lire_meta("prochain:inventaire") == "0"
    boite.mot_de_passe = "autre"  # mauvais mot de passe collé : message clair
    assert cli.main(["gmail-relier", "camille@example.org"], mac) == 1
    assert "pas ton mot de passe Google" in capsys.readouterr().out
    assert cli.main(["gmail-relier", "a@b.fr"], Systeme(lambda a, e, d: Resultat(0, ""), mac=False)) == 1
