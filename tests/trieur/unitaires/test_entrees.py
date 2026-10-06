"""Les entrées surveillées, avec une horloge imitée : stabilité, fantômes iCloud, notes, Téléchargements, AirDrop."""

from __future__ import annotations

import json
import os
from pathlib import Path

from modules.trieur import config, pages
from modules.trieur.base import Base
from modules.trieur.entrees.surveillance import Entrees, lire_note
from tests.trieur.outils import FauxSysteme


class Horloge:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def avancer(self, s: float) -> None:
        self.t += s


def _monde(reglages, tmp_path):
    h = Horloge()
    base = Base(tmp_path / "t.db")
    faux = FauxSysteme()
    e = Entrees(reglages, base, faux, h)
    e.creer_les_dossiers()
    return e, h, faux, base


def _tours(e, h, n=3, pas=1.0):
    prets = []
    for _ in range(n):
        prets += e.regarder()
        h.avancer(pas)
    return prets


def _ecrire(chemin: Path, contenu: bytes, quand: float) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    os.utime(chemin, (quand, quand))
    return chemin


def test_stabilite_et_fichiers_ignores(reglages, tmp_path):
    e, h, _, base = _monde(reglages, tmp_path)
    boite = config.chemin(reglages, "boite")
    doc = _ecrire(boite / "facture.pdf", b"%PDF-1.4 a", h())
    for nom in (".DS_Store", "~$brouillon.docx", pages.COFFRE, "Mon coffre (Trieur).html", "x.pdf.crdownload"):
        _ecrire(boite / nom, b"x", h())
    (boite / "Raccourcis").mkdir()
    assert e.regarder() == [] and e.regarder() == []  # 1re et 2e mesure
    prets = e.regarder()  # 3e mesure identique : prêt
    assert [(p.chemin, p.source, p.note) for p in prets] == [(doc, "boite", None)]
    assert e.regarder() == []  # pris une fois
    doc.unlink()  # rangé par la chaîne (sinon il serait reproposé : la file le reconnaît alors)
    # Un fichier qui grossit encore n'est pas pris.
    gros = _ecrire(boite / "gros.pdf", b"1", h())
    e.regarder()
    gros.write_bytes(b"12")  # il change : on recommence à compter
    assert e.regarder() == [] and e.regarder() == []
    assert [p.chemin for p in e.regarder()] == [gros]
    base.fermer()


def test_fantome_icloud_demande_une_fois(reglages, tmp_path):
    e, h, faux, base = _monde(reglages, tmp_path)
    boite = config.chemin(reglages, "boite")
    _ecrire(boite / ".facture.pdf.icloud", b"bplist", h())
    _tours(e, h, 5)
    assert faux.telecharges == [boite / "facture.pdf"]
    h.avancer(200)
    e.regarder()
    assert len(faux.telecharges) == 2  # relancé après 2 minutes
    _ecrire(boite / "facture.pdf", b"%PDF vrai", h())
    assert [p.chemin.name for p in _tours(e, h, 3)] == ["facture.pdf"]
    base.fermer()


def test_note_de_l_iphone(reglages, tmp_path):
    e, h, _, base = _monde(reglages, tmp_path)
    boite = config.chemin(reglages, "boite")
    _ecrire(boite / "IMG_1.meta.json", json.dumps({"note": " garantie 3 ans "}).encode(), h())
    _ecrire(boite / "IMG_1.jpeg", b"jpeg", h())
    prets = _tours(e, h, 3)
    assert [(p.chemin.name, p.note, p.meta.name) for p in prets] == [
        ("IMG_1.jpeg", "garantie 3 ans", "IMG_1.meta.json")
    ]
    (boite / "IMG_1.jpeg").unlink()  # rangé par la chaîne
    (boite / "IMG_1.meta.json").unlink()
    # Une note seule depuis plus de 10 minutes devient un document comme un autre.
    _ecrire(boite / "perdue.meta.json", b'{"note": "x"}', h() - 700)
    assert [p.chemin.name for p in _tours(e, h, 3)] == ["perdue.meta.json"]
    assert lire_note(boite / "absent.json") is None
    _ecrire(boite / "vide.meta.json", b'{"note": ""}', h())
    assert lire_note(boite / "vide.meta.json") is None
    _ecrire(boite / "liste.meta.json", b"[1]", h())
    assert lire_note(boite / "liste.meta.json") is None
    base.fermer()


def test_telechargements(reglages, tmp_path):
    e, h, faux, base = _monde(reglages, tmp_path)
    dl = config.chemin(reglages, "telechargements")
    _ecrire(dl / "ancien.pdf", b"%PDF avant", h() - 3600)  # déjà là avant l'installation
    _ecrire(dl / "nouveau.pdf", b"%PDF apres", h() + 1)
    _ecrire(dl / "image.png", b"png", h() + 1)
    _ecrire(dl / "film.mp4.crdownload", b"...", h() + 1)
    assert _tours(e, h, 3) == []  # pas encore 2 minutes de calme
    h.avancer(130)
    assert [(p.chemin.name, p.source) for p in e.regarder()] == [("nouveau.pdf", "telechargements")]
    # Laissé une fois (pas assez sûr) : jamais repris tant qu'il ne change pas.
    el = base.ajouter(dl / "nouveau.pdf", "telechargements")
    base.mettre_a_jour(el, etat="ignore", taille=(dl / "nouveau.pdf").stat().st_size)
    # De même dans la boîte : un fichier en erreur n'est pas repris en boucle tant qu'il ne change pas.
    boite = config.chemin(reglages, "boite")
    casse = _ecrire(boite / "casse.pdf", b"%PDF", h())
    base.mettre_a_jour(base.ajouter(casse, "boite"), etat="erreur", taille=4)
    h.avancer(200)
    assert _tours(e, h, 3) == []
    # AirDrop : quarantaine « sharingd », n'importe quel format.
    faux.quarantaine = lambda chemin: "0083;65f0a1b2;sharingd;" if chemin.name == "photo.heic" else ""
    _ecrire(dl / "photo.heic", b"heic", h() + 1)
    _tours(e, h, 2)
    h.avancer(130)
    assert [(p.chemin.name, p.source) for p in e.regarder()] == [("photo.heic", "airdrop")]
    casse.write_bytes(b"%PDF-1.7 corrige")  # il a changé : il est repris
    assert [p.chemin.name for p in _tours(e, h, 3)] == ["casse.pdf"]
    base.fermer()


def test_date_d_installation_gardee(reglages, tmp_path):
    base = Base(tmp_path / "t.db")
    premier = Entrees(reglages, base, FauxSysteme(), lambda: 100.0)
    second = Entrees(reglages, base, FauxSysteme(), lambda: 999.0)
    assert premier.installe_le == second.installe_le == 100.0
    reglages["telechargements"]["actif"] = False
    assert [s for _, s in second.dossiers()] == ["boite", "boite"]  # « À trier » pas encore pris (D-58)
    second.creer_les_dossiers()
    assert [s for _, s in second.dossiers()] == ["boite", "boite", "a_trier"]
    base.fermer()
