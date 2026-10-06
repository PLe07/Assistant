"""La commande « trieur » dans un bac à sable (réglages, Mac et OCR imités)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.trieur import cli, config, doctor, traitement
from tests.trieur.outils import DEVIS_AMBIGU, FACTURE, FauxOCR, FauxSysteme, pdf


@pytest.fixture
def lancer(reglages):
    sorties: list[str] = []
    o = traitement.outils(reglages, systeme_=FauxSysteme(), moteur=FauxOCR(), ia=None)

    def _lancer(*argv: str) -> tuple[int, str]:
        sorties.clear()
        ctx = cli.Contexte(reglages, o, ecrire=sorties.append)
        ctx.fermer = lambda: None  # la base reste ouverte d'une commande à l'autre
        code = cli.main(list(argv), ctx)
        return code, "\n".join(sorties)

    yield _lancer
    o.base.fermer()


def test_aide(capsys):
    assert cli.main([]) == 0 and "trieur ajouter" in capsys.readouterr().out


def test_ajouter_journal_statut_coffre(lancer, tmp_path, reglages):
    f = pdf(tmp_path / "Bureau/facture.pdf", FACTURE)
    code, sortie = lancer("ajouter", str(f), "--note", "garantie 3 ans")
    assert code == 0 and "✅ n°1 facture.pdf → Classés/Factures/2026/2026-10-03_Fnac_Facture" in sortie
    assert lancer("ajouter", str(tmp_path / "absent.pdf"))[0] == 1
    code, sortie = lancer("journal")
    assert "n°1 facture.pdf" in sortie
    code, sortie = lancer("statut")
    assert "1 rangé(s)" in sortie and "1 garantie(s) en cours" in sortie and "éteinte" in sortie
    code, sortie = lancer("coffre")
    assert "fin le 03/10/2029" in sortie and "[note]" in sortie
    code, sortie = lancer("pages")
    assert (config.chemin(reglages, "boite") / "Mon coffre.html").exists()


def test_finder_notifie(lancer, tmp_path):
    f = pdf(tmp_path / "x.pdf", FACTURE)
    assert lancer("ajouter", "--source", "finder", str(f))[0] == 0


def test_garanties_a_la_main(lancer):
    code, sortie = lancer("garantie", "ajouter", "Vélo cargo", "--achat", "2026-09-01", "--mois", "60")
    assert code == 0 and "fin le 01/09/2031" in sortie
    code, sortie = lancer("garantie", "modifier", "1", "--fin", "2032-01-01")
    assert "n°2" in sortie
    code, sortie = lancer("garantie", "supprimer", "2")
    assert code == 0
    assert lancer("garantie", "supprimer", "2")[0] == 1
    assert lancer("coffre")[1] == "🛡 Aucune garantie pour l'instant."
    with pytest.raises(SystemExit):
        lancer("garantie", "ajouter", "X", "--achat", "hier")


def test_annuler_corriger(lancer, tmp_path):
    f = pdf(tmp_path / "devis.pdf", DEVIS_AMBIGU)
    code, sortie = lancer("ajouter", str(f))
    assert "🔎" in sortie
    code, sortie = lancer("corriger", "1", "--type", "devis", "--emetteur", "Plomberie Martin")
    assert code == 0 and "Devis/2026" in sortie and "retenu" in sortie
    code, sortie = lancer("annuler", "1")
    assert code == 0 and "remis" in sortie and f.exists()
    assert lancer("annuler", "1")[0] == 1 and lancer("corriger", "1", "--type", "devis")[0] == 1


def test_ranger_existant(lancer, tmp_path):
    vieux = tmp_path / "Vieux papiers"
    pdf(vieux / "a.pdf", FACTURE)
    pdf(vieux / "sous/b.pdf", DEVIS_AMBIGU)
    code, sortie = lancer("ranger-existant", str(vieux))
    assert "Plan pour 1 fichier" in sortie and "Factures/2026/2026-10-03_Fnac" in sortie and (vieux / "a.pdf").exists()
    code, sortie = lancer("ranger-existant", str(vieux), "--recursif")
    assert "Plan pour 2 fichier" in sortie and "à verifier" in sortie.replace("a verifier", "à verifier")
    code, sortie = lancer("ranger-existant", str(vieux), "--confirmer")
    assert "✅" in sortie and not (vieux / "a.pdf").exists()
    assert lancer("ranger-existant", str(tmp_path / "rien"))[0] == 1
    (tmp_path / "vide").mkdir()
    assert lancer("ranger-existant", str(tmp_path / "vide"))[1] == "Rien à ranger."


def test_arborescence(lancer, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert "Aucun" in lancer("arborescence")[1]
    for nom in ("Factures", "Impôts", "Vacances"):
        (tmp_path / "Documents" / nom).mkdir(parents=True)
    code, sortie = lancer("arborescence")
    assert (
        "~/Documents/Factures/{annee}" in sortie
        and "~/Documents/Vacances/{annee}" in sortie
        and "Rien n'est changé" in sortie
    )
    from modules.trieur import arborescence

    enregistre = {}
    monkeypatch.setattr("core.config.regler_module", lambda m, c, v: enregistre.update({(m, c): v}))
    code, sortie = lancer("arborescence", "--appliquer")
    assert (
        enregistre[("trieur", "arborescence")]["impots" if False else "avis_imposition"] == "~/Documents/Impôts/{annee}"
    )
    assert arborescence.proposer(tmp_path / "absent", {"arborescence": {}}) == {}


def test_doctor_et_installer(lancer, reglages, monkeypatch):
    code, sortie = lancer("doctor")
    assert "pymupdf" in sortie and "regles.toml" in sortie and "surveillance éteinte" in sortie
    monkeypatch.setattr("modules.trieur.raccourcis.shutil.which", lambda _: None)
    Path(reglages["chemins"]["icloud"]).mkdir(parents=True, exist_ok=True)
    code, sortie = lancer("installer", "--sans-allumer")
    assert code == 0 and "action rapide du Finder" in sortie and "non signé" in sortie
    assert (config.chemin(reglages, "services") / "Trier avec l'assistant.workflow").exists()
    lignes = doctor.verifier(reglages, None, mac=True)
    assert any("action rapide" in t and e == "✅" for e, t in lignes)
    assert doctor.afficher([("✅", "a"), ("❌", "b")]) == 1
