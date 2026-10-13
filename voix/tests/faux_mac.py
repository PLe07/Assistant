"""Un faux Mac pour les tests d'actions (§9.3) : de faux exécutables (`open`, `osascript`, `networksetup`, `pmset`,
`shortcuts`, `mdfind`, `defaults`, `say` et les commandes des modules) qui **notent** chaque appel (programme +
arguments exacts) et simulent l'état du Mac (volume, sourdine, Wi-Fi, apparence) ; un faux pont vers l'app.

Rien n'est lancé pour de vrai : les faux programmes écrivent dans un fichier de trace et un fichier d'état JSON.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from outils import catalogue_reference as ref
from voix import config
from voix.actions.base import Outils
from voix.actions.executeur import MODULES, SYSTEME, Executeur
from voix.actions.pont import ReponsePont, valider

ETAT_INITIAL: dict[str, Any] = {
    "volume": 45, "muet": False, "wifi": True, "sombre": False, "mdfind": [], "batt": "", "codes": {},
    "lent": [], "sortie_module": "ok", "raccourcis": [],
}  # fmt: skip

FAUX = r"""#!{python}
import json, os, sys, time
nom = os.path.basename(sys.argv[0])
args = sys.argv[1:]
with open(os.environ["FAUX_TRACE"], "a", encoding="utf-8") as f:
    f.write(json.dumps({{"prog": nom, "argv": args}}) + "\n")
chemin_etat = os.environ["FAUX_ETAT"]
etat = json.load(open(chemin_etat, encoding="utf-8"))
if nom in etat["lent"]:
    time.sleep(5)
code = etat["codes"].get(nom, 0)
sortie = ""
if nom == "osascript":
    script = " ".join(a for a in args if not a.startswith("-"))
    if "get volume settings" in script:
        sortie = "%d,%s" % (etat["volume"], "true" if etat["muet"] else "false")
    elif "set volume output volume" in script:
        etat["volume"] = int(args[-1])
    elif "with output muted" in script and "without" not in script:
        etat["muet"] = True
    elif "without output muted" in script:
        etat["muet"] = False
elif nom == "networksetup":
    if args[:1] == ["-listallhardwareports"]:
        sortie = "Hardware Port: Ethernet\nDevice: en1\n\nHardware Port: Wi-Fi\nDevice: en0\nEthernet Address: x\n"
    elif args[:1] == ["-getairportpower"]:
        sortie = "Wi-Fi Power (%s): %s" % (args[1], "On" if etat["wifi"] else "Off")
    elif args[:1] == ["-setairportpower"]:
        etat["wifi"] = args[2] == "on"
elif nom == "defaults" and args[:3] == ["read", "-g", "AppleInterfaceStyle"]:
    if etat["sombre"]:
        sortie = "Dark"
    else:
        sys.stderr.write("The domain/default pair of (kCFPreferencesAnyApplication, AppleInterfaceStyle) "
                         "does not exist\n")
        code = 1
elif nom == "defaults":
    code = 1
elif nom == "mdfind":
    sortie = "\n".join(etat["mdfind"])
elif nom == "shortcuts" and args[:1] == ["list"]:
    sortie = "\n".join(etat["raccourcis"])
elif nom == "pmset" and args[:2] == ["-g", "batt"]:
    sortie = etat["batt"]
elif nom in ("tableau", "ambiance", "quotidien", "bouclier"):
    sortie = etat["sortie_module"]
json.dump(etat, open(chemin_etat, "w", encoding="utf-8"))
sys.stdout.write(sortie)
sys.exit(code)
"""


@dataclass
class FauxPont:
    """Le faux pont vers l'app : valide l'ordre comme le vrai, le note, et simule l'apparence."""

    etat: Path
    ordres: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    refus: set[str] = field(default_factory=set)
    donnees: dict[str, dict[str, Any]] = field(default_factory=dict)

    def demander(self, ordre: str, params: dict[str, Any]) -> ReponsePont:
        propres = valider(ordre, params)
        self.ordres.append((ordre, propres))
        if ordre in self.refus:
            return ReponsePont(False, {}, "refusé par macOS")
        if ordre == "apparence.regler":
            e = json.loads(self.etat.read_text())
            e["sombre"] = propres["sombre"]
            self.etat.write_text(json.dumps(e))
        return ReponsePont(True, self.donnees.get(ordre, {}))


@dataclass
class FauxMac:
    racine: Path
    maison: Path
    bin: Path
    trace: Path
    etat_fichier: Path
    pont: FauxPont

    def appels(self) -> list[tuple[str, list[str]]]:
        if not self.trace.exists():
            return []
        return [(e["prog"], e["argv"]) for e in map(json.loads, self.trace.read_text().splitlines())]

    def vider(self) -> None:
        self.trace.write_text("")
        self.pont.ordres.clear()

    @property
    def etat(self) -> dict[str, Any]:
        return json.loads(self.etat_fichier.read_text())

    def regler(self, **valeurs: Any) -> None:
        e = self.etat
        e.update(valeurs)
        self.etat_fichier.write_text(json.dumps(e))

    def outils(self, **en_plus: Any) -> Outils:
        executeur = Executeur([str(self.bin)], [str(self.bin)], delai_s=3.0,
                              env={"FAUX_TRACE": str(self.trace), "FAUX_ETAT": str(self.etat_fichier),
                                   "PATH": "/usr/bin:/bin"})  # fmt: skip
        chemins = config.Chemins(self.maison)
        reglages = config.Reglages({s: dict(v) for s, v in config.DEFAUTS.items()})
        o = Outils(executeur, chemins, reglages, ref.catalogue(maison=self.maison), ref.commandes(self.maison),
                   self.pont, maintenant=lambda: datetime(2026, 10, 13, 9, 0))  # fmt: skip
        for k, v in en_plus.items():
            setattr(o, k, v)
        return o


def fabriquer(racine: Path, modules: bool = True) -> FauxMac:
    maison = racine / "maison"
    for d in ("Downloads", "Desktop", "Documents", "Pictures", "Music", "Movies", "Documents/Cours",
              "Documents/Classés", "Library/Mobile Documents/com~apple~CloudDocs"):  # fmt: skip
        (maison / d).mkdir(parents=True, exist_ok=True)
    (maison / "Documents" / "Compta.numbers").write_text("compta")
    binaire = racine / "bin"
    binaire.mkdir(exist_ok=True)
    programmes = list(SYSTEME) + (list(MODULES) if modules else [])
    for nom in programmes:
        p = binaire / nom
        p.write_text(FAUX.format(python=sys.executable))
        os.chmod(p, 0o755)
    trace = racine / "trace.jsonl"
    trace.write_text("")
    etat = racine / "etat.json"
    etat.write_text(json.dumps(ETAT_INITIAL))
    return FauxMac(racine, maison, binaire, trace, etat, FauxPont(etat))
