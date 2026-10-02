"""Ce que les yeux voient, 100 % sur ton Mac (macOS uniquement).

- fenetre_au_premier_plan() : quelle fenêtre est devant toi (sans rien capturer).
- lire_fenetre() : capture CETTE fenêtre seulement, en mémoire, lit son texte avec Vision
  (la reconnaissance de texte intégrée à macOS), puis jette l'image.
Aucune image n'est jamais écrite sur le disque.

Capture : ScreenCaptureKit (l'outil actuel d'Apple), et l'ancienne méthode en secours.
"""

import threading
import time

TERMINAUX = ("Terminal", "iTerm2", "Warp", "Ghostty", "Alacritty", "kitty")


def autorise() -> bool:
    """L'autorisation « Enregistrement de l'écran » est-elle accordée à ce programme ?"""
    import Quartz

    return bool(Quartz.CGPreflightScreenCaptureAccess())


def demander_autorisation() -> None:
    """Fait apparaître la demande de macOS (une seule fois : ensuite, c'est dans les Réglages)."""
    import Quartz

    Quartz.CGRequestScreenCaptureAccess()


def inactif_depuis() -> float:
    """Secondes depuis ta dernière action au clavier, à la souris ou au trackpad."""
    import Quartz

    return float(Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType))


def ecran_verrouille() -> bool:
    import Quartz

    session = Quartz.CGSessionCopyCurrentDictionary() or {}
    return bool(session.get("CGSSessionScreenIsLocked", False))


def _bundle(pid: int) -> str:
    try:
        from AppKit import NSRunningApplication

        appli = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        return str(appli.bundleIdentifier() or "") if appli is not None else ""
    except Exception:
        return ""


def fenetre_au_premier_plan() -> dict | None:
    """La fenêtre normale la plus en avant (les menus et barres flottantes sont ignorés)."""
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for w in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
        if int(w.get(Quartz.kCGWindowLayer, 1)) != 0 or float(w.get(Quartz.kCGWindowAlpha, 1)) == 0:
            continue
        cadre = w.get(Quartz.kCGWindowBounds) or {}
        if float(cadre.get("Width", 0)) < 200 or float(cadre.get("Height", 0)) < 120:
            continue
        pid = int(w.get(Quartz.kCGWindowOwnerPID, 0))
        return {
            "id": int(w.get(Quartz.kCGWindowNumber, 0)),
            "pid": pid,
            "appli": str(w.get(Quartz.kCGWindowOwnerName, "") or ""),
            "titre": str(w.get(Quartz.kCGWindowName, "") or ""),
            "bundle": _bundle(pid),
        }
    return None


def _attendre(fini: threading.Event, delai: float) -> bool:
    """Attend une réponse de macOS. Sur le fil principal, on laisse aussi tourner la boucle
    d'événements de macOS : certaines réponses n'arrivent que par elle."""
    if threading.current_thread() is not threading.main_thread():
        return fini.wait(delai)
    from Foundation import NSDate, NSRunLoop

    fin = time.time() + delai
    while not fini.is_set() and time.time() < fin:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.01))
        fini.wait(0.04)
    return fini.is_set()


def _capturer_sck(id_fenetre: int):
    """ScreenCaptureKit (macOS 14 et plus) : capture une seule fenêtre, même partiellement cachée."""
    import ScreenCaptureKit as SCK

    if not hasattr(SCK, "SCScreenshotManager"):
        return None
    recu, fini = {}, threading.Event()

    def contenu_recu(contenu, erreur):
        recu["contenu"] = contenu
        fini.set()

    SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
        True, True, contenu_recu)
    if not _attendre(fini, 5) or recu.get("contenu") is None:
        return None
    cible = next((w for w in recu["contenu"].windows() if int(w.windowID()) == id_fenetre), None)
    if cible is None:
        return None
    filtre = SCK.SCContentFilter.alloc().initWithDesktopIndependentWindow_(cible)
    reglage = SCK.SCStreamConfiguration.alloc().init()
    cadre, echelle = filtre.contentRect(), float(filtre.pointPixelScale() or 1)
    largeur = min(int(cadre.size.width * echelle), 3200)  # assez pour lire, pas plus
    reglage.setWidth_(largeur)
    reglage.setHeight_(int(cadre.size.height * largeur / max(cadre.size.width, 1)))
    reglage.setShowsCursor_(False)
    image, fini_image = {}, threading.Event()

    def image_recue(img, erreur):
        image["img"] = img
        fini_image.set()

    SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(filtre, reglage, image_recue)
    if not _attendre(fini_image, 5):
        return None
    return image.get("img")


def _capturer_cg(id_fenetre: int):
    """L'ancienne méthode (CoreGraphics), en secours."""
    import Quartz

    return Quartz.CGWindowListCreateImage(Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
                                          id_fenetre, Quartz.kCGWindowImageBoundsIgnoreFraming)


_ORDRE = ["ScreenCaptureKit", "CoreGraphics"]  # la méthode qui vient de marcher passe en premier


def capturer(id_fenetre: int, methode: str | None = None):
    """(image en mémoire, méthode utilisée) ou (None, raison)."""
    fonctions = {"ScreenCaptureKit": _capturer_sck, "CoreGraphics": _capturer_cg}
    erreurs = []
    for nom in [methode] if methode else list(_ORDRE):
        try:
            image = fonctions[nom](id_fenetre)
        except Exception as e:  # méthode absente sur cette version de macOS…
            erreurs.append(f"{nom} : {type(e).__name__}")
            continue
        if image is not None:
            if not methode and _ORDRE[0] != nom:  # pas d'attente inutile au prochain coup d'œil
                _ORDRE.remove(nom)
                _ORDRE.insert(0, nom)
            return image, nom
        erreurs.append(f"{nom} : rien reçu")
    return None, " · ".join(erreurs)


def lire_texte(image) -> list[str]:
    """Le texte de l'image, ligne par ligne, de haut en bas (Vision, sur ton Mac)."""
    import Vision
    from Foundation import NSDictionary

    requete = Vision.VNRecognizeTextRequest.alloc().init()
    requete.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    requete.setUsesLanguageCorrection_(True)
    try:
        requete.setRecognitionLanguages_(["fr-FR", "en-US"])
    except Exception:
        pass
    # Un vrai dictionnaire macOS, vide : un {} de Python fait planter Vision avec PyObjC 12.2
    # (« NSInvalidArgumentException - key does not exist »).
    gestion = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, NSDictionary.dictionary())
    ok, _ = gestion.performRequests_error_([requete], None)
    if not ok:
        return []
    lignes = []
    for observation in requete.results() or []:
        candidats = observation.topCandidates_(1)
        if candidats and len(candidats):
            cadre = observation.boundingBox()  # origine en bas à gauche : y grand = haut de l'écran
            lignes.append((-round(cadre.origin.y, 2), cadre.origin.x, str(candidats[0].string())))
    return [texte for _, _, texte in sorted(lignes)]


class Capteur:
    """Ce que le module utilise ; les tests le remplacent par une imitation."""

    def autorise(self) -> bool:
        return autorise()

    def demander_autorisation(self) -> None:
        demander_autorisation()

    def fenetre(self) -> dict | None:
        return fenetre_au_premier_plan()

    def absent(self, apres: float) -> bool:
        return ecran_verrouille() or inactif_depuis() > apres

    def lire(self, fenetre: dict) -> list[str] | None:
        """Capture en mémoire → texte → l'image est jetée. None si la capture a échoué."""
        image, _ = capturer(fenetre["id"])
        if image is None:
            return None
        try:
            return lire_texte(image)
        finally:
            del image
