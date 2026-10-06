"""D-59 : un fichier illisible n'est plus repris à chaque passage (235 lignes d'erreur sur ton Mac), un fichier iCloud
encore sans contenu est attendu au lieu d'être lu, et doctor dit d'où viennent les erreurs."""

from __future__ import annotations

import errno
import time
from pathlib import Path

from modules.trieur import base, config, daemon, doctor, rangement, traitement
from modules.trieur.entrees import surveillance
from tests.trieur.outils import FACTURE, FauxOCR, FauxSysteme, pdf


class Horloge:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _demon(reglages):
    h, faux = Horloge(1_000_000.0), FauxSysteme()
    o = traitement.outils(reglages, systeme_=faux, moteur=FauxOCR(), ia=None)
    d = daemon.Demon(reglages, outils=o, horloge=h)
    d.entrees.horloge = h
    return d, h, faux


def _tours(d, h, n):
    for _ in range(n):
        d.tour()
        h.t += 2


def test_un_fichier_illisible_n_est_pas_repris_en_boucle(reglages, monkeypatch):
    d, h, _ = _demon(reglages)
    d.demarrer()
    illisible = pdf(config.chemin(reglages, "boite") / "scan.pdf", FACTURE)
    vraie = rangement.empreinte

    def empreinte(chemin):
        if Path(chemin) == illisible:
            raise OSError(11, "Resource deadlock avoided")
        return vraie(chemin)

    monkeypatch.setattr(rangement, "empreinte", empreinte)
    _tours(d, h, 40)  # 80 s : avant D-59, une nouvelle ligne d'erreur toutes les 6 s environ
    erreurs = d.o.base.erreurs()
    assert len(erreurs) == 1 and erreurs[0].taille == illisible.stat().st_size
    assert "Resource deadlock avoided" in (erreurs[0].erreur or "") and illisible.exists()
    illisible.write_bytes(illisible.read_bytes() + b"\n")  # il change : il est repris (et lu, cette fois)
    monkeypatch.setattr(rangement, "empreinte", vraie)
    _tours(d, h, 4)
    assert d.o.base.compter().get("classe") == 1 and not illisible.exists()
    d.arreter()


def test_un_fichier_icloud_sans_contenu_est_demande_puis_attendu(reglages, monkeypatch):
    d, h, faux = _demon(reglages)
    d.demarrer()
    fichier = pdf(config.chemin(reglages, "boite") / "envoi.pdf", FACTURE)
    vide = {fichier}
    monkeypatch.setattr(surveillance, "sans_contenu", lambda st: bool(vide))
    _tours(d, h, 10)  # 20 s : demandé une fois, jamais lu
    assert faux.telecharges == [fichier] and d.o.base.compter() == {}
    h.t += surveillance.RELANCE_ICLOUD_S
    _tours(d, h, 1)
    assert faux.telecharges == [fichier, fichier]  # redemandé après 2 minutes
    vide.clear()  # iCloud l'a apporté
    _tours(d, h, 4)
    assert d.o.base.compter() == {"classe": 1}
    d.arreter()


def test_les_lignes_d_erreur_en_double_sont_retirees_au_demarrage(reglages):
    d, _, _ = _demon(reglages)
    b = d.o.base
    for _ in range(5):
        b.mettre_a_jour(b.ajouter(Path("/boite/scan.pdf"), "boite"), etat="erreur", erreur="OSError : x")
    garde = b.ajouter(Path("/boite/scan.pdf"), "boite")
    b.mettre_a_jour(garde, etat="erreur")
    b.noter_action(garde, "range", "/boite/scan.pdf", "/Classés/scan.pdf", "h")
    autre = b.ajouter(Path("/boite/autre.pdf"), "boite")
    b.mettre_a_jour(autre, etat="erreur")
    derniere = b.ajouter(Path("/boite/scan.pdf"), "boite")
    b.mettre_a_jour(derniere, etat="erreur", erreur="OSError : x")
    d.demarrer()
    assert sorted(el.id for el in b.erreurs()) == sorted([garde, autre, derniere])
    d.arreter()


def test_doctor_dit_d_ou_viennent_les_erreurs(reglages, monkeypatch):
    d, _, _ = _demon(reglages)
    b = d.o.base
    for i in range(3):
        b.mettre_a_jour(b.ajouter(Path(f"/iCloud/BoiteMac/f{i}.pdf"), "boite"), etat="erreur",
                        erreur="OSError : [Errno 11] Resource deadlock avoided")  # fmt: skip
    b.mettre_a_jour(b.ajouter(Path("/Téléchargements/x.pdf"), "telechargements"), etat="erreur", erreur="vide")
    monkeypatch.setattr("modules.trieur.extraction.ocr.choisir", lambda *a: None)
    monkeypatch.setattr(doctor, "_superviseur", lambda: (None, None))
    textes = [t for _, t in doctor.verifier(reglages, b, mac=False)]
    i = textes.index("4 en erreur : python trieur.py journal")
    assert textes[i + 1 : i + 3] == ["   3 dans /iCloud/BoiteMac · OSError : [Errno 11] Resource deadlock avoided",
                                     "   1 dans /Téléchargements · vide"]  # fmt: skip
    b.fermer()


def test_resource_deadlock_avoided_demande_a_icloud_puis_reessaie(reglages, monkeypatch):
    """D-60 : ta photo IMG_7892.jpg. La lire échouait (« Resource deadlock avoided ») : elle est demandée à iCloud,
    laissée sans notification, puis réessayée toutes les 2 minutes sur la même ligne, et rangée quand elle arrive."""
    d, h, faux = _demon(reglages)
    h.t = time.time()
    envoyees: list[str] = []
    d.notifieur.envoyer = lambda t, m: envoyees.append(t)  # type: ignore[method-assign]
    reglages["mode_test"] = False
    d.demarrer()
    envoi = pdf(Path(reglages["chemins"]["boite_raccourcis"]) / "envoi.pdf", FACTURE)
    vraie, pas_la = rangement.empreinte, {envoi}

    def empreinte(chemin):
        if Path(chemin) in pas_la:
            raise OSError(errno.EDEADLK, "Resource deadlock avoided")
        return vraie(chemin)

    monkeypatch.setattr(rangement, "empreinte", empreinte)
    _tours(d, h, 20)
    [el] = d.o.base.derniers(10)
    assert (el.etat, el.erreur) == ("ignore", base.ATTENTE_ICLOUD) and faux.telecharges == [envoi]
    assert d.o.base.attendus_d_icloud() == 1 and envoyees == [] and envoi.exists()
    monkeypatch.setattr(time, "time", lambda: h.t)
    h.t += base.RELANCE_ICLOUD_S
    _tours(d, h, 4)
    assert faux.telecharges == [envoi, envoi] and [e.id for e in d.o.base.derniers(10)] == [el.id]
    pas_la.clear()  # iCloud l'a apportée
    h.t += base.RELANCE_ICLOUD_S
    _tours(d, h, 8)
    [fini] = d.o.base.derniers(10)
    assert fini.id == el.id and fini.etat == "classe" and not envoi.exists() and envoyees == ["🗂 Rangé"]
    d.arreter()


def test_un_fichier_qui_revient_reprend_sa_ligne(reglages):
    d, _, _ = _demon(reglages)
    b = d.o.base
    a = b.ajouter(Path("/boite/a.pdf"), "boite")
    b.mettre_a_jour(a, etat="erreur", erreur="x", essais=3)
    assert b.ajouter(Path("/boite/a.pdf"), "boite", note="garantie") == a
    el = b.element(a)
    assert el is not None and (el.etat, el.essais, el.erreur, el.note) == ("en_attente", 0, None, "garantie")
    b.mettre_a_jour(a, etat="erreur")
    b.noter_action(a, "range", "/boite/a.pdf", "/Classés/a.pdf", "h")
    assert b.ajouter(Path("/boite/a.pdf"), "boite") != a  # une ligne qui a bougé un fichier garde son histoire
    b.fermer()


def test_doctor_montre_ce_qu_icloud_doit_apporter(reglages, monkeypatch):
    d, _, _ = _demon(reglages)
    b = d.o.base
    b.mettre_a_jour(b.ajouter(Path("/r/IMG.jpg"), "boite"), etat="ignore", erreur=base.ATTENTE_ICLOUD)
    monkeypatch.setattr("modules.trieur.extraction.ocr.choisir", lambda *a: None)
    monkeypatch.setattr(doctor, "_superviseur", lambda: (None, None))
    lignes = doctor.verifier(reglages, b, mac=False)
    assert ("⏳", "1 attendu(s) d'iCloud : téléchargement demandé, nouvel essai toutes les 2 minutes") in lignes
    assert ("✅", "documents : 1 laissé à sa place") in lignes
    b.fermer()
