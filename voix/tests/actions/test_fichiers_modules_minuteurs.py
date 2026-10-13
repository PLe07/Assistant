"""Fichiers (chemins vérifiés, Spotlight numéroté), modules (commande publique, délai, README en lecture seule),
minuteurs (gardés sur disque, notification)."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.faux_mac import FauxMac
from voix.actions import modules
from voix.actions.base import CheminRefuse, adresse_ouvrable, chemin_ouvrable
from voix.actions.minuteur import Minuteurs, notifier
from voix.session import Session


def _fichier(p: Path, contenu: str = "x", age_s: float = 0) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenu)
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


# --- chemins et adresses ----------------------------------------------------------------------------------------


def test_chemin_ouvrable(mac: FauxMac, tmp_path: Path) -> None:
    m = mac.maison
    assert chemin_ouvrable(str(m / "Documents"), m, dossier=True) == str((m / "Documents").resolve())
    doc = _fichier(m / "Documents" / "a.pdf")
    assert chemin_ouvrable(str(doc), m, dossier=False) == str(doc.resolve())
    script = _fichier(m / "Documents" / "x.command")
    executable = _fichier(m / "Documents" / "outil")
    executable.chmod(0o755)
    dehors = _fichier(tmp_path / "ailleurs.txt")
    lien = m / "Documents" / "lien.txt"
    lien.symlink_to(dehors)
    for brut, raison in [(str(script), "s'exécute"), (str(executable), "exécutable"), (str(dehors), "hors"),
                         (str(lien), "hors"), ("relatif.txt", "relatif"), (str(m / "absent"), "introuvable"),
                         ("-a", "invalide"), (str(m / "Documents") + "\n", "invalide")]:  # fmt: skip
        with pytest.raises(CheminRefuse, match=raison):
            chemin_ouvrable(brut, m)
    with pytest.raises(CheminRefuse):
        chemin_ouvrable(str(doc), m, dossier=True)
    with pytest.raises(CheminRefuse):
        chemin_ouvrable(str(m / "Documents"), m, dossier=False)


def test_adresses() -> None:
    assert adresse_ouvrable("https://www.youtube.com") == "https://www.youtube.com"
    for mauvaise in ("http://x.fr", "file:///etc/passwd", "javascript:alert(1)", "https://x.fr/a b", "https://",
                     "https://x.fr/\"a", "ftp://x"):  # fmt: skip
        with pytest.raises(CheminRefuse):
            adresse_ouvrable(mauvaise)


# --- derniers fichiers -------------------------------------------------------------------------------------------


def test_dernier_pdf_telechargement_capture(mac: FauxMac) -> None:
    m = mac.maison
    _fichier(m / "Downloads" / "vieux.pdf", age_s=500)
    recent = _fichier(m / "Documents" / "recent.pdf", age_s=10)
    _fichier(m / "Downloads" / "encours.pdf.crdownload", age_s=0)
    _fichier(m / "Downloads" / "notes.txt", age_s=100)
    _fichier(m / "Downloads" / "piege.command", age_s=1)
    capture = _fichier(m / "Desktop" / "Capture d’écran 2026-10-13 à 09.00.00.png", age_s=30)
    _fichier(m / "Desktop" / "autre.png", age_s=1)
    s = Session(mac.outils())
    assert s.entendre("ouvre mon dernier PDF").statut == "fait"
    assert s.entendre("ouvre le dernier fichier téléchargé").statut == "fait"
    assert s.entendre("ouvre ma dernière capture d'écran").statut == "fait"
    assert [a for _, (a, *_) in mac.appels() if a.startswith("/")] == [
        str(recent.resolve()), str((m / "Downloads" / "notes.txt").resolve()), str(capture.resolve())]  # fmt: skip


def test_rien_trouve(mac: FauxMac) -> None:
    s = Session(mac.outils())
    assert s.entendre("ouvre mon dernier PDF").texte == "Je n'ai pas trouvé le dernier PDF."
    assert s.entendre("ouvre le dernier fichier téléchargé").statut == "info"


def test_spotlight_numerote_puis_ouvre(mac: FauxMac) -> None:
    m = mac.maison
    a = _fichier(m / "Documents" / "facture fnac.pdf")
    b = _fichier(m / "Downloads" / "facture edf.pdf")
    mac.regler(mdfind=[str(a), f"{m}/Library/Caches/facture.tmp", "/etc/facture", str(b)])
    s = Session(mac.outils())
    r = s.entendre("cherche facture")
    assert r.texte == "2 résultats : 1. facture fnac.pdf ; 2. facture edf.pdf"
    mac.vider()
    assert s.entendre("ouvre le 2").texte == "✓ facture edf.pdf ouvert"
    assert s.entendre("montre le premier dans le Finder").statut == "fait"
    assert mac.appels() == [("open", [str(b.resolve())]), ("open", ["-R", str(a.resolve())])]
    assert s.entendre("ouvre le 5").texte == "Il n'y a que 2 résultat(s)."
    assert s.entendre("ouvre le dernier").texte == "✓ facture edf.pdf ouvert"


def test_resultat_sans_recherche(mac: FauxMac) -> None:
    assert Session(mac.outils()).entendre("ouvre le 2").texte.startswith("Il n'y a pas de résultats")


def test_alias_vers_un_site_et_une_app(mac: FauxMac) -> None:
    from voix.nlu.alias import lire

    commandes = lire('[[alias]]\nnom = "mon journal"\ncible = "https://www.lemonde.fr"\n'
                     '[[alias]]\nnom = "mon éditeur"\ncible = "app:Notion"\n', mac.maison)  # fmt: skip
    o = mac.outils(commandes=commandes)
    o.catalogue.ajouter(commandes.alias)
    s = Session(o)
    assert s.entendre("ouvre mon journal").statut == "fait"
    assert s.entendre("ouvre mon éditeur").statut == "fait"
    assert mac.appels() == [("open", ["https://www.lemonde.fr"]), ("open", ["-b", "notion.id"])]


# --- modules -----------------------------------------------------------------------------------------------------


def test_module_absent_rien_n_est_lance(mac: FauxMac) -> None:
    r = Session(mac.outils(modules={})).entendre("ouvre le tableau de bord")
    assert r.texte == "Tableau de bord n'est pas installé." and mac.appels() == []


def test_module_decouverte_et_modes(mac: FauxMac, tmp_path: Path) -> None:
    from voix.actions.executeur import Executeur

    trouves = modules.decouvrir(Executeur([], [str(mac.bin)]))
    assert set(trouves) == {"tableau", "ambiance", "quotidien", "bouclier"}
    projet = tmp_path / "projets" / "ambiance"
    (projet / "bin").mkdir(parents=True)
    commande = projet / "bin" / "ambiance"
    commande.write_text("#!/bin/sh\n")
    (projet / "README.md").write_text("Dis `ambiance mode code` ou `ambiance mode sieste`.\n")
    avant = (projet / "README.md").stat().st_mtime
    assert modules.modes_ambiance(str(commande)) == {"code": "code", "sieste": "sieste"}
    assert (projet / "README.md").stat().st_mtime == avant
    assert modules.modes_ambiance(str(tmp_path / "rien")) == {}


def test_module_mode_verifie(mac: FauxMac) -> None:
    o = mac.outils(modules={"ambiance": ""}, modes_ambiance={"code": "code", "concentration": "focus"})
    s = Session(o)
    assert s.entendre("mode code").texte == "✓ Mode code"
    assert mac.appels() == [("ambiance", ["mode", "code"])]
    from voix.actions.modules import executer

    assert executer(o, "module.ambiance_mode", "rm -rf").statut == "erreur"
    assert executer(o, "module.ambiance_mode", "sieste").statut == "erreur"  # pas annoncé par le README


def test_module_lent_ou_en_erreur(mac: FauxMac) -> None:
    o = mac.outils(modules={"tableau": "", "quotidien": ""})
    o.reglages["modules"]["delai_s"] = 1.0
    mac.regler(lent=["tableau"])
    r = Session(o).entendre("ouvre le tableau de bord")
    assert r.statut == "erreur" and "ne répond pas" in r.texte
    mac.regler(lent=[], codes={"quotidien": 2}, sortie_module="pas de menu cette semaine")
    r = Session(o).entendre("menu de la semaine")
    assert r.statut == "erreur" and "pas de menu cette semaine" in r.texte
    mac.regler(codes={}, sortie_module="Lundi : pâtes\nMardi : soupe\n")
    assert Session(o).entendre("menu de la semaine").texte == "Lundi : pâtes Mardi : soupe"


# --- minuteurs ---------------------------------------------------------------------------------------------------


def test_minuteurs_sur_disque_et_echeance(mac: FauxMac) -> None:
    o = mac.outils()
    s = Session(o)
    s.entendre("minuteur 10 minutes")
    s.entendre("rappelle-moi dans 20 minutes de sortir le linge")
    assert s.entendre("il reste combien de temps").texte == "Il reste 10 minutes sur le minuteur."
    relus = Minuteurs(o.chemins.minuteurs)  # un redémarrage du moteur
    assert [m.message for m in relus.liste] == [None, "sortir le linge"]
    assert oct(o.chemins.minuteurs.stat().st_mode & 0o777) == "0o600"
    o.maintenant = lambda: datetime(2026, 10, 13, 9, 15)
    sorties = s.tic()
    assert [r.texte for r in sorties] == ["⏰ Minuteur terminé"]
    assert mac.pont.ordres == [("notification", {"titre": "Minuteur", "message": "10 minutes écoulées"})]
    assert s.entendre("annule le minuteur").texte == "✓ Rappel annulé"
    assert s.entendre("annule le minuteur").texte == "Il n'y a pas de minuteur en cours."


def test_notification_de_secours_sans_l_app(mac: FauxMac) -> None:
    mac.pont.refus.add("notification")
    o = mac.outils()
    m = Minuteurs(o.chemins.minuteurs).ajouter(60, 'appeler "Paul" ; rm -rf ~', datetime(2026, 1, 1))
    assert m is not None and notifier(o, m)
    prog, argv = mac.appels()[0]
    assert prog == "osascript" and argv[-2:] == ["Rappel", 'appeler "Paul" ; rm -rf ~']
    assert not any("Paul" in a for a in argv[:-2])  # le texte n'est jamais dans le script


def test_trop_de_minuteurs(mac: FauxMac) -> None:
    o = mac.outils()
    mins = Minuteurs(o.chemins.minuteurs)
    for _ in range(20):
        mins.ajouter(60, None, datetime(2026, 1, 1))
    assert mins.ajouter(60, None, datetime(2026, 1, 1)) is None
    assert mins.echus(datetime(2026, 1, 1) + timedelta(minutes=2))[0].ident == 1


def test_minuteurs_fichier_abime(mac: FauxMac) -> None:
    f = mac.maison / "m.json"
    f.write_text('[{"ident": 1, "fin": "pas une date"}, 3, {"ident": "x"}]')
    assert Minuteurs(f).liste == []
    f.write_text("{")
    assert Minuteurs(f).liste == []
