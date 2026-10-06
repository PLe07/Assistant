"""§11.3 : fuites. Fixture HIBP ; correspondance des domaines (sous-domaines, alias), filtre de date, notification
une seule fois par fuite ; liste indisponible ; option payante ; tableau de bord et ligne de commande."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from bouclier import cli, config, db, reseau, tableau_de_bord
from bouclier.comptes import inventaire
from bouclier.fuites import croisement, hibp, rapport, traductions
from bouclier.notifier import Notifieur
from bouclier.systeme import Resultat, Systeme

FIXTURE = [
    {"Name": "Vinted2024", "Title": "Vinted", "Domain": "vinted.fr", "BreachDate": "2024-03-01",
     "AddedDate": "2024-04-02T10:00:00Z", "DataClasses": ["Email addresses", "Passwords", "Names"],
     "IsVerified": True, "IsFabricated": False, "IsSensitive": False, "IsRetired": False, "IsSpamList": False,
     "PwnCount": 100000},
    {"Name": "GoogleForum", "Title": "Forum Google", "Domain": "forum.google.com", "BreachDate": "2023-01-01",
     "AddedDate": "2023-02-01T00:00:00Z", "DataClasses": ["Usernames", "Email addresses"], "IsVerified": True},
    {"Name": "Avant", "Title": "Ancienne fuite", "Domain": "deezer.com", "BreachDate": "2015-06-01",
     "AddedDate": "2016-01-01T00:00:00Z", "DataClasses": ["Email addresses"], "IsVerified": True},
    {"Name": "Spam", "Title": "Liste de spam", "Domain": "vinted.fr", "BreachDate": "2022-01-01",
     "DataClasses": ["Email addresses"], "IsSpamList": True},
    {"Name": "Faux", "Title": "Fabriquée", "Domain": "vinted.fr", "BreachDate": "2022-01-01",
     "DataClasses": ["Email addresses"], "IsFabricated": True},
    {"Name": "SansDomaine", "Title": "Compilation", "Domain": "", "BreachDate": "2019-01-01",
     "DataClasses": ["Email addresses", "Passwords"]},
    {"Name": "Inconnu", "Title": "Site que tu n'utilises pas", "Domain": "autre-site.com", "BreachDate": "2024-01-01",
     "DataClasses": ["Email addresses"]},
]  # fmt: skip


class FauxHibp:
    def __init__(self, liste: list[dict[str, object]] | None = None, statut: int = 200) -> None:
        self.liste = liste if liste is not None else FIXTURE
        self.statut = statut
        self.appels: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, **kw: object) -> reseau.Reponse:
        reseau.verifier_url(url)
        entetes = dict(kw.get("entetes") or {})  # type: ignore[call-overload]
        self.appels.append((url, entetes))
        if self.statut == 0:
            raise reseau.ErreurReseau("haveibeenpwned.com injoignable")
        if "breachedaccount" in url:
            return reseau.Reponse(200, json.dumps([{"Name": "Vinted2024"}]).encode(), url)
        return reseau.Reponse(self.statut, json.dumps(self.liste).encode(), url)


def _base_avec_comptes(tmp_path: Path) -> db.Base:
    base = db.Base(tmp_path / "b.db")
    inv = inventaire.Inventaire()
    for brut in (
        b"From: <no-reply@vinted.fr>\r\nSubject: Bienvenue !\r\nDate: Mon, 3 Jan 2022 10:00:00 +0100\r\n\r\n",
        b"From: <no-reply@accounts.google.com>\r\nSubject: Nouvelle connexion\r\n\r\n",
        b"From: <no-reply@deezer.com>\r\nSubject: Welcome to Deezer\r\nDate: Mon, 3 Jan 2018 10:00:00 +0100\r\n\r\n",
        b"From: <news@lemonde.fr>\r\nSubject: La lettre\r\nList-Unsubscribe: <x>\r\n\r\n",
    ):  # fmt: skip
        obs = inventaire.observer(brut)
        assert obs is not None
        inv.ajouter_mail(obs)
    inventaire.enregistrer(base, inv)
    return base


class Notes:
    def __init__(self) -> None:
        self.envoyees: list[tuple[str, str]] = []

    def notifier(self, titre: str, texte: str, sous_titre: str = "") -> bool:
        self.envoyees.append((titre, texte))
        return True


def _notifieur(base: db.Base, heure: int = 14) -> tuple[Notifieur, Notes]:
    notes = Notes()
    t = dt.datetime(2026, 10, 6, heure, 0).timestamp()
    return Notifieur(base, notes, config.charger(), horloge=lambda: t), notes  # type: ignore[arg-type]


def test_lire_ecarte_spam_fabrique_et_sans_domaine() -> None:
    fuites = hibp.lire(json.dumps(FIXTURE).encode())
    assert [f.nom for f in fuites] == ["Vinted2024", "GoogleForum", "Avant", "Inconnu"]
    assert fuites[0].date == dt.date(2024, 3, 1) and fuites[0].donnees[1] == "Passwords"
    assert hibp.lire(b"pas du json") == [] and hibp.lire(b"{}") == []


def test_croisement_sous_domaines_alias_et_date(tmp_path: Path) -> None:
    base = _base_avec_comptes(tmp_path)
    comptes = croisement.comptes_surveilles(base)
    assert {c.service for c in comptes} == {"vinted", "google", "deezer"}  # pas l'abonnement au Monde
    res = croisement.croiser(hibp.lire(json.dumps(FIXTURE).encode()), comptes)
    assert [c.fuite.nom for c in res] == ["Vinted2024", "GoogleForum"]  # deezer : fuite antérieure au compte
    assert "tout de suite" in res[0].que_faire and "par précaution" in res[1].que_faire


def test_une_seule_notification_par_fuite(tmp_path: Path) -> None:
    base = _base_avec_comptes(tmp_path)
    faux = FauxHibp()
    notifieur, notes = _notifieur(base)
    r = rapport.verifier(config.chemins(), config.charger(), base, notifieur, faux)
    assert r.bilan.premier_passage and len(r.bilan.nouvelles) == 2
    assert notes.envoyees == [("🛡️ 2 fuite(s) ancienne(s) touchent tes comptes",
                               "Le détail et quoi faire : bouclier fuites, ou le tableau de bord.")]  # fmt: skip
    assert faux.appels[0][0] == hibp.URL_LISTE
    r = rapport.verifier(config.chemins(), config.charger(), base, notifieur, faux)
    assert r.bilan.nouvelles == [] and len(notes.envoyees) == 1 and len(faux.appels) == 1  # liste du jour en cache
    nouvelle = {"Name": "Google2026", "Title": "Google", "Domain": "google.com", "BreachDate": "2026-09-01",
                "DataClasses": ["Email addresses", "Phone numbers"]}  # fmt: skip
    faux.liste = [*FIXTURE, nouvelle]
    r = rapport.verifier(config.chemins(), config.charger(), base, notifieur, faux, forcer=True)
    assert [c.fuite.nom for c in r.bilan.nouvelles] == ["Google2026"]
    assert notes.envoyees[-1][0] == "⚠️ Fuite de données chez Google (Gmail, YouTube)"
    assert "numéros de téléphone" in notes.envoyees[-1][1]
    rapport.verifier(config.chemins(), config.charger(), base, notifieur, faux, forcer=True)
    assert len(notes.envoyees) == 2  # jamais deux fois


def test_liste_injoignable_garde_la_copie(tmp_path: Path) -> None:
    base = _base_avec_comptes(tmp_path)
    notifieur, _ = _notifieur(base)
    r = rapport.verifier(config.chemins(), config.charger(), base, notifieur, FauxHibp(statut=0))
    assert "injoignable" in r.liste and r.bilan.toutes == []
    rapport.verifier(config.chemins(), config.charger(), base, notifieur, FauxHibp())
    r = rapport.verifier(config.chemins(), config.charger(), base, notifieur, FauxHibp(statut=0), forcer=True)
    assert "copie précédente gardée" in r.liste and len(r.bilan.toutes) == 2
    r = rapport.verifier(config.chemins(), config.charger(), base, notifieur, FauxHibp(statut=503), forcer=True)
    assert "illisible (code 503)" in r.liste and len(r.bilan.toutes) == 2


def test_option_payante_par_adresse(tmp_path: Path) -> None:
    base = _base_avec_comptes(tmp_path)
    reglages = config.charger()
    reglages["fuites"]["cle_hibp"] = "cle-de-test"
    reglages["gmail"]["adresse"] = "camille@example.org"
    faux = FauxHibp()
    notifieur, _ = _notifieur(base)
    r = rapport.verifier(config.chemins(), reglages, base, notifieur, faux)
    assert r.adresse_verifiee and [c.confirmee for c in r.bilan.toutes] == [True, False]
    url, entetes = faux.appels[-1]
    assert url.startswith(hibp.URL_ADRESSE + "camille%40example.org") and entetes == {"hibp-api-key": "cle-de-test"}
    assert hibp.par_adresse("a@b.fr", "") is None and hibp.par_adresse("pas-une-adresse", "k") is None

    def introuvable(url: str, **kw: object) -> reseau.Reponse:
        return reseau.Reponse(404, b"", url)

    assert hibp.par_adresse("a@b.fr", "k", introuvable) == set()


def test_traductions() -> None:
    assert traductions.traduire(["Passwords", "Email addresses", "Truc inconnu"]) == [
        "mots de passe", "adresses e-mail", "truc inconnu"]  # fmt: skip
    assert traductions.mots_de_passe_concernes(["Password hints"]) and not traductions.mots_de_passe_concernes(
        ["Names"]
    )


def test_tableau_de_bord_et_attribution(tmp_path: Path) -> None:
    base = _base_avec_comptes(tmp_path)
    assert "pas encore été téléchargée" in tableau_de_bord.construire(base)
    notifieur, _ = _notifieur(base)
    rapport.verifier(config.chemins(), config.charger(), base, notifieur, FauxHibp())
    html = tableau_de_bord.construire(base)
    assert "Fuites qui touchent tes comptes (2)" in html and "mots de passe" in html
    assert "Have I Been Pwned" in html and "CC BY 4.0" in html


def test_cli_fuites(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base_avec_comptes(config.chemins().support)
    base.fermer()
    (config.chemins().support / "b.db").replace(config.chemins().base)

    def executer(args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        return Resultat(0, "")

    rapport_verifier = rapport.verifier
    monkeypatch.setattr(rapport, "verifier", lambda *a, **k: rapport_verifier(*a, telecharger=FauxHibp(), **k))
    assert cli.main(["fuites"], Systeme(executer, mac=False)) == 0
    sortie = capsys.readouterr().out
    assert "⚠️ Vinted (03/2024)" in sortie and "Mozilla Monitor" in sortie and "👉 Change ce mot de passe" in sortie
