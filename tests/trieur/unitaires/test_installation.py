"""Les notifications de chaque sorte, l'installation dans les cas difficiles, et doctor."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from modules.trieur import config, doctor, installer, raccourcis
from modules.trieur.base import Base
from modules.trieur.entrees import surveillance
from modules.trieur.notifications import Notifieur
from tests.trieur.outils import FauxSysteme


def _el(etat, **k):
    valeurs = {"id": 1, "nom": "a.pdf", "destination": "/C/Factures/2026/x.pdf", "erreur": None}
    valeurs.update(k)
    return SimpleNamespace(etat=etat, **valeurs)


def test_chaque_sorte_de_notification(reglages):
    reglages["mode_test"] = False
    envoyees = []
    h = [0.0]
    n = Notifieur(reglages, envoyer=lambda t, m: envoyees.append((t, m)), horloge=lambda: h[0])
    for etat in ("a_verifier", "photos", "doublon", "en_attente"):
        n.element(_el(etat))
    assert n.vider() == 0  # trop tôt : on attend la rafale
    h[0] = 10
    assert n.vider() == 3 and [t for t, _ in envoyees] == ["🗂 À vérifier", "📷 Photo rangée", "🗂 Déjà rangé"]
    n.element(_el("erreur", erreur="panne"))
    assert n.vider(forcer=True) == 1 and envoyees[3] == ("⚠️ Trieur", "a.pdf : panne") and n.vider() == 0
    n.echeance("Four", 7, "13/10/2026")
    assert envoyees[-1] == ("🛡 Garantie", "Four : fin dans 7 jours (13/10/2026)")


def test_installation_sans_icloud_et_finder_occupe(reglages, tmp_path, monkeypatch):
    base = Base(tmp_path / "t.db")
    monkeypatch.setattr(installer.finder, "installer", lambda *a: (_ for _ in ()).throw(FileExistsError("occupé")))
    faits = installer.installer(reglages, base, FauxSysteme(), allumer=False)
    textes = " ".join(t for _, t in faits)
    assert "iCloud Drive introuvable" in textes and "occupé" in textes and "pas d'iCloud" in textes
    assert base.lire_meta("installe_le") is not None
    allumes = []
    monkeypatch.setattr("core.config.activer_module", lambda nom, actif: allumes.append((nom, actif)))
    installer.installer(reglages, base, FauxSysteme(), allumer=True)
    assert allumes == [("trieur", True)]
    base.fermer()


def test_raccourcis_signes_puis_gardes(reglages, tmp_path, monkeypatch):
    boite = tmp_path / "boite"
    boite.mkdir()
    monkeypatch.setattr(raccourcis, "signer", lambda src, dst: (dst.write_bytes(b"signe"), (True, ""))[1])
    faits = installer._raccourcis(reglages, boite)
    assert [e for e, _ in faits] == ["✅", "✅"] and (boite / "Raccourcis" / "Envoie au Mac.shortcut").exists()
    assert all("déjà prêt" in t for _, t in installer._raccourcis(reglages, boite))


def test_doctor_branches(reglages, tmp_path, monkeypatch):
    base = Base(tmp_path / "t.db")
    for cle in ("classes", "a_trier", "photos"):
        Path(reglages["chemins"][cle]).mkdir(parents=True)
    (Path(reglages["chemins"]["icloud"]) / "BoiteMac").mkdir(parents=True)
    monkeypatch.setattr("modules.trieur.extraction.ocr.choisir", lambda *a: None)
    reglages["actif"] = True
    monkeypatch.setattr(doctor, "_superviseur", lambda: (None, None))
    lignes = dict((t, e) for e, t in doctor.verifier(reglages, base, mac=False))
    assert lignes["aucun OCR : photos et scans iront dans « À vérifier »"] == "⚠️"
    assert any("muette" in t for t in lignes)
    base.ecrire_meta("battement", str(time.time()))
    base.mettre_a_jour(base.ajouter(tmp_path / "x.pdf", "cli"), etat="erreur")
    base.mettre_a_jour(base.ajouter(tmp_path / "y.pdf", "cli"), etat="a_verifier")
    base.mettre_a_jour(base.ajouter(tmp_path / "z.pdf", "telechargements"), etat="ignore")
    textes = " ".join(t for _, t in doctor.verifier(reglages, base, mac=False))
    assert "surveillance active" in textes and "1 en erreur" in textes and "1 à vérifier" in textes
    assert "1 laissé à sa place" in textes and "trieur.py statut" in textes and "ignore" not in textes
    monkeypatch.setattr("modules.trieur.extraction.ocr.choisir", lambda *a: SimpleNamespace(nom="vision"))
    assert any("Apple Vision" in t for _, t in doctor.verifier(reglages, None, mac=False))
    base.fermer()


def test_doctor_dit_pourquoi_la_surveillance_est_muette(monkeypatch):
    """Juste après l'installation, le superviseur n'a pas encore lancé le Trieur : ⏳, pas ❌."""

    def cas(vivant, ligne=None):
        monkeypatch.setattr(doctor, "_superviseur", lambda: (vivant, ligne))
        return doctor._pourquoi_muette()

    def trieur(statut, relances=0, detail=""):
        return {"nom": "trieur", "statut": statut, "detail": detail, "pid": None, "relances": relances}

    assert cas(None)[0] == "❌" and "assistant.py etat" in cas(None)[1]
    assert cas(False) == ("❌", "surveillance allumée mais le superviseur de l'Assistant est arrêté : "
                                "python service.py installer")  # fmt: skip
    for ligne in (None, trieur("démarrage"), trieur("actif")):
        assert cas(True, ligne)[0] == "⏳"
    assert cas(True, trieur("en pause"))[0] == "⚠️"
    etat, texte = cas(True, trieur("relance", 2, "dans 50 s · ImportError"))
    assert etat == "❌" and "relance (dans 50 s · ImportError), 2 relance(s)" in texte and "journal" in texte
    assert cas(True, trieur("actif", 1))[0] == "❌"  # relancé après une chute, et toujours muet
    assert doctor.afficher([("✅", "a"), ("⏳", "b")]) == 0


def test_doctor_lit_le_superviseur(monkeypatch):
    import core.etat

    monkeypatch.setattr(core.etat, "lire", lambda cle, defaut=None: str(time.time()))
    monkeypatch.setattr(core.etat, "modules", lambda: [{"nom": "trieur", "statut": "actif", "relances": 0}])
    assert doctor._superviseur() == (True, {"nom": "trieur", "statut": "actif", "relances": 0})
    monkeypatch.setattr(core.etat, "lire", lambda cle, defaut=None: str(time.time() - 60))
    assert doctor._superviseur() == (False, None)
    monkeypatch.setattr(core.etat, "lire", lambda cle, defaut=None: 1 / 0)
    assert doctor._superviseur() == (None, None)


def test_les_anciens_a_trier_du_trieur(reglages, tmp_path, monkeypatch):
    """D-57 et D-59 : un ancien « À trier » né après l'installation du Trieur est retiré s'il est vide ; plein, il
    n'est pas touché ; né avant, il est à toi et n'est jamais regardé."""
    base = Base(tmp_path / "t.db")
    ancien, a_toi = Path(reglages["chemins"]["anciens_a_trier"][0]), tmp_path / "Documents" / "À trier"
    reglages["chemins"]["anciens_a_trier"].append(str(a_toi))
    a_toi.mkdir(parents=True)  # né avant l'arrivée du Trieur (voir ne_le plus bas)
    assert config.chemin(reglages, "a_trier").parent.name == "Documents" and ancien.parent.name == "Bureau"
    assert installer._anciens_a_trier(reglages, base) == []  # pas encore installé : rien n'est au Trieur
    base.ecrire_meta("installe_le", str(time.time() - 60))
    vrai_ne_le = surveillance.ne_le
    monkeypatch.setattr(surveillance, "ne_le", lambda p: 1_000.0 if p == a_toi else vrai_ne_le(p))
    monkeypatch.setattr("modules.trieur.extraction.ocr.choisir", lambda *a: None)
    monkeypatch.setattr(doctor, "_superviseur", lambda: (None, None))

    ancien.mkdir(parents=True)
    (ancien / "facture.pdf").write_bytes(b"%PDF mien")
    (ancien / ".DS_Store").write_bytes(b"finder")
    assert any("encore là" in t for _, t in doctor.verifier(reglages, base, mac=False))
    [(etat, texte)] = installer._anciens_a_trier(reglages, base)
    assert etat == "⚠️" and "1 élément(s)" in texte
    assert (ancien / "facture.pdf").read_bytes() == b"%PDF mien" and (ancien / ".DS_Store").exists()

    (ancien / "facture.pdf").unlink()  # toi, en le vidant
    [(etat, texte)] = installer._anciens_a_trier(reglages, base)
    assert etat == "✅" and not ancien.exists() and a_toi.is_dir()
    assert not any("encore là" in t for _, t in doctor.verifier(reglages, base, mac=False))
    base.fermer()


def test_l_ancien_a_trier_rempli_entre_deux_n_est_pas_touche(reglages, tmp_path, monkeypatch):
    base = Base(tmp_path / "t.db")
    base.ecrire_meta("installe_le", str(time.time() - 60))
    ancien = Path(reglages["chemins"]["anciens_a_trier"][0])
    ancien.mkdir(parents=True)
    vrai_rmdir = Path.rmdir

    def arrive_juste_avant(self):  # un fichier déposé entre le coup d'œil et le retrait
        (self / "arrivé.pdf").write_bytes(b"%PDF")
        vrai_rmdir(self)

    monkeypatch.setattr(Path, "rmdir", arrive_juste_avant)
    [(etat, _)] = installer._anciens_a_trier(reglages, base)
    assert etat == "⚠️" and (ancien / "arrivé.pdf").exists()
    base.fermer()
