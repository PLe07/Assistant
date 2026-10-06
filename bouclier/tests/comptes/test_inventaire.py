"""§11.3 : l'inventaire sur une boîte imitée de 60 services (précision et rappel ≥ 90 %), la lecture seule absolue,
les navigateurs (la colonne mot de passe n'est jamais lue), le regroupement par service, les statuts."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from bouclier import db
from bouclier.comptes import imap_lecture_seule as imap
from bouclier.comptes import inventaire, navigateurs, regroupement
from tests.comptes.boite_simulee import FauxImap, generer

RACINE = Path(__file__).resolve().parents[2] / "bouclier"


@pytest.fixture
def base(tmp_path: Path) -> db.Base:
    return db.Base(tmp_path / "b.db")


def _lecteur(faux: FauxImap) -> imap.LecteurImap:
    lecteur = imap.LecteurImap(fabrique=lambda serveur: faux)
    lecteur.connecter("moi@example.org", "bon")
    return lecteur


# --- Précision et rappel -------------------------------------------------------------------------------------------


def test_precision_et_rappel_sur_60_services(base: db.Base) -> None:
    messages, comptes, abonnements = generer()
    assert len(comptes) + len(abonnements) == 60
    faux = FauxImap(messages)
    inv = inventaire.Inventaire()
    r = inventaire.releve_gmail(_lecteur(faux), base, inv, lot=50)
    assert r.dossier == "[Gmail]/Tous les messages" and r.lus == len(messages)
    trouves = {i for i, c in inv.comptes.items() if c.nature == "compte"}
    abonnes = {i for i, c in inv.comptes.items() if c.nature == "abonnement"}
    vrais = len(trouves & comptes)
    precision, rappel = vrais / len(trouves), vrais / len(comptes)
    print(f"\nComptes : précision {precision:.0%}, rappel {rappel:.0%} ; abonnements {len(abonnes & abonnements)}/20")
    assert precision >= 0.9 and rappel >= 0.9
    assert len(abonnes & abonnements) >= 18
    assert not any(i.endswith(("gmail.com", "outlook.fr")) for i in inv.comptes)  # les personnes ne comptent pas
    assert faux.violations == []


def test_lecture_seule_absolue_drapeaux_identiques(base: db.Base) -> None:
    messages, _, _ = generer()
    faux = FauxImap(messages)
    lecteur = _lecteur(faux)
    lecteur.examiner("[Gmail]/Tous les messages")
    echantillon = sorted(faux.messages)[:20]
    avant = lecteur.drapeaux(echantillon)
    inventaire.releve_gmail(lecteur, base, inventaire.Inventaire())
    lecteur.message(echantillon[0], 5_000_000)
    apres = lecteur.drapeaux(echantillon)
    assert avant == apres and len(avant) == 20 and any("\\Seen" in d for d in avant.values())
    assert faux.violations == []
    assert all(c[0] in ("LOGIN", "LIST", "EXAMINE", "UID") for c in faux.commandes)
    assert all(c[1] in ("SEARCH", "FETCH") for c in faux.commandes if c[0] == "UID")
    lecteur.fermer()
    assert faux.commandes[-1] == ("LOGOUT",)


@pytest.mark.parametrize(
    "elements",
    ["(BODY[])", "(RFC822)", "(RFC822.TEXT)", "(BINARY[1])", "(BODY[HEADER])", "(UID BODY[]<0.100>)", "(FLAGS) STORE"],
)
def test_elements_qui_marqueraient_comme_lu_refuses(elements: str) -> None:
    with pytest.raises(imap.ImapInterdit):
        imap.verifier_elements(elements)


def test_commandes_interdites_jamais_envoyees() -> None:
    faux = FauxImap(generer()[0])
    lecteur = _lecteur(faux)
    with pytest.raises(imap.ImapInterdit):
        lecteur.uids_depuis(0)  # aucune boîte ouverte en lecture seule
    lecteur.examiner("INBOX")
    for commande in ("STORE", "COPY", "MOVE", "EXPUNGE"):
        with pytest.raises(imap.ImapInterdit):
            lecteur._uid(commande, "1", "+FLAGS (\\Seen)")
    assert faux.violations == [] and not any(c[0] == "UID" and c[1] != "SEARCH" for c in faux.commandes[3:])


def test_releve_incremental_et_uidvalidity(base: db.Base) -> None:
    messages, _, _ = generer()
    faux = FauxImap(messages)
    assert inventaire.releve_gmail(_lecteur(faux), base, inventaire.Inventaire()).lus == len(messages)
    assert inventaire.releve_gmail(_lecteur(faux), base, inventaire.Inventaire()).lus == 0  # rien de nouveau
    faux.validite = "999"  # la boîte a été recréée : on repart de zéro
    assert inventaire.releve_gmail(_lecteur(faux), base, inventaire.Inventaire()).lus == len(messages)


def test_erreurs_de_connexion() -> None:
    faux = FauxImap(generer()[0])
    faux.mot_de_passe = "autre"
    with pytest.raises(imap.ErreurImap, match="mot de passe d'application"):
        _lecteur(faux)

    def injoignable(serveur: str) -> FauxImap:
        raise OSError("réseau")

    with pytest.raises(imap.ErreurImap, match="injoignable"):
        imap.LecteurImap(fabrique=injoignable).connecter("a", "b")


def test_aucune_ecriture_imap_dans_le_code() -> None:
    """§11.2 : recherche automatisée dans tout fichier qui parle IMAP."""
    interdit = re.compile(r"\b(cx|imap|connexion|client|serveur)\.(store|copy|move|expunge|append|create|delete|rename"
                          r"|subscribe)\(|[\"'](STORE|COPY|MOVE|EXPUNGE)[\"']|readonly\s*=\s*False")  # fmt: skip
    fichiers = [f for f in RACINE.rglob("*.py") if "imaplib" in f.read_text(encoding="utf-8") or "imap" in f.name]
    assert fichiers
    for f in fichiers:
        assert not interdit.search(f.read_text(encoding="utf-8")), f


def test_seuls_nos_secrets_du_trousseau_sont_lus() -> None:
    from bouclier.systeme import Resultat, Systeme

    appels: list[list[str]] = []
    s = Systeme(lambda a, e, d: (appels.append(list(a)), Resultat(0, "secret"))[1], mac=True)
    assert s.trousseau_lire("bouclier-gmail", "moi") == "secret"
    assert s.trousseau_lire("Chrome Safe Storage") is None and s.trousseau_lire("assistant-gmail") is None
    assert len(appels) == 1


def test_aucune_lecture_de_mot_de_passe_dans_le_code() -> None:
    for f in RACINE.rglob("*.py"):
        texte = f.read_text(encoding="utf-8")
        assert "password_value" not in texte, f
        assert (
            not re.search(r"find-(generic|internet)-password[^\n]*-(g|w)\b(?![^\n]*bouclier-)", texte)
            or f.name == "systeme.py"
        )


# --- Navigateurs ---------------------------------------------------------------------------------------------------


def _login_data(chemin: Path, lignes: list[tuple[str, str]]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(chemin)
    cx.execute("CREATE TABLE logins (origin_url TEXT, username_value TEXT, password_value BLOB, signon_realm TEXT)")
    for site, nom in lignes:
        cx.execute("INSERT INTO logins VALUES (?, ?, ?, ?)", (site, nom, b"LEURRE-MOT-DE-PASSE", site))
    cx.commit()
    cx.close()


def test_navigateurs_sans_jamais_lire_le_mot_de_passe(maison: Path) -> None:
    support = maison / "Library" / "Application Support"
    _login_data(support / "Google/Chrome/Default/Login Data",
                [("https://www.vinted.fr/", "moi"), ("https://accounts.google.com/", "moi@exemple.org")])  # fmt: skip
    _login_data(support / "BraveSoftware/Brave-Browser/Profile 1/Login Data", [("https://www.doctolib.fr/", "x")])
    firefox = support / "Firefox/Profiles/abc.default/logins.json"
    firefox.parent.mkdir(parents=True)
    entree = {"hostname": "https://www.leboncoin.fr", "encryptedUsername": "U1", "encryptedPassword": "LEURRE-MDP"}
    firefox.write_text(json.dumps({"logins": [entree]}), encoding="utf-8")
    trace: list[str] = []
    avant = (support / "Google/Chrome/Default/Login Data").read_bytes()
    releve = navigateurs.relever(maison, trace)
    assert sorted(releve.navigateurs) == ["Brave", "Chrome", "Firefox"]
    assert {i.site for i in releve.identifiants} >= {"https://www.vinted.fr/", "https://www.leboncoin.fr"}
    assert trace and all("password" not in requete.lower() for requete in trace)
    assert all("LEURRE" not in repr(i) for i in releve.identifiants)
    assert (support / "Google/Chrome/Default/Login Data").read_bytes() == avant
    inv = inventaire.Inventaire()
    for ident in releve.identifiants:
        inv.ajouter_identifiant(ident)
    assert {"vinted", "google", "doctolib", "leboncoin"} <= {i for i, c in inv.comptes.items() if c.nature == "compte"}


def test_navigateur_abime_ou_absent(maison: Path) -> None:
    abime = maison / "Library/Application Support/Microsoft Edge/Default/Login Data"
    abime.parent.mkdir(parents=True)
    abime.write_bytes(b"pas une base")
    ff = maison / "Library/Application Support/Firefox/Profiles/x/logins.json"
    ff.parent.mkdir(parents=True)
    ff.write_text("{abîmé", encoding="utf-8")
    r = navigateurs.relever(maison)
    assert r.identifiants == [] and r.erreurs == []
    assert navigateurs.relever(maison / "vide").navigateurs == []


# --- Regroupement, enregistrement, statuts --------------------------------------------------------------------------


def test_regroupement() -> None:
    assert regroupement.identifier("accounts.google.com").id == "google"
    assert regroupement.identifier("mail.instagram.com").id == "instagram"
    assert regroupement.identifier("e.boursobank.com").id == "boursobank"
    inconnu = regroupement.identifier("news.petite-boutique.fr")
    assert (inconnu.id, inconnu.categorie, inconnu.connu) == ("petite-boutique.fr", "autre", False)
    base = regroupement.charger()
    francais = [s for s in base.services.values() if s.fr and s.suppression]
    assert len(francais) >= 150 and all(s.suppression and s.suppression.startswith("https://") for s in francais)
    assert base.sources["justdeleteme"]["licence"] == "MIT" and base.sources["2factorauth"]["licence"] == "MIT"
    assert regroupement.service("impots").difficulte == "impossible"  # type: ignore[union-attr]


def test_enregistrer_fusionne_et_garde_ton_statut(base: db.Base) -> None:
    inv = inventaire.Inventaire()
    obs = inventaire.observer(b"From: Vinted <no-reply@vinted.fr>\r\nSubject: Bienvenue !\r\nDate: Mon, 3 Jan 2022 "
                              b"10:00:00 +0100\r\n\r\n")  # fmt: skip
    assert obs is not None and obs.signaux == {"creation"}
    inv.ajouter_mail(obs)
    assert inventaire.enregistrer(base, inv) == 1
    assert inventaire.poser_statut(base, "vinted", "supprimer") and not inventaire.poser_statut(base, "rien", "garder")
    inv2 = inventaire.Inventaire()
    obs2 = inventaire.observer(b"From: Vinted <news@vinted.fr>\r\nSubject: =?utf-8?q?Nouveaut=C3=A9s?=\r\n"
                               b"Date: Tue, 5 Sep 2023 10:00:00 +0200\r\nList-Unsubscribe: <x>\r\n\r\n")  # fmt: skip
    assert obs2 is not None
    inv2.ajouter_mail(obs2)
    inventaire.enregistrer(base, inv2)
    [ligne] = inventaire.lignes(base)
    assert (ligne.nature, ligne.statut, ligne.premiere_vue, ligne.derniere_activite) == (
        "compte",
        "a_supprimer",
        "2022-01-03",
        "2023-09-05",
    )
    assert ligne.signaux == {"creation": 1} and ligne.service is not None and ligne.service.suppression
    assert inventaire.compter(base) == {"compte": 1}
    assert inventaire.domaines_des_comptes(base) == {"vinted": ["vinted.fr"]}
    inventaire.poser_statut(base, "vinted", "supprime")
    assert inventaire.domaines_des_comptes(base) == {}


def test_observer_entetes_bizarres() -> None:
    assert inventaire.observer(b"From: personne\r\nSubject: x\r\n\r\n") is None
    o = inventaire.observer(b"From: a@b.fr\r\nSubject: =?bad?q?x?=\r\nDate: pas une date\r\n\r\n")
    assert o is not None and o.date is None
