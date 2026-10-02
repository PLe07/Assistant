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


# Les réponses de macOS quand il refuse (codes « AXError »), dites simplement.
AX_ERREURS = {-25200: "échec", -25201: "demande refusée", -25202: "élément disparu", -25204: "l'appli ne répond pas",
              -25205: "pas proposé par cette appli", -25211: "accessibilité non autorisée", -25212: "rien à lire"}


CHERCHE_PROFONDEUR, CHERCHE_MAX = 5, 200  # recherche du texte dans un cadre : bornée, pour rester rapide
ARBRE_MAX = 40  # lignes du diagnostic


def code(erreur: int) -> str:
    return f"erreur {erreur} : {AX_ERREURS.get(erreur, 'inconnue')}"


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

    # --- l'appli et le champ où tu écris ------------------------------------------------------------

    def _lire(self, element, nom: str) -> tuple[int, object]:
        """(réponse de macOS, valeur) : 0 = réussi, sinon un code d'erreur (voir code())."""
        erreur, valeur = _ax().AXUIElementCopyAttributeValue(element, nom, None)
        return int(erreur), (valeur if erreur == 0 else None)

    def _attribut(self, element, nom: str):
        return self._lire(element, nom)[1]

    def _pid_focus(self) -> int | None:
        """L'appli qui a le clavier, d'après l'accessibilité (la réponse la plus sûre, quand macOS la donne)."""
        AS = _ax()
        focus = self._attribut(AS.AXUIElementCreateSystemWide(), "AXFocusedApplication")
        if focus is None:
            return None
        erreur, pid = AS.AXUIElementGetPid(focus, None)
        return int(pid) if erreur == 0 and pid else None

    def _fenetre_devant(self) -> dict | None:
        try:
            from modules.yeux.capture import fenetre_au_premier_plan

            return fenetre_au_premier_plan()
        except Exception:
            return None

    def _pids_devant(self) -> list[tuple[str, int]]:
        """Les autres façons de demander à macOS quelle appli est devant : [(d'où vient l'info, pid)]."""
        trouves = []
        try:
            from AppKit import NSWorkspace

            appli = NSWorkspace.sharedWorkspace().frontmostApplication()
            if appli is not None:
                trouves.append(("applis ouvertes", int(appli.processIdentifier())))
        except Exception:
            pass
        f = self._fenetre_devant()
        if f and f.get("pid") and int(f["pid"]) not in [pid for _, pid in trouves]:
            trouves.append(("fenêtre la plus en avant", int(f["pid"])))
        return trouves

    def _pid_devant(self) -> int | None:
        pid = self._pid_focus()
        if pid is not None:
            return pid
        AS = _ax()
        for _, candidat in self._pids_devant():  # l'appli confirme qu'elle est devant : jamais une appli en arrière-plan
            if self._attribut(AS.AXUIElementCreateApplication(candidat), "AXFrontmost"):
                return candidat
        return None

    def appli_devant(self) -> dict | None:
        """{appli, bundle, titre, pid} de l'appli où tu écris (le titre de sa fenêtre sert aux exclusions)."""
        from AppKit import NSRunningApplication

        pid = self._pid_devant()
        appli = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if pid else None
        if appli is None:
            return None
        fenetre = self._attribut(_ax().AXUIElementCreateApplication(pid), "AXFocusedWindow")
        titre = self._attribut(fenetre, "AXTitle") if fenetre is not None else None
        if not titre:  # en secours, le titre que voit l'écran (pour ne jamais rater un site exclu)
            f = self._fenetre_devant()
            titre = f.get("titre") if f and int(f.get("pid") or 0) == pid else ""
        return {"appli": str(appli.localizedName() or ""), "bundle": str(appli.bundleIdentifier() or ""),
                "titre": str(titre or ""), "pid": pid}

    def _focus(self, pid: int | None):
        """L'élément qui a le clavier : demandé au système, puis à l'appli elle-même."""
        AS = _ax()
        element = self._attribut(AS.AXUIElementCreateSystemWide(), "AXFocusedUIElement")
        if element is None and pid:
            element = self._attribut(AS.AXUIElementCreateApplication(pid), "AXFocusedUIElement")
        return element

    def _role(self, element) -> str:
        return f"{self._attribut(element, 'AXRole') or '?'}/{self._attribut(element, 'AXSubrole') or '-'}"

    def _enfants(self, element) -> list:
        return list(self._attribut(element, "AXChildren") or [])

    def _lisible(self, element) -> bool:
        """Un vrai champ de texte : macOS donne son texte et la position du curseur."""
        return self._lire(element, "AXSelectedTextRange")[0] == 0 and isinstance(self._attribut(element, "AXValue"), str)

    def _texte_dedans(self, cadre):
        """Le texte où tu écris, à l'intérieur d'un cadre : celui qui a le focus, sinon le seul qui existe.
        Plusieurs sans focus : aucun (on ne devine jamais lequel modifier)."""
        file, vus, trouves = [(cadre, 0)], 0, []
        while file and vus < CHERCHE_MAX:
            element, niveau = file.pop(0)
            vus += 1
            if niveau and self._lisible(element):
                if self._attribut(element, "AXFocused"):
                    return element
                trouves.append(element)
                continue
            if niveau < CHERCHE_PROFONDEUR:
                file.extend((enfant, niveau + 1) for enfant in self._enfants(element))
        return trouves[0] if len(trouves) == 1 else None

    def champ(self, pid: int | None = None):
        """Le champ de texte où tu écris, ou None. Certaines applis (Pages…) donnent le cadre autour du texte :
        le texte est alors cherché dedans."""
        element = self._focus(pid)
        if element is None or self._lisible(element):
            return element
        return self._texte_dedans(element) or element

    def _arbre(self, cadre) -> list[str]:
        """Ce que contient un élément, en abrégé (les rôles, jamais le texte) : pour le diagnostic."""
        lignes = []

        def visiter(element, niveau):
            for enfant in self._enfants(element):
                if len(lignes) >= ARBRE_MAX:
                    return
                marques = ["texte"] if isinstance(self._attribut(enfant, "AXValue"), str) else []
                marques += ["curseur"] if self._lire(enfant, "AXSelectedTextRange")[0] == 0 else []
                marques += ["focus"] if self._attribut(enfant, "AXFocused") else []
                lignes.append("  " * niveau + f"└ {self._role(enfant)}" + (f" ({', '.join(marques)})" if marques else ""))
                if niveau + 1 < CHERCHE_PROFONDEUR:
                    visiter(enfant, niveau + 1)

        visiter(cadre, 0)
        if len(lignes) >= ARBRE_MAX:
            lignes.append("… (la suite est coupée)")
        return lignes or ["(vide)"]

    def sonder(self) -> list[str]:
        """Chaque étape de la lecture, avec la réponse de macOS : pour voir où ça bloque. Jamais le texte lui-même."""
        from AppKit import NSRunningApplication

        AS = _ax()

        def nom(pid):
            appli = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if pid else None
            return f"{appli.localizedName()} (pid {pid})" if appli is not None else f"pid {pid}"

        def reponse(erreur, ok):
            return f"✅ {ok}" if erreur == 0 else f"⛔ {code(erreur)}"

        def oui_non(erreur, valeur, non="non"):
            return f"⛔ {code(erreur)}" if erreur else "✅ oui" if valeur else f"⚠️ {non}"

        lignes = []
        try:
            erreur, _ = self._lire(AS.AXUIElementCreateSystemWide(), "AXFocusedApplication")
            pid = self._pid_focus()
            lignes.append("appli active (accessibilité) : " + reponse(erreur, nom(pid)))
            for source, candidat in self._pids_devant():
                erreur, devant = self._lire(AS.AXUIElementCreateApplication(candidat), "AXFrontmost")
                lignes.append(f"appli devant ({source}) : {nom(candidat)} · elle confirme être devant : "
                              + oui_non(erreur, devant))
            pid = self._pid_devant()
            lignes.append("→ appli retenue : " + (nom(pid) if pid else "⛔ aucune"))
            erreur, _ = self._lire(AS.AXUIElementCreateSystemWide(), "AXFocusedUIElement")
            lignes.append("champ (système) : " + reponse(erreur, "trouvé"))
            if pid:
                erreur, _ = self._lire(AS.AXUIElementCreateApplication(pid), "AXFocusedUIElement")
                lignes.append("champ (appli) : " + reponse(erreur, "trouvé"))
            champ = self._focus(pid)
            if champ is None:
                return lignes
            if not self._lisible(champ):
                erreur, noms = AS.AXUIElementCopyAttributeNames(champ, None)
                lignes.append(f"champ donné : {self._role(champ)}, sans texte lisible · ce qu'il sait dire : "
                              + (", ".join(str(n).removeprefix("AX") for n in noms or []) if erreur == 0 else code(erreur)))
                lignes.append("ce qu'il contient :")
                lignes.extend(f"   {ligne}" for ligne in self._arbre(champ))
                dedans = self._texte_dedans(champ)
                lignes.append("→ texte trouvé dedans : " + (f"✅ {self._role(dedans)}" if dedans is not None else "⛔ aucun"))
                champ = dedans if dedans is not None else champ
            role = self._role(champ)
            erreur, texte = self._lire(champ, "AXValue")
            lignes.append(f"champ {role} · texte : " + reponse(erreur, f"{len(str(texte or ''))} caractères"))
            erreur, _ = self._lire(champ, "AXSelectedTextRange")
            lignes.append("curseur : " + reponse(erreur, "lu"))
            erreur, modifiable = AS.AXUIElementIsAttributeSettable(champ, "AXSelectedText", None)
            lignes.append("remplaçable : " + oui_non(erreur, modifiable, "non (l'anglais sera copié)"))
        except Exception as e:  # le diagnostic ne doit jamais planter
            lignes.append(f"⛔ {type(e).__name__} : {e}")
        return lignes

    # --- lire et remplacer --------------------------------------------------------------------------

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
