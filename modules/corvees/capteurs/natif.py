"""Tout ce qui parle à macOS, isolé ici (et remplacé par des imitations dans les tests).

Chaque fonction renvoie None au lieu de planter : le capteur qui l'appelle passe alors en mode dégradé.
Aucune de ces fonctions ne lit le contenu de tes documents ni ne capture l'écran ou le clavier.
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Any

# Des fenêtres du système, jamais « l'appli devant » (noms anglais et français).
FENETRES_SYSTEME = {
    "WindowManager",
    "Window Server",
    "Dock",
    "SystemUIServer",
    "Control Center",
    "Centre de contrôle",
    "Notification Center",
    "Centre de notifications",
    "Spotlight",
    "loginwindow",
    "screencaptureui",
    "Wallpaper",
    "Fond d'écran",
}


class Natif:
    """Les questions posées à macOS par les capteurs."""

    def __init__(self) -> None:
        self.disponible = sys.platform == "darwin"

    # --- l'appli au premier plan (C1) -------------------------------------------------------------------------

    def appli_devant(self) -> tuple[str, str] | None:
        """(nom, identifiant) de l'appli au premier plan, d'après la liste des applis de macOS (sans autorisation)."""
        try:
            from AppKit import NSWorkspace

            appli = NSWorkspace.sharedWorkspace().frontmostApplication()
            if appli is None:
                return None
            return str(appli.localizedName() or ""), str(appli.bundleIdentifier() or "")
        except Exception:
            return None

    def appli_devant_secours(self) -> tuple[str, str] | None:
        """En secours : le propriétaire de la fenêtre normale la plus en avant (sans autorisation non plus). Les
        fenêtres du système (Stage Manager, Dock, Centre de contrôle…) ne comptent pas : ce ne sont pas des applis."""
        try:
            import Quartz

            options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
            for w in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
                proprietaire = str(w.get(Quartz.kCGWindowOwnerName, "") or "")
                if int(w.get(Quartz.kCGWindowLayer, 1)) != 0 or proprietaire in FENETRES_SYSTEME:
                    continue
                cadre = w.get(Quartz.kCGWindowBounds) or {}
                if float(cadre.get("Width", 0)) < 200 or float(cadre.get("Height", 0)) < 120:
                    continue
                return proprietaire, ""
            return None
        except Exception:
            return None

    def pomper(self, secondes: float) -> None:
        """Laisse macOS mettre à jour la liste des applis (elle n'avance que si la boucle d'événements tourne)."""
        try:
            from Foundation import NSDate, NSRunLoop

            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(secondes))
        except Exception:
            import time

            time.sleep(secondes)

    # --- le titre de la fenêtre (C2) --------------------------------------------------------------------------

    def accessibilite(self) -> bool:
        try:
            import ApplicationServices

            return bool(ApplicationServices.AXIsProcessTrusted())
        except Exception:
            return False

    def titre_fenetre(self) -> str | None:
        """Le titre de la fenêtre au premier plan (autorisation « Accessibilité »)."""
        try:
            import ApplicationServices as AS
            from AppKit import NSWorkspace

            appli = NSWorkspace.sharedWorkspace().frontmostApplication()
            if appli is None:
                return None
            element = AS.AXUIElementCreateApplication(appli.processIdentifier())
            erreur, fenetre = AS.AXUIElementCopyAttributeValue(element, "AXFocusedWindow", None)
            if erreur or fenetre is None:
                return None
            erreur, titre = AS.AXUIElementCopyAttributeValue(fenetre, "AXTitle", None)
            return None if erreur or titre is None else str(titre)
        except Exception:
            return None

    # --- le presse-papiers (C6) -------------------------------------------------------------------------------

    def presse_papiers(self) -> tuple[int, list[str], bytes | None] | None:
        """(compteur de changements, types, texte en octets pour l'empreinte). Le texte n'est jamais gardé."""
        try:
            from AppKit import NSPasteboard

            pb = NSPasteboard.generalPasteboard()
            types = [str(t) for t in (pb.types() or [])]
            texte = pb.stringForType_("public.utf8-plain-text")
            return int(pb.changeCount()), types, (str(texte).encode() if texte is not None else None)
        except Exception:
            return None

    def compteur_presse_papiers(self) -> int | None:
        try:
            from AppKit import NSPasteboard

            return int(NSPasteboard.generalPasteboard().changeCount())
        except Exception:
            return None

    # --- l'inactivité -----------------------------------------------------------------------------------------

    def inactivite(self) -> float | None:
        """Secondes depuis ta dernière action (clavier, souris) : seulement la durée, jamais l'action."""
        try:
            import Quartz

            return float(
                Quartz.CGEventSourceSecondsSinceLastEventType(
                    Quartz.kCGEventSourceStateCombinedSessionState, 0xFFFFFFFF
                )
            )
        except Exception:
            pass
        try:
            sortie = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r'"HIDIdleTime" = (\d+)', sortie)
            return int(m.group(1)) / 1e9 if m else None
        except Exception:
            return None

    # --- l'alimentation ---------------------------------------------------------------------------------------

    def alimentation(self) -> tuple[bool, int | None]:
        """(branché au secteur ?, pourcentage de batterie). En cas de doute : branché."""
        try:
            sortie = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
        except Exception:
            return True, None
        m = re.search(r"(\d+)%", sortie)
        return "Battery Power" not in sortie, (int(m.group(1)) if m else None)


def natif() -> Any:
    """L'accès à macOS, ou None ailleurs (le conteneur de construction, les tests)."""
    return Natif() if sys.platform == "darwin" else None
