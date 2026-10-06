"""D-58 : un dossier « À trier » qui existait déjà avec tes fichiers n'est jamais surveillé, et ce que le Trieur y
avait vu est oublié sans que rien n'ait bougé."""

from __future__ import annotations

import os
from pathlib import Path

from modules.trieur import config, daemon, doctor, installer, traitement
from modules.trieur.entrees import surveillance
from tests.trieur.outils import FACTURE, FauxOCR, FauxSysteme, pdf


def _outils(reglages):
    return traitement.outils(reglages, systeme_=FauxSysteme(), moteur=FauxOCR(), ia=None)


def test_un_a_trier_qui_contient_deja_tes_fichiers_n_est_jamais_touche(reglages):
    a_toi = config.chemin(reglages, "a_trier")
    mien = pdf(a_toi / "facture de l'an dernier.pdf", FACTURE)  # une vraie facture : elle serait rangée
    os.utime(mien, (1_000_000, 1_000_000))
    avant = (mien.read_bytes(), mien.stat().st_mtime)
    o = _outils(reglages)
    etat, message = surveillance.prendre_a_trier(reglages, o.base)
    assert etat == "❌" and "contient tes fichiers" in message and o.base.lire_meta(surveillance.A_TRIER) is None
    d = daemon.Demon(reglages, outils=o)
    d.demarrer()
    for _ in range(6):
        d.tour()
    assert o.base.compter() == {} and (mien.read_bytes(), mien.stat().st_mtime) == avant
    assert sorted(p.name for p in a_toi.iterdir()) == ["facture de l'an dernier.pdf"]
    lignes = dict((t, e) for e, t in doctor.verifier(reglages, o.base, mac=False))
    assert any(e == "❌" and "contient tes fichiers" in t for t, e in lignes.items())
    d.arreter()


def test_cree_par_le_trieur_ou_vide_il_est_pris(reglages, tmp_path):
    o = _outils(reglages)
    dossier = config.chemin(reglages, "a_trier")
    assert surveillance.prendre_a_trier(reglages, o.base) == ("✅", f"dossier {dossier}")
    assert surveillance.a_trier_du_trieur(reglages, o.base) == dossier
    pdf(dossier / "x.pdf", FACTURE)  # le sien : il le garde, rempli ou non
    assert surveillance.prendre_a_trier(reglages, o.base)[0] == "✅"

    vide = tmp_path / "Vide"
    (vide / ".DS_Store").parent.mkdir()
    (vide / ".DS_Store").write_bytes(b"finder")
    reglages["chemins"]["a_trier"] = str(vide)
    assert surveillance.a_trier_du_trieur(reglages, o.base) is None  # un autre chemin : pas encore le sien
    assert surveillance.prendre_a_trier(reglages, o.base)[0] == "✅"
    assert surveillance.a_trier_du_trieur(reglages, o.base) == vide

    lien = tmp_path / "Lien"
    lien.symlink_to(tmp_path / "ailleurs", target_is_directory=True)
    reglages["chemins"]["a_trier"] = str(lien)
    assert surveillance.prendre_a_trier(reglages, o.base)[0] == "❌"
    o.base.fermer()


def test_ce_qui_a_ete_vu_chez_toi_est_oublie_sans_que_rien_n_ait_bouge(reglages, tmp_path):
    """Le cas de ton Mac : 109 fichiers de ton ~/Documents/À trier en « erreur », aucun déplacé."""
    o = _outils(reglages)
    a_toi = tmp_path / "Documents" / "À trier"
    a_toi.mkdir(parents=True)
    vus = []
    for i, etat in enumerate(("erreur", "erreur", "en_attente")):
        el = o.base.ajouter(a_toi / f"f{i}.pdf", "a_trier")
        o.base.mettre_a_jour(el, etat=etat, erreur="OSError : [Errno 11] Resource deadlock avoided")
        vus.append(el)
    bouge = o.base.ajouter(a_toi / "bouge.pdf", "a_trier")
    o.base.mettre_a_jour(bouge, etat="erreur")
    o.base.noter_action(bouge, "range", str(a_toi / "bouge.pdf"), "/Classés/bouge.pdf", "h")
    range_avant = o.base.ajouter(a_toi / "ancien.pdf", "a_trier")
    o.base.mettre_a_jour(range_avant, etat="classe")
    surveillance.prendre_a_trier(reglages, o.base)
    chez_nous = o.base.ajouter(config.chemin(reglages, "a_trier") / "n.pdf", "a_trier")
    o.base.mettre_a_jour(chez_nous, etat="erreur")

    # L'installateur montre la preuve (le journal des actions), sans rien oublier : l'ancien démon tourne encore.
    faits = installer._vus_hors_de_chez_nous(reglages, o.base)
    assert faits[0][0] == "✅" and faits[0][1].startswith(f"3 fichier(s) de ton dossier {a_toi} vus par erreur")
    assert "aucun déplacé ni modifié" in faits[0][1] and "Resource deadlock avoided" in faits[0][1]
    assert faits[1] == ("⚠️", "1 fichier(s) d'un dossier à toi ont une action au journal : python trieur.py journal")
    assert installer._vus_hors_de_chez_nous(reglages, o.base) == faits

    # Le nouveau démon les oublie au démarrage, avant son premier tour : l'élément « en attente » n'est jamais traité.
    d = daemon.Demon(reglages, outils=o)
    d.demarrer()
    assert all(o.base.element(i) is None for i in vus)
    assert all(o.base.element(i) is not None for i in (bouge, range_avant, chez_nous))
    assert traitement.traiter_la_file(o) == []
    assert installer._vus_hors_de_chez_nous(reglages, o.base) == [faits[1]]
    d.arreter()


def test_oublier_garde_ce_qui_a_une_action(reglages):
    o = _outils(reglages)
    a, b = o.base.ajouter(Path("/x/a.pdf"), "a_trier"), o.base.ajouter(Path("/x/b.pdf"), "a_trier")
    o.base.noter_action(b, "range", "/x/b.pdf", "/y/b.pdf", "h")
    assert o.base.oublier([a, b]) == 1 and o.base.element(a) is None and o.base.element(b) is not None
    o.base.fermer()
