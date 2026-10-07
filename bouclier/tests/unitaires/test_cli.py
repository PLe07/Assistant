"""La commande `bouclier` (vérifier, historique), sur un Mac imité."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from bouclier import cli, config
from bouclier.systeme import Resultat, Systeme


def _systeme(presse_papiers: str = "") -> Systeme:
    def executer(args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        if list(args)[:1] in (["pbpaste"], ["xclip"]):
            return Resultat(0, presse_papiers)
        return Resultat(1, "", "absent")

    return Systeme(executer, mac=False)


def test_verifier_un_texte(capsys: pytest.CaptureFixture[str]) -> None:
    sms = "Colissimo : votre colis est en attente. Payez 1,99 € : https://colissimo-suivi-frais.top/p"
    assert cli.main(["verifier", sms], _systeme()) == 0
    sortie = capsys.readouterr().out
    assert sortie.startswith("🔴 Arnaque très probable — faux message « Colissimo »") and "33700" in sortie
    assert cli.main(["historique"], _systeme()) == 0
    assert "Arnaque très probable" in capsys.readouterr().out


def test_verifier_un_fichier_et_le_presse_papiers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    eml = tmp_path / "m.eml"
    eml.write_bytes(b"From: \"Ameli\" <info@ameli-remboursement.top>\nSubject: Remboursement\n\n"
                    b"Vous avez droit a 250 euros, confirmez votre RIB : https://ameli-rembourse.top/r")  # fmt: skip
    assert cli.main(["verifier", str(eml)], _systeme()) == 0
    assert "faux message « Ameli" in capsys.readouterr().out
    assert cli.main(["verifier", "--presse-papiers"], _systeme("Salut, on mange ensemble demain ?")) == 0
    sortie = capsys.readouterr().out
    assert "⚪ Pas de signe d'arnaque détecté" in sortie and "autre canal" in sortie
    assert cli.main(["verifier", "--presse-papiers"], _systeme("")) == 1
    image = tmp_path / "capture.png"
    image.write_bytes(b"\x89PNG")
    assert cli.main(["verifier", str(image)], _systeme()) == 1
    assert "lecture des images indisponible" in capsys.readouterr().out


def test_sans_argument_et_aide(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert cli.main(["verifier"], _systeme()) == 1
    assert "Donne-moi le message" in capsys.readouterr().out
    assert cli.main([], _systeme()) == 0
    assert "verifier" in capsys.readouterr().out


def test_config_abimee_signalee(capsys: pytest.CaptureFixture[str]) -> None:
    c = config.chemins()
    c.support.mkdir(parents=True)
    c.config.write_text("[ia\n", encoding="utf-8")
    assert cli.main(["historique"], _systeme()) == 0
    sortie = capsys.readouterr()
    assert "ne se lit pas" in sortie.err and "Aucune vérification" in sortie.out  # l'alerte, sur la sortie d'erreur
    assert cli.main(["installation", "label"], _systeme()) == 0
    assert capsys.readouterr().out.strip().startswith("com.")  # `$(bouclier installation label)` reste propre
