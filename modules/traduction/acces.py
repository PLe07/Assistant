"""Ce qui parle à macOS (macOS uniquement). Les tests remplacent tout ceci par des imitations.

- Clavier : remarque chaque « . » tapé (écoute seule, rien n'est enregistré : autorisation « Surveillance de
  l'entrée »). Les champs de mot de passe sont invisibles : macOS les cache de lui-même.
- Mac : lit la phrase dans le champ où tu écris et la remplace (autorisation « Accessibilité »).
"""

import subprocess
from dataclasses import dataclass


@dataclass
class Lu:
    texte: str
    curseur: int  # position du curseur, en unités macOS (UTF-16)
    secret: bool = False  # champ de mot de passe : on n'y touche jamais


def _ax():
    import ApplicationServices

    return ApplicationServices


def _type_plage(AS):
    return getattr(AS, "kAXValueTypeCFRange", None) or AS.kAXValueCFRangeType


def _plage(AS, debut: int, longueur: int):
    try:
        from CoreFoundation import CFRangeMake

        valeur = CFRangeMake(debut, longueur)
    except ImportError:
        valeur = (debut, longueur)
    return AS.AXValueCreate(_type_plage(AS), valeur)


class Mac:
    # --- autorisations ------------------------------------------------------------------------------

    def saisie_autorisee(self) -> bool:
        import Quartz

        return bool(Quartz.CGPreflightListenEventAccess())

    def demander_saisie(self) -> None:
        import Quartz

        Quartz.CGRequestListenEventAccess()

    def accessibilite_autorisee(self, demander: bool = False) -> bool:
        AS = _ax()
        if demander:  # fait apparaître la demande de macOS (une fois)
            from Foundation import NSDictionary

            options = NSDictionary.dictionaryWithDictionary_({AS.kAXTrustedCheckOptionPrompt: True})
            return bool(AS.AXIsProcessTrustedWithOptions(options))
        return bool(AS.AXIsProcessTrusted())

    # --- lire et remplacer --------------------------------------------------------------------------

    def _attribut(self, element, nom: str):
        erreur, valeur = _ax().AXUIElementCopyAttributeValue(element, nom, None)
        return valeur if erreur == 0 else None

    def appli_devant(self) -> dict | None:
        """{appli, bundle, titre, pid} de l'appli où tu écris (le titre de sa fenêtre sert aux exclusions)."""
        from AppKit import NSRunningApplication

        AS = _ax()
        focus = self._attribut(AS.AXUIElementCreateSystemWide(), "AXFocusedApplication")
        if focus is None:
            return None
        erreur, pid = AS.AXUIElementGetPid(focus, None)
        appli = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if erreur == 0 else None
        if appli is None:
            return None
        fenetre = self._attribut(focus, "AXFocusedWindow")
        titre = self._attribut(fenetre, "AXTitle") if fenetre is not None else None
        return {"appli": str(appli.localizedName() or ""), "bundle": str(appli.bundleIdentifier() or ""),
                "titre": str(titre or ""), "pid": pid}

    def champ(self):
        """Le champ de texte où tu écris, ou None."""
        return self._attribut(_ax().AXUIElementCreateSystemWide(), "AXFocusedUIElement")

    def lire(self, champ) -> Lu | None:
        if "Secure" in str(self._attribut(champ, "AXSubrole") or "") + str(self._attribut(champ, "AXRole") or ""):
            return Lu("", 0, secret=True)
        texte, plage = self._attribut(champ, "AXValue"), self._attribut(champ, "AXSelectedTextRange")
        if texte is None or plage is None:
            return None
        ok, r = _ax().AXValueGetValue(plage, _type_plage(_ax()), None)
        if not ok or r.length:  # du texte sélectionné : ce n'est pas une phrase qui vient de finir
            return None
        return Lu(str(texte), int(r.location))

    def remplacer(self, champ, debut: int, longueur: int, nouveau: str, curseur_apres: int) -> bool:
        """Remplace [debut, debut + longueur) par « nouveau », puis remet le curseur. False si l'appli refuse."""
        from modules.traduction.phrase import position

        AS = _ax()
        if AS.AXUIElementSetAttributeValue(champ, "AXSelectedTextRange", _plage(AS, debut, longueur)) != 0:
            return False
        if AS.AXUIElementSetAttributeValue(champ, "AXSelectedText", nouveau) != 0:
            return False
        apres = self._attribut(champ, "AXValue")  # certaines applis disent « oui » sans rien changer
        if apres is None or not str(apres)[position(str(apres), debut):].startswith(nouveau):
            AS.AXUIElementSetAttributeValue(champ, "AXSelectedTextRange", _plage(AS, debut + longueur, 0))
            return False
        AS.AXUIElementSetAttributeValue(champ, "AXSelectedTextRange", _plage(AS, curseur_apres, 0))
        return True

    def copier(self, texte: str) -> None:
        subprocess.run(["pbcopy"], input=texte, text=True, check=False, timeout=5)


class Clavier:
    """Écoute seule du clavier : appelle quand_point() à chaque « . » tapé (jamais pour un raccourci Cmd/Ctrl).
    Ne garde aucune touche : seul le fait qu'un point vient d'être tapé est transmis."""

    def __init__(self, quand_point):
        self.quand_point = quand_point
        self.tap = None

    def _rappel(self, proxy, type_, event, refcon):
        import Quartz

        if type_ == Quartz.kCGEventKeyDown:
            drapeaux = Quartz.CGEventGetFlags(event)
            if not drapeaux & (Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskControl):
                _, caractere = Quartz.CGEventKeyboardGetUnicodeString(event, 4, None, None)
                if caractere == ".":
                    self.quand_point()
        elif type_ in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            if self.tap is not None:  # macOS coupe une écoute jugée trop lente : on la relance
                Quartz.CGEventTapEnable(self.tap, True)
        return event

    def tourner(self, arret) -> bool:
        """Écoute jusqu'à l'arrêt. False si macOS refuse l'écoute (autorisation « Surveillance de l'entrée »)."""
        import Quartz

        self.tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                           Quartz.kCGEventTapOptionListenOnly,
                                           Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown), self._rappel, None)
        if self.tap is None:
            return False
        source = Quartz.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self.tap, True)
        try:
            while not arret.is_set():
                Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.5, False)
        finally:
            Quartz.CGEventTapEnable(self.tap, False)
            Quartz.CFRunLoopRemoveSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
        return True
