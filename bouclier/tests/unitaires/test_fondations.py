"""Fondations : réglages, caviardage, base, journal, notifications, interface du Mac."""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from bouclier import caviardage, config, db, journal
from bouclier.notifier import Notifieur
from bouclier.systeme import Resultat, Systeme, executer_vraiment


class FauxExecuteur:
    def __init__(self, reponses: dict[str, Resultat] | None = None) -> None:
        self.appels: list[list[str]] = []
        self.reponses = reponses or {}

    def __call__(self, args: Sequence[str], entree: str | None = None, delai: float = 60) -> Resultat:
        self.appels.append(list(args))
        return self.reponses.get(args[0], Resultat(0, "ok\n"))


# --- Réglages ----------------------------------------------------------------------------------------------------


def test_config_defauts_et_fusion(maison: Path) -> None:
    c = config.chemins()
    assert c.support == maison / "Library" / "Application Support" / "Bouclier"
    assert config.charger(c)["ia"]["budget_mensuel_usd"] == 2.0
    assert config.ecrire_modele_si_absent(c)
    assert not config.ecrire_modele_si_absent(c)
    assert oct(os.stat(c.config).st_mode & 0o777) == "0o600"
    c.config.write_text("[ia]\nbudget_mensuel_usd = 1\nmodele = 3\n[nouveau]\nx = 1\n", encoding="utf-8")
    r = config.charger(c)
    assert r["ia"]["budget_mensuel_usd"] == 1  # un entier accepté pour un réel
    assert r["ia"]["modele"] == "claude-haiku-4-5"  # mauvais type : défaut gardé
    assert r["nouveau"] == {"x": 1}


def test_config_abimee(maison: Path) -> None:
    c = config.chemins()
    c.support.mkdir(parents=True)
    c.config.write_text("[ia\n", encoding="utf-8")
    with pytest.raises(config.ConfigIllisible):
        config.charger(c)
    reglages, erreur = config.charger_ou_defauts(c)
    assert reglages["ia"]["active"] and erreur and "config.toml" in erreur


def test_chemins_icloud(maison: Path) -> None:
    c = config.chemins()
    assert c.entrees()[0].as_posix().endswith("com~apple~CloudDocs/Bouclier/entree")
    assert "iCloud~is~workflow~my~workflows/Documents/Bouclier/entree" in c.entrees()[1].as_posix()
    config.preparer_dossiers(c)
    assert oct(os.stat(c.support).st_mode & 0o777) == "0o700"
    assert not c.icloud.exists()  # jamais créé hors installation


# --- Caviardage ----------------------------------------------------------------------------------------------------

PERSO = {
    "noms": ["Camille Durand"],
    "telephones": ["06 12 34 56 78"],
    "adresses": ["12 rue des Lilas"],
    "emails": ["camille.durand@example.org"],
}


def test_caviardage_donnees_declarees_et_formes() -> None:
    texte = (
        "Bonjour Camille DURAND, votre IBAN FR76 3000 6000 0112 3456 7890 189 et la carte 4970 1012 3456 7893 "
        "sont bloqués. Appelez le 0612345678 ou écrivez à camille.durand@example.org. "
        "Livraison au 12, Rue des Lilas 33000 Bordeaux. Votre code de validation : 482913. "
        "Lien : https://suivi.example/colis?id=CAMILLE-123#x"
    )
    sortie = caviardage.caviarder(texte, PERSO)
    for interdit in ("Camille", "DURAND", "FR76", "4970", "0612345678", "camille.durand", "Lilas", "33000", "482913",
                     "CAMILLE-123"):  # fmt: skip
        assert interdit.lower() not in sortie.lower(), interdit
    assert "[NOM]" in sortie and "[IBAN]" in sortie and "[CARTE]" in sortie and "[CODE]" in sortie
    assert "https://suivi.example/colis?[…]" in sortie


def test_caviardage_garde_les_indices() -> None:
    sortie = caviardage.caviarder("Rappelez vite le 08 99 12 34 56 ou le +33 6 11 22 33 44, ou mail x@evil.top")
    assert "[TÉLÉPHONE 089…]" in sortie and "[TÉLÉPHONE]" in sortie and "[E-MAIL]@evil.top" in sortie
    # Un nombre qui n'est ni une carte (Luhn faux) ni un IBAN reste tel quel.
    assert "1234 5678 9012 3456" in caviardage.caviarder("colis 1234 5678 9012 3456")
    assert caviardage.caviarder("") == ""


def test_caviardage_accents_et_international() -> None:
    sortie = caviardage.caviarder("Hélène Écuyer appelle +44 20 7946 0958", {"noms": ["Helene Ecuyer"], "x": []})
    assert "Hélène" not in sortie and "[NOM]" in sortie and "[TÉLÉPHONE]" in sortie
    assert caviardage.caviarder("abc", {"noms": ["ab"]}) == "abc"  # trop court pour être sûr
    assert not caviardage._iban_valide("FR76 3000")
    assert not caviardage._iban_valide("FR7A30006000011234567890189")


# --- Base ---------------------------------------------------------------------------------------------------------


def test_base_cree_en_600_et_meta(tmp_path: Path) -> None:
    b = db.ouvrir(tmp_path / "b.db")
    assert oct(os.stat(tmp_path / "b.db").st_mode & 0o777) == "0o600"
    b.ecrire_meta("x", "1")
    assert b.lire_meta("x") == "1" and b.lire_meta("absent", "d") == "d"
    b.fermer()


def test_base_abimee_mise_de_cote(tmp_path: Path) -> None:
    chemin = tmp_path / "b.db"
    chemin.write_bytes(b"ceci n'est pas une base" * 100)
    (tmp_path / "b.db-journal").write_bytes(b"x")
    b = db.ouvrir(chemin)
    assert b.mise_de_cote is not None and b.mise_de_cote.exists()
    b.ecrire_meta("ok", "oui")
    assert b.lignes("SELECT COUNT(*) AS n FROM analyses")[0]["n"] == 0
    b.fermer()


# --- Journal ------------------------------------------------------------------------------------------------------


def test_journal_caviarde(tmp_path: Path) -> None:
    log = journal.configurer(tmp_path, {"noms": ["Camille Durand"]})
    log.info("message de %s au %s", "Camille Durand", "06 12 34 56 78")
    try:
        raise ValueError("Camille Durand 4970101234567893")
    except ValueError:
        log.exception("échec pour Camille Durand")
    for h in log.handlers:
        h.flush()
    contenu = (tmp_path / "bouclier.log").read_text(encoding="utf-8")
    assert "Camille" not in contenu and "06 12" not in contenu and "4970" not in contenu
    assert "[NOM]" in contenu and "[ValueError]" in contenu
    journal.configurer(tmp_path, console=True)  # reconfigurer ne double pas les sorties
    assert len(journal.log().handlers) == 2


def test_journal_message_mal_forme(tmp_path: Path) -> None:
    log = journal.configurer(tmp_path)
    log.info("deux %s %s", "seul")
    for h in log.handlers:
        h.flush()
    assert "deux" in (tmp_path / "bouclier.log").read_text(encoding="utf-8")


# --- Interface du Mac --------------------------------------------------------------------------------------------


def test_systeme_commandes_construites() -> None:
    ex = FauxExecuteur({"security": Resultat(0, "secret\n")})
    s = Systeme(ex, mac=True)
    assert s.notifier("Titre « x »", 'texte "guillemets"', "sous")
    assert ex.appels[-1][0] == "osascript" and ex.appels[-1][-3:] == ["Titre « x »", 'texte "guillemets"', "sous"]
    assert s.trousseau_lire("bouclier-gmail", "moi@example.org") == "secret"
    assert ex.appels[-1] == ["security", "find-generic-password", "-s", "bouclier-gmail", "-a", "moi@example.org", "-w"]
    assert s.telecharger_icloud(Path("/x/y.txt")) and ex.appels[-1][:2] == ["brctl", "download"]
    assert s.dialogue("T", "x") and s.ouvrir(Path("/x")) and s.ouvrir_editeur(Path("/x"))
    assert s.presse_papiers() == "ok\n"
    assert s.corbeille(Path("/x/photo.jpg"))  # pas de Foundation ici : le Finder
    assert ex.appels[-1][0] == "osascript" and ex.appels[-1][-1] == "/x/photo.jpg"


def test_systeme_trousseau_ecriture_limitee(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Systeme(FauxExecuteur(), mac=True)
    vus: list[list[str]] = []
    monkeypatch.setattr(s, "interactif", lambda args: vus.append(list(args)) or 0)
    assert not s.trousseau_ecrire_interactif("assistant-gmail", "moi")  # jamais l'élément d'un autre projet
    assert s.trousseau_ecrire_interactif("bouclier-gmail", "moi")
    assert vus == [["security", "add-generic-password", "-U", "-s", "bouclier-gmail", "-a", "moi", "-w"]]


def test_systeme_hors_mac() -> None:
    ex = FauxExecuteur({"xclip": Resultat(1, "")})
    s = Systeme(ex, mac=False)
    assert not s.notifier("t", "x") and not s.dialogue("t", "x") and s.trousseau_lire("s") is None
    assert not s.telecharger_icloud(Path("/x")) and not s.corbeille(Path("/x")) and not s.permettre_icloud()
    assert not s.trousseau_ecrire_interactif("bouclier-gmail", "moi")
    assert s.presse_papiers() == ""
    assert s.ouvrir(Path("/x")) and ex.appels[-1][0] == "xdg-open"
    assert s.commande_existe("python3") and not s.commande_existe("commande-qui-n-existe-pas")


def test_executer_vraiment() -> None:
    assert executer_vraiment(["python3", "-c", "print(1)"]).sortie.strip() == "1"
    assert executer_vraiment(["commande-qui-n-existe-pas"]).code == 127
    assert executer_vraiment(["python3", "-c", "import time; time.sleep(5)"], delai=0.2).code == 124
    s = Systeme(mac=False)
    assert s.interactif(["true"]) == 0 and s.interactif(["commande-qui-n-existe-pas"]) == 127
    assert Systeme(mac=True).permettre_icloud() is False  # pas de libSystem ici


# --- Notifications -------------------------------------------------------------------------------------------------


def _notifieur(tmp_path: Path, heure: int) -> tuple[Notifieur, FauxExecuteur, list[float]]:
    lt = time.localtime()
    t = [time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, heure, 30, 0, 0, 0, -1))]
    ex = FauxExecuteur()
    n = Notifieur(db.ouvrir(tmp_path / "n.db"), Systeme(ex, mac=True), config.DEFAUTS, horloge=lambda: t[0])
    return n, ex, t


def test_notifications_plafond_de_3(tmp_path: Path) -> None:
    n, ex, _ = _notifieur(tmp_path, 14)
    assert [n.envoyer("fuite", f"F{i}", "x") for i in range(5)] == [True, True, True, False, False]
    assert n.envoyer("arnaque", "réponse", "x", reponse_a_demande=True)  # hors plafond
    assert len(ex.appels) == 4 and n.envoyees_aujourdhui() == 3


def test_notifications_nuit_puis_8h(tmp_path: Path) -> None:
    n, ex, t = _notifieur(tmp_path, 2)
    assert n.en_silence()
    assert not n.envoyer("arnaque", "Alerte de nuit", "x")
    assert ex.appels == []
    assert n.envoyer("arnaque", "Réponse", "x", reponse_a_demande=True)  # une réponse part même la nuit
    assert n.envoyer_en_attente() == 0  # toujours la nuit
    t[0] += 6 * 3600  # 8 h 30
    assert not n.en_silence()
    assert n.envoyer_en_attente() == 1
    assert ex.appels[-1][-3] == "Alerte de nuit"
    assert n.envoyer_en_attente() == 0


def test_notifications_silence_sans_chevauchement(tmp_path: Path) -> None:
    n, _, _ = _notifieur(tmp_path, 13)
    n.reglages = {"silence_debut": 12, "silence_fin": 14, "max_par_jour": 3}
    assert n.en_silence()
