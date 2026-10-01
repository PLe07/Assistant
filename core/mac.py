"""Petites questions posées à macOS, partagées par les modules."""

import subprocess

TEXTES_AUTORISATION = {"accordee": "accordée", "refusee": "refusée", "jamais_demandee": "jamais demandée",
                       "restreinte": "bloquée par une restriction", None: "inconnue"}


def sur_secteur() -> bool:
    """True si le Mac est branché (en cas de doute, on considère qu'il l'est)."""
    try:
        sortie = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True
    return "Battery Power" not in sortie


def autorisation_micro() -> str | None:
    """Ce que macOS a décidé pour le micro de CE programme : accordee, refusee, jamais_demandee,
    restreinte (None : impossible à savoir). Ne déclenche aucune demande, ne touche pas au micro."""
    try:
        import objc

        objc.loadBundle("AVFoundation", {}, bundle_path="/System/Library/Frameworks/AVFoundation.framework",
                        scan_classes=False)
        statut = int(objc.lookUpClass("AVCaptureDevice").authorizationStatusForMediaType_("soun"))  # « soun » = audio
    except Exception:
        return None
    return {0: "jamais_demandee", 1: "restreinte", 2: "refusee", 3: "accordee"}.get(statut)
