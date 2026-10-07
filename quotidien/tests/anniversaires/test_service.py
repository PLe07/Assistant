"""Les rappels J-7, J-1 et J émis exactement une fois (horloge simulée), groupés, silencieux la nuit, rattrapés
seulement s'ils servent encore ; le message prêt ouvert dans Messages (jamais envoyé) ; la commande."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quotidien import cli, config
from quotidien.anniversaires import service
from quotidien.anniversaires.dates import DateNaissance
from quotidien.anniversaires.proches import Personne
from quotidien.db import Base as BaseDonnees
from quotidien.systeme import Resultat, Systeme

PARIS = ZoneInfo("Europe/Paris")
LEA = Personne("lea", "Léa", "Exemple", DateNaissance(14, 10, 2001), "ami_proche", "drole", ("adore le foot",),
               "06 11 22 33 44", "contacts", True)  # fmt: skip
HUGO = Personne("hugo", "Hugo", "Martin", DateNaissance(14, 10), None, "sobre", source="contacts")
COLLEGUE = Personne("col", "Inès", "Durand", DateNaissance(15, 10, 1990), "collegue", "formel", source="contacts")
BISSEXTILE = Personne("feb", "Noé", "", DateNaissance(29, 2, 2004), "famille", "tendre")


def t(jour: int, heure: int, minute: int = 0, mois: int = 10, annee: int = 2026) -> float:
    return datetime(annee, mois, jour, heure, minute, tzinfo=PARIS).timestamp()


class Mac:
    """Un faux Mac qui enregistre chaque commande (aucune n'est exécutée)."""

    def __init__(self, choix: str = "") -> None:
        self.appels: list[list[str]] = []
        self.entrees: list[str | None] = []
        self.choix = choix

    def __call__(self, args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        self.appels.append(list(args))
        self.entrees.append(entree)
        script = " ".join(args)
        if "choose from list" in script:
            return Resultat(0, self.choix)
        return Resultat(0, "")

    def notifications(self) -> list[str]:
        return [" ".join(a[4:6]) for a in self.appels if a[:1] == ["osascript"] and "display notification" in a[2]]


@pytest.fixture
def db(maison: Path) -> BaseDonnees:
    return BaseDonnees(config.chemin_base())


def _simuler(db: BaseDonnees, personnes: list[Personne], debut: float, fin: float, pas_minutes: int = 15,
             reglages: config.Reglages | None = None) -> tuple[Mac, list[tuple[float, str]]]:  # fmt: skip
    mac = Mac()
    s = Systeme(mac, mac=True)
    r = reglages or config.defauts()
    r.reglages["anniversaires"]["dialogue"] = False
    emis: list[tuple[float, str]] = []
    instant = debut
    while instant <= fin:
        emis += [(instant, x) for x in service.emettre(db, r, s, personnes, instant)]
        instant += pas_minutes * 60
    return mac, emis


def test_j7_j1_j_exactement_une_fois(db: BaseDonnees) -> None:
    mac, emis = _simuler(db, [LEA, HUGO, COLLEGUE], t(1, 0), t(16, 23, 45))
    textes = [x for _, x in emis]
    assert textes == [
        "🎁 Dans 7 jours — Anniversaire de Léa (25 ans), mercredi 14 octobre. Une idée de cadeau ?",
        "🎂 Demain — Anniversaires de Hugo et Léa (25 ans) → message prêt.",
        "🎂 Aujourd'hui — Anniversaires de Hugo et Léa (25 ans). Message prêt : ouvre-le et envoie-le toi-même.",
        "🎂 Demain — Anniversaire de Inès (36 ans) → message prêt.",
        "🎂 Aujourd'hui — Anniversaire de Inès (36 ans). Message prêt : ouvre-le et envoie-le toi-même.",
    ]
    heures = [datetime.fromtimestamp(x, PARIS).strftime("%d %H:%M") for x, _ in emis]
    assert heures == ["07 10:00", "13 19:30", "14 09:00", "14 19:30", "15 09:00"]
    assert len(mac.notifications()) == 5
    assert db.cx.execute("SELECT COUNT(*) FROM anniversaires_emis").fetchone()[0] == 7  # 2 + 2 + 2 + 1 (pas de J-7)
    # Relancer la même semaine (redémarrage du démon) : rien de plus.
    _, encore = _simuler(db, [LEA, HUGO, COLLEGUE], t(1, 0), t(16, 23, 45), pas_minutes=60)
    assert encore == []
    # Le message est prêt dès la veille, une seule fois par anniversaire.
    assert db.cx.execute("SELECT COUNT(*) FROM messages_prets").fetchone()[0] == 3


def test_rattrapage_seulement_utile_et_jamais_la_nuit(db: BaseDonnees) -> None:
    # Le Mac dort du 12 au 14 à 8 h : J-7 et J-1 sont passés, et ne servent plus ; J est émis à 9 h.
    _, emis = _simuler(db, [LEA], t(14, 8), t(14, 12))
    assert [x for _, x in emis] == [
        "🎂 Aujourd'hui — Anniversaire de Léa (25 ans). Message prêt : ouvre-le et envoie-le toi-même."
    ]
    db.cx.execute("DELETE FROM anniversaires_emis")
    # Réveil le 8 à 15 h : le J-7 (prévu le 7 à 10 h) sert encore, il part avec le bon nombre de jours.
    _, emis = _simuler(db, [LEA], t(8, 15), t(8, 16))
    assert [x for _, x in emis] == ["🎁 Dans 6 jours — Anniversaire de Léa (25 ans), mercredi 14 octobre. Une idée "
                                    "de cadeau ?"]  # fmt: skip
    # Réveil à 23 h 30 la veille : rien avant 7 h ; à 7 h le J-1 ne sert plus (c'est le jour même), on attend 9 h.
    db.cx.execute("DELETE FROM anniversaires_emis")
    _, emis = _simuler(db, [LEA], t(13, 23, 30), t(14, 9))
    assert [datetime.fromtimestamp(x, PARIS).strftime("%d %H:%M") for x, _ in emis] == ["14 09:00"]
    assert service.en_silence(t(13, 23, 30), config.defauts().reglages)
    assert service.en_silence(t(14, 6, 59), config.defauts().reglages)
    assert not service.en_silence(t(14, 7, 0), config.defauts().reglages)


def test_29_fevrier_les_annees_non_bissextiles(db: BaseDonnees) -> None:
    _, emis = _simuler(db, [BISSEXTILE], t(27, 0, mois=2, annee=2027), t(1, 23, mois=3, annee=2027), pas_minutes=30)
    heures = [datetime.fromtimestamp(x, PARIS).strftime("%d/%m %H:%M") for x, _ in emis]
    assert heures == ["27/02 19:30", "28/02 09:00"]
    r = config.defauts()
    r.reglages["anniversaires"]["date_29_fevrier"] = "01-03"
    db.cx.execute("DELETE FROM anniversaires_emis")
    _, emis = _simuler(db, [BISSEXTILE], t(27, 0, mois=2, annee=2027), t(1, 23, mois=3, annee=2027), 30, r)
    # Le J-7 (prévu le 22/02, le Mac « dormait ») sert encore le 27 : rattrapé, avec le bon nombre de jours.
    assert [datetime.fromtimestamp(x, PARIS).strftime("%d/%m") for x, _ in emis] == ["27/02", "28/02", "01/03"]
    assert emis[0][1].startswith("🎁 Dans 2 jours — Anniversaire de Noé (23 ans), lundi 1 mars.")


def test_fetes_en_option(db: BaseDonnees) -> None:
    lea_fete = Personne("lf", "Léa", "", DateNaissance(1, 1, 2000), "ami", "sobre")
    _, emis = _simuler(db, [lea_fete], t(22, 0, mois=3), t(22, 23, mois=3))
    assert emis == []  # désactivé par défaut
    r = config.defauts()
    r.reglages["anniversaires"]["fetes"] = True
    _, emis = _simuler(db, [lea_fete], t(22, 0, mois=3), t(22, 23, mois=3), reglages=r)
    assert [x for _, x in emis] == ["🌼 Bonne fête — C'est la fête de Léa aujourd'hui → petit message prêt."]
    assert service.jour_de_fete("Zzz", 2026) is None and service.jour_de_fete("", 2026) is None
    assert service.jour_de_fete("Marie Anne", 2026) == date(2026, 8, 15)


def test_ouvrir_dans_messages_jamais_envoyer(db: BaseDonnees) -> None:
    mac = Mac()
    s = Systeme(mac, mac=True)
    r = config.defauts()
    m = service.message_pret(db, r.reglages, LEA, date(2026, 10, 14), t(13, 19))
    mac.choix = m.variantes[1]
    service.emettre(db, r, s, [LEA], t(14, 9))  # dialogue activé par défaut
    choisir = [a for a in mac.appels if a[:1] == ["osascript"] and "choose from list" in a[2]]
    assert len(choisir) == 1 and choisir[0][4:7] == ["Message pour Léa", choisir[0][5], "Ouvrir dans Messages"]
    assert choisir[0][7:] == m.variantes
    ouvert = [a for a in mac.appels if a[:1] == ["open"]]
    assert len(ouvert) == 1 and ouvert[0][1].startswith("sms:")
    assert "pbcopy" in [a[0] for a in mac.appels] and m.variantes[1] in mac.entrees
    # « Plus tard » : rien n'est ouvert.
    mac2 = Mac(choix="")
    assert not service.proposer_envoi(db, r.reglages, Systeme(mac2, mac=True), LEA, date(2026, 10, 14), t(14, 9))
    assert not [a for a in mac2.appels if a[:1] == ["open"]]
    # Choix direct d'une variante (commande).
    mac3 = Mac()
    assert service.proposer_envoi(db, r.reglages, Systeme(mac3, mac=True), LEA, date(2026, 10, 14), t(14, 9), 3)
    assert [a for a in mac3.appels if a[:1] == ["open"]]


def test_ligne_du_brief() -> None:
    assert (
        service.ligne_brief([LEA, HUGO], date(2026, 10, 13))
        == "🎂 Demain : anniversaires de Hugo et Léa → message prêt."
    )
    assert service.ligne_brief([LEA, COLLEGUE], date(2026, 10, 14)) == (
        "🎂 Aujourd'hui : anniversaire de Léa → message prêt · Demain : anniversaire de Inès → message prêt."
    )
    assert service.ligne_brief([LEA], date(2026, 10, 1)) is None
    assert [p.prenom for _, p in service.a_venir([LEA, HUGO, COLLEGUE, BISSEXTILE], date(2026, 10, 1), 30)] == [
        "Hugo", "Léa", "Inès"]  # fmt: skip


def test_annuaire_contacts_et_proches(maison: Path) -> None:
    config.dossier_support().mkdir(parents=True, exist_ok=True)
    (config.dossier_support() / "proches.toml").write_text(
        '[[personne]]\nprenom = "Léa"\nrelation = "couple"\n\n[[personne]]\nprenom = "Mamie"\nanniversaire = "05/06"\n'
        'relation = "famille"\n', encoding="utf-8")  # fmt: skip
    bruts = [{"identifiant": "1", "prenom": "Léa", "nom": "X", "jour": 14, "mois": 10, "annee": 2001}]
    a = service.annuaire(config.charger(), date(2026, 10, 7), lambda: ("ok", bruts))
    assert a.statut_contacts == "ok"
    assert [(p.prenom, p.relation) for p in a.personnes] == [("Léa", "couple"), ("Mamie", "famille")]
    refuse = service.annuaire(config.charger(), date(2026, 10, 7), lambda: ("refuse", []))
    assert refuse.statut_contacts == "refuse" and [p.prenom for p in refuse.personnes] == ["Mamie"]  # mode dégradé
    r = config.charger()
    r.reglages["anniversaires"]["contacts"] = False
    sans = service.annuaire(r, date(2026, 10, 7), lambda: pytest.fail("Contacts lus malgré le réglage"))  # type: ignore[arg-type,return-value]
    assert sans.statut_contacts == "desactive" and [p.prenom for p in sans.personnes] == ["Mamie"]


def test_cli(maison: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from quotidien.anniversaires import contacts

    bruts: list[dict[str, Any]] = [
        {"identifiant": "1", "prenom": "Léa", "nom": "X", "jour": 14, "mois": 10, "annee": 2001,
         "telephones": [("mobile", "06 11")]},
        {"identifiant": "2", "prenom": "Hugo", "nom": "Y", "jour": 2, "mois": 1, "annee": None},
    ]  # fmt: skip
    monkeypatch.setattr(contacts, "contacts_du_mac", lambda: ("ok", bruts))
    monkeypatch.setattr(contacts, "demander_acces", lambda: "ok")
    mac = Mac()
    s = Systeme(mac, mac=True)
    horloge = lambda: t(7, 12)  # noqa: E731
    assert cli.main(["anniversaires"], s, horloge) == 0
    sortie = capsys.readouterr().out
    assert "Contacts : accès accordé · 2 anniversaire(s)" in sortie
    assert "mercredi 14 octobre · Léa (25 ans)" in sortie and "samedi 2 janvier · Hugo" in sortie
    assert cli.main(["anniversaires", "message", "léa"], s, horloge) == 0
    sortie = capsys.readouterr().out
    assert sortie.count("\n1. ") + sortie.startswith("1. ") == 1 and "\n3. " in sortie and "Léa" in sortie
    assert cli.main(["anniversaires", "message", "Zoé"], s, horloge) == 1
    assert "Personne ne s'appelle Zoé" in capsys.readouterr().out
    assert cli.main(["anniversaires", "ouvrir", "Léa", "2"], s, horloge) == 0
    assert [a for a in mac.appels if a[:1] == ["open"] and a[1].startswith("sms:")]
    assert cli.main(["anniversaires", "ouvrir", "Léa", "9"], s, horloge) == 2
    assert cli.main(["anniversaires", "ouvrir"], s, horloge) == 2
    monkeypatch.setattr(contacts, "contacts_du_mac", lambda: ("refuse", []))
    monkeypatch.setattr(contacts, "demander_acces", lambda: "refuse")
    assert cli.main(["anniversaires"], s, horloge) == 0
    sortie = capsys.readouterr().out
    assert "Contacts : accès refusé" in sortie and "Aucun anniversaire" in sortie


def test_nettoyage_des_vieux_messages(db: BaseDonnees) -> None:
    r = config.defauts().reglages
    service.message_pret(db, r, LEA, date(2026, 10, 14), t(13, 19))
    service.message_pret(db, r, HUGO, date(2026, 12, 20), t(13, 19) + 70 * 86400)
    assert [x[0] for x in db.lignes("SELECT cle FROM messages_prets")] == ["hugo/2026-12-20"]
    assert service.echeances([Personne("x", "X", "", DateNaissance(0, 0))], date(2026, 1, 1), r) == []
    assert timedelta(days=1)
