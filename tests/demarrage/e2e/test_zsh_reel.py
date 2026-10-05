"""Le vrai zsh (présent ici comme sur le Mac) : chronométrage et zprof dans une copie isolée."""

import shutil
from pathlib import Path

from modules.demarrage.mesure import zsh
from modules.demarrage.systeme import Mac


class MacAvecMaison(Mac):
    def __init__(self, maison: Path):
        super().__init__()
        self.maison = str(maison)


def test_zprof_avec_le_vrai_zsh(tmp_path):
    assert shutil.which("zsh"), "zsh est nécessaire (il l'est sur macOS)"
    maison = tmp_path / "maison"
    maison.mkdir()
    zshrc = maison / ".zshrc"
    zshrc.write_text("charge_lente() { sleep 0.35 }\ncharge_lente\n", encoding="utf-8")
    mac = MacAvecMaison(maison)
    t = zsh.mesurer(mac, tmp_path / "temp", essais=3, seuil_ms=10_000)  # chronométrage seul
    assert t.mediane_ms is not None and t.mediane_ms > 0 and len(t.essais_ms) == 3 and t.causes == []
    causes = zsh.profiler(mac, tmp_path / "temp")
    assert causes and causes[0]["fonction"] == "charge_lente" and float(causes[0]["ms"]) >= 300
    assert zshrc.read_text(encoding="utf-8") == "charge_lente() { sleep 0.35 }\ncharge_lente\n"
    assert list((tmp_path / "temp").iterdir()) == []
