"""Les fixtures de format sont anonymes par construction, et les plists pièges sont bien piégées."""

import plistlib
import re

import pytest

from tests.demarrage.conftest import FORMATS

TEXTES = sorted(p for p in FORMATS.rglob("*") if p.is_file() and p.suffix == ".txt")


def test_il_y_a_des_fixtures_pour_chaque_commande():
    noms = {p.stem.split("_")[0] for p in TEXTES}
    assert {"launchctl", "ps", "top", "pmset", "codesign", "mdls", "sfltool", "osascript", "systemextensionsctl",
            "crontab", "sysctl", "last", "log"} <= noms  # fmt: skip


@pytest.mark.parametrize("chemin", TEXTES, ids=lambda p: p.name)
def test_anonyme(chemin):
    texte = chemin.read_text(encoding="utf-8")
    assert texte.strip()
    assert set(re.findall(r"/Users/([^/\s]+)", texte)) <= {"utilisateur"}
    assert all(e.endswith("exemple.fr") for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texte))
    uuids = re.findall(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", texte)
    assert all(u.startswith("00000000-0000-0000-0000-") for u in uuids)


def test_plists_pieges():
    dossier = FORMATS / "plists"
    assert plistlib.loads((dossier / "com.exemple.binaire.plist").read_bytes())["KeepAlive"] is True
    assert (dossier / "com.exemple.binaire.plist").read_bytes().startswith(b"bplist00")
    with pytest.raises(Exception):  # noqa: B017 (selon la version : InvalidFileException ou ExpatError)
        plistlib.loads((dossier / "com.exemple.casse.plist").read_bytes())
    assert plistlib.loads((dossier / "com.exemple.vide.plist").read_bytes())["ProgramArguments"] == []
    assert isinstance(plistlib.loads((dossier / "com.exemple.keepalive.plist").read_bytes())["KeepAlive"], dict)
