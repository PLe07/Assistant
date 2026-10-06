"""L'interface vers le Mac (avec osascript, brctl et PyObjC imités) et les cas limites du déplacement sûr."""

from __future__ import annotations

import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

from modules.trieur import rangement, systeme
from modules.trieur.base import Base


class Lancement:
    def __init__(self, sortie="", code=0, erreur=None):
        self.appels: list[list[str]] = []
        self.sortie, self.code, self.erreur = sortie, code, erreur

    def __call__(self, cmd, **k):
        self.appels.append(cmd)
        if self.erreur:
            raise self.erreur
        return SimpleNamespace(returncode=self.code, stdout=self.sortie, stderr="refus")


def test_simple_hors_du_mac(tmp_path):
    s = systeme.Simple()
    assert not s.poser_tags(tmp_path, ["x"]) and s.coins(tmp_path) is None
    assert s.rappel_creer("L", "t", datetime(2027, 1, 1)) is None and not s.rappel_supprimer("L", "x")
    assert not s.telecharger_icloud(tmp_path)
    (tmp_path / "f.pdf").write_bytes(b"x")
    assert s.creer_alias(tmp_path / "f.pdf", tmp_path / "Garanties" / "a.pdf")
    assert (tmp_path / "Garanties" / "a.pdf").is_symlink()
    assert not s.creer_alias(tmp_path / "f.pdf", tmp_path / "Garanties" / "a.pdf")  # déjà là : refusé, pas écrasé
    assert isinstance(systeme.choisir(), systeme.Mac if sys.platform == "darwin" else systeme.Simple)


def test_rappels_par_osascript(monkeypatch):
    lancer = Lancement("x-apple-reminder://ABC")
    monkeypatch.setattr(systeme.subprocess, "run", lancer)
    mac = systeme.Mac()
    assert (
        mac.rappel_creer("Garanties", "Garantie : vélo", datetime(2027, 3, 5, 9, 0), "note") == "x-apple-reminder://ABC"
    )
    cmd = lancer.appels[0]
    assert cmd[:2] == ["osascript", "-e"] and cmd[3:] == [
        "Garanties",
        "Garantie : vélo",
        "note",
        "2027",
        "3",
        "5",
        "9",
        "0",
    ]
    lancer.sortie = "1"
    assert mac.rappel_supprimer("Garanties", "x-apple-reminder://ABC")
    lancer.code = 1
    assert mac.rappel_creer("Garanties", "t", datetime(2027, 1, 1)) is None
    monkeypatch.setattr(systeme.subprocess, "run", Lancement(erreur=OSError("absent")))
    assert not mac.rappel_supprimer("Garanties", "x")


def test_icloud_par_brctl(monkeypatch, tmp_path):
    mac = systeme.Mac()
    monkeypatch.setattr(systeme.shutil, "which", lambda _: None)
    assert not mac.telecharger_icloud(tmp_path / ".a.pdf.icloud")
    monkeypatch.setattr(systeme.shutil, "which", lambda _: "/usr/bin/brctl")
    lancer = Lancement()
    monkeypatch.setattr(systeme.subprocess, "run", lancer)
    assert mac.telecharger_icloud(tmp_path / "a.pdf") and lancer.appels[0][:2] == ["brctl", "download"]
    monkeypatch.setattr(systeme.subprocess, "run", Lancement(erreur=systeme.subprocess.TimeoutExpired("brctl", 60)))
    assert not mac.telecharger_icloud(tmp_path / "a.pdf")


def test_natif_imite(monkeypatch, tmp_path):
    faux = SimpleNamespace(poser_tags=lambda c, t: True, creer_alias=lambda c, a: False,
                           coins_du_document=lambda i: [(0, 0), (1, 0), (1, 1), (0, 1)])  # fmt: skip
    monkeypatch.setitem(sys.modules, "modules.trieur.natif", faux)
    import modules.trieur as paquet

    monkeypatch.setattr(paquet, "natif", faux, raising=False)
    mac = systeme.Mac()
    assert mac.poser_tags(tmp_path, ["Facture"]) and mac.coins(tmp_path) == [(0, 0), (1, 0), (1, 1), (0, 1)]
    (tmp_path / "f.pdf").write_bytes(b"x")
    assert mac.creer_alias(tmp_path / "f.pdf", tmp_path / "al" / "f.pdf")  # repli : lien symbolique
    faux.poser_tags = lambda c, t: (_ for _ in ()).throw(RuntimeError("pas de Foundation"))
    faux.coins_du_document = lambda i: (_ for _ in ()).throw(RuntimeError("pas de Vision"))
    faux.creer_alias = lambda c, a: (_ for _ in ()).throw(RuntimeError("pas de Foundation"))
    assert not mac.poser_tags(tmp_path, ["x"]) and mac.coins(tmp_path) is None
    assert mac.creer_alias(tmp_path / "f.pdf", tmp_path / "al" / "g.pdf")


def test_deplacement_cas_limites(tmp_path, monkeypatch):
    base = Base(tmp_path / "t.db")
    source = tmp_path / "a.pdf"
    source.write_bytes(b"contenu")
    with pytest.raises(rangement.DeplacementImpossible, match="changé"):
        rangement.deplacer(source, tmp_path / "d", "a.pdf", base, 1, attendue="0" * 64)
    cible = rangement.deplacer(source, tmp_path / "d", "a.pdf", base, 1, garder_source=True)
    assert source.exists() and cible.read_bytes() == b"contenu"
    # Le nom est pris entre le choix et la création : le suivant est pris, rien n'est écrasé.
    candidats = iter([tmp_path / "d" / "a.pdf", tmp_path / "d" / "a-7.pdf"])
    monkeypatch.setattr(rangement, "libre", lambda d, n: next(candidats))
    deux = rangement.copier_sans_ecraser(source, tmp_path / "d", "a.pdf")
    assert deux.name == "a-7.pdf" and cible.read_bytes() == b"contenu"
    monkeypatch.undo()
    # Une copie qui échoue en route est retirée.
    monkeypatch.setattr(rangement.shutil, "copyfileobj", lambda *a: (_ for _ in ()).throw(OSError("disque plein")))
    with pytest.raises(OSError):
        rangement.copier_sans_ecraser(source, tmp_path / "d", "b.pdf")
    assert not (tmp_path / "d" / "b.pdf").exists()
    monkeypatch.undo()
    # Ramener : copie de retour incorrecte → rien ne bouge.
    vraie = rangement.empreinte
    monkeypatch.setattr(rangement, "empreinte", lambda c: "x" if c.parent == tmp_path / "retour" else vraie(c))
    with pytest.raises(rangement.DeplacementImpossible, match="retour"):
        rangement.ramener(cible, tmp_path / "retour" / "a.pdf", base, 1)
    assert cible.exists()
    base.fermer()


def test_applescript_sans_mot_reserve():
    """Sur le vrai Mac, « set note to … » échouait : « note » est réservé en AppleScript. Toute variable des scripts
    commence donc par « v »."""
    import re

    for script in (systeme._RAPPEL_CREER, systeme._RAPPEL_SUPPRIMER):
        variables = re.findall(r"\bset (\w+) to\b", script) + re.findall(r"\brepeat with (\w+) in\b", script)
        assert variables and all(v.startswith("v") and v[1].isupper() for v in variables), variables
