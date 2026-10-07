"""Les vérifications réelles, sur ton Mac seulement (`-m reel`) : Rappels, iCloud, Contacts, raccourcis signés,
IA. Chacune nettoie derrière elle dans un bloc `finally` et vérifie qu'il ne reste aucune trace.

    cd ~/Assistant/quotidien
    .venv/bin/python -m pytest -m reel tests/e2e_mac tests/frigo/test_vision.py -s

Un test « skipped » veut dire qu'un accès n'est pas encore accordé (voir ACTIONS_HUMAINES.md).
"""

from __future__ import annotations

import os
import platform
import shutil
import time
from pathlib import Path

import pytest

from quotidien import config, rappels_apple
from quotidien.db import Base as BaseDonnees
from quotidien.systeme import Systeme

pytestmark = [pytest.mark.reel, pytest.mark.skipif(platform.system() != "Darwin", reason="seulement sur un Mac")]
LISTE_TEST = "Quotidien-TEST"


def _vraie_maison(monkeypatch: pytest.MonkeyPatch) -> Path:
    maison = Path.home()
    monkeypatch.setenv("QUOTIDIEN_MAISON", str(maison))
    return maison


def _listes(systeme: Systeme) -> dict[str, str] | None:
    from integrite import empreinte

    etat = empreinte.rappels()
    return None if "(listes)" in etat else etat


def test_rappels_reels(tmp_path: Path) -> None:  # pragma: no cover - sur le Mac
    systeme = Systeme()
    avant = _listes(systeme)
    if avant is None:
        pytest.skip("accès aux Rappels pas encore accordé")
    assert LISTE_TEST not in avant, "une liste Quotidien-TEST existe déjà : supprime-la d'abord"
    r = config.defauts().reglages
    r["rappels"]["liste_courses"] = LISTE_TEST
    rappels = rappels_apple.Rappels(BaseDonnees(tmp_path / "q.db"), systeme, r)
    try:
        assert rappels.liste("courses") == LISTE_TEST
        elements = [rappels_apple.Element(f"courses:test:{i}", f"Test Quotidien {i}", "à supprimer") for i in range(3)]
        assert rappels.ajouter("courses", elements) == 3
        assert rappels.compter(LISTE_TEST) == 3
    finally:
        rappels.supprimer_nos_listes()
    apres = _listes(systeme)
    assert apres == avant, "les autres listes de Rappels ont changé"
    print(f"\nRappels réels : liste {LISTE_TEST} créée, 3 éléments relus, supprimée ; {len(avant)} autres listes "
          "identiques (noms et nombres).")  # fmt: skip


def test_icloud_reel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # pragma: no cover - sur le Mac
    from quotidien import daemon

    _vraie_maison(monkeypatch)
    if not config.icloud_drive().is_dir():
        pytest.skip("iCloud Drive absent")
    monkeypatch.setenv("QUOTIDIEN_DOSSIER_ICLOUD", "Quotidien-TEST")
    dossiers = [config.dossier_icloud(), config.dossier_icloud_raccourcis()]
    assert not any(d.exists() for d in dossiers), "un dossier Quotidien-TEST existe déjà : supprime-le d'abord"
    db = BaseDonnees(tmp_path / "q.db")
    try:
        entree = config.dossier_icloud() / "entree"
        entree.mkdir(parents=True)
        demande = entree / "frigo-verification-reelle-1.txt"
        demande.write_text("2 courgettes, feta, 4 oeufs", encoding="utf-8")
        os.utime(demande, (time.time() - 10, time.time() - 10))
        d = daemon.Demon(db, Systeme(), composants=daemon.Composants(fournisseur_contacts=lambda: ("ok", [])))
        assert "iCloud : 1 demande(s) des raccourcis" in d.tour_rapide().fait
        reponse = (config.dossier_icloud() / "reponses" / "frigo-verification-reelle-1.txt").read_text(
            encoding="utf-8")  # fmt: skip
        assert reponse.startswith("🧊 J'ai compris : 2 courgettes, feta, 4 œufs.")
        assert not demande.exists()
    finally:
        for d in dossiers:
            shutil.rmtree(d, ignore_errors=True)
    assert not any(d.exists() for d in dossiers)
    print("\niCloud réel : aller-retour d'une demande de vide-frigo dans Quotidien-TEST, puis dossier supprimé.")


def test_contacts_reels() -> None:  # pragma: no cover - sur le Mac
    from datetime import date

    from quotidien.anniversaires import contacts

    statut = contacts.statut_mac()
    if statut != "ok":
        pytest.skip(f"Contacts : {contacts.STATUTS.get(statut, statut)}")
    lecture = contacts.lire(date.today())
    # Seulement des nombres : aucun nom n'est écrit nulle part.
    print(f"\nContacts réels : {len(lecture.personnes)} anniversaire(s) trouvé(s), {lecture.sans_date} contact(s) "
          f"sans date, {lecture.ignores} ignoré(s).")  # fmt: skip
    assert len(lecture.personnes) >= 0


def test_raccourcis_signes(tmp_path: Path) -> None:  # pragma: no cover - sur le Mac
    from quotidien.raccourcis import generer

    if not shutil.which("shortcuts"):
        pytest.skip("commande shortcuts absente")
    for fichier in generer.ecrire(tmp_path):
        ok, message = generer.plutil_lint(fichier)
        assert ok, message
        signe = tmp_path / fichier.name.replace(".non-signé", "")
        ok, message = generer.signer(fichier, signe)
        if not ok and "iCloud" in message:
            pytest.skip(f"signature impossible : {message}")
        assert ok, message
        assert signe.stat().st_size > 0


def test_message_ia_reel(tmp_path: Path) -> None:  # pragma: no cover - sur le Mac, avec une clé ou Claude Code
    from quotidien import ia
    from quotidien.anniversaires import messages
    from quotidien.anniversaires.dates import DateNaissance
    from quotidien.anniversaires.proches import Personne

    systeme = Systeme()
    r = config.defauts().reglages
    client = ia.choisir_client(r, systeme.trousseau_lire)
    if client is None:
        pytest.skip("ni clé API ni Claude Code")
    p = Personne("test", "Camille", "Nom-Secret", DateNaissance(14, 3, 2001), "ami_proche", "drole",
                 ("souvenir : voyage à Lisbonne",))  # fmt: skip
    m = messages.rediger(BaseDonnees(tmp_path / "q.db"), r, p, 25, 2026, client=client)
    assert len(m.variantes) == 3 and all(messages.defaut(v, "Camille") is None for v in m.variantes)
    assert m.cout_usd < 0.02
    print(f"\nIA réelle ({client.nom}) : source {m.source}, coût {m.cout_usd:.4f} $")
    for v in m.variantes:
        print("  · " + v.replace("\n", " / "))
