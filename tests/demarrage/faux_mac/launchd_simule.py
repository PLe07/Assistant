"""Un launchd et un System Events qui se souviennent : bootout, disable, enable, bootstrap et les éléments
d'ouverture changent vraiment leur état, comme sur le Mac. Pour juger desactiver et restaurer."""

from __future__ import annotations

import plistlib
import re

from modules.demarrage.systeme import Resultat
from tests.demarrage.faux_mac.systeme_faux import FauxMac


class LaunchdSimule:
    def __init__(self, mac: FauxMac, charges: dict[str, str | None] | None = None, desactives: set[str] | None = None,
                 ouverture: dict[str, str] | None = None, automatisation: bool = True):  # fmt: skip
        self.mac = mac
        self.charges = dict(charges or {})  # label → plist (None : sans fichier connu)
        self.desactives = set(desactives or set())
        self.ouverture = dict(ouverture or {})  # nom → chemin de l'app
        self.automatisation = automatisation
        self.domaine = f"gui/{mac.uid}"
        # Les réponses fixes du faux Mac à « launchctl print gui/UID/label » masqueraient l'état : on les reprend.
        fixes = [c for c in mac.exactes if c[:2] == ("launchctl", "print") and len(c) == 3]
        self.details = {c[2]: mac.exactes.pop(c) for c in fixes if c[2].startswith(self.domaine + "/")}
        mac.repondre(["launchctl", "print-disabled", self.domaine], lambda c, m: Resultat(0, self._desactives()))
        mac.repondre_debut(["launchctl", "print"], self._print)
        for verbe in ("bootout", "disable", "enable", "bootstrap"):
            mac.repondre_debut(["launchctl", verbe], getattr(self, f"_{verbe}"))
        mac.repondre_debut(["osascript"], self._osascript)

    def _desactives(self) -> str:
        lignes = "".join(f'\t"{label}" => disabled\n' for label in sorted(self.desactives))
        return f"disabled services = {{\n{lignes}}}\n"

    def _label(self, cible: str) -> str:
        return cible.removeprefix(self.domaine + "/")

    def _print(self, c: list[str], m: FauxMac) -> Resultat:
        label = self._label(c[2]) if len(c) > 2 else ""
        if label in self.charges:
            fixe = self.details.get(c[2])
            if fixe is not None:
                return fixe(c, m) if callable(fixe) else fixe
            return Resultat(0, f"{c[2]} = {{\n\tpath = {self.charges[label]}\n\tstate = running\n}}\n")
        return Resultat(113, "", f'Could not find service "{label}" in domain for user gui: {self.mac.uid}\n')

    def _bootout(self, c: list[str], m: FauxMac) -> Resultat:
        label = self._label(c[2])
        if self.charges.pop(label, "absent") == "absent":
            return Resultat(3, "", "Boot-out failed: 3: No such process\n")
        return Resultat(0, "")

    def _disable(self, c: list[str], m: FauxMac) -> Resultat:
        self.desactives.add(self._label(c[2]))
        return Resultat(0, "")

    def _enable(self, c: list[str], m: FauxMac) -> Resultat:
        self.desactives.discard(self._label(c[2]))
        return Resultat(0, "")

    def _bootstrap(self, c: list[str], m: FauxMac) -> Resultat:
        chemin = c[3]
        try:
            label = plistlib.loads(m.chemin(chemin).read_bytes())["Label"]
        except Exception:
            return Resultat(5, "", "Bootstrap failed: 5: Input/output error\n")
        if label in self.desactives:
            return Resultat(5, "", "Bootstrap failed: 5: Input/output error\n")  # launchd refuse un service désactivé
        self.charges[label] = chemin
        return Resultat(0, "")

    def _osascript(self, c: list[str], m: FauxMac) -> Resultat:
        script = " ".join(c[1:])
        if not self.automatisation:
            return Resultat(1, "", "execution error: Not authorized to send Apple events to System Events. (-1743)\n")
        retire = re.search(r'delete login item "((?:[^"\\]|\\.)*)"', script)
        if retire:
            nom = retire.group(1).replace('\\"', '"').replace("\\\\", "\\")
            if self.ouverture.pop(nom, None) is None:
                return Resultat(
                    1, "", f'execution error: System Events got an error: Can\'t get login item "{nom}". (-1728)\n'
                )
            return Resultat(0, "")
        ajoute = re.search(r'make login item at end with properties \{path:"((?:[^"\\]|\\.)*)"', script)
        if ajoute:
            chemin = ajoute.group(1)
            self.ouverture[chemin.rsplit("/", 1)[-1].removesuffix(".app")] = chemin
            return Resultat(0, "login item " + chemin)
        return Resultat(0, "".join(f"{n}\t{p}\tfalse\n" for n, p in self.ouverture.items()))
