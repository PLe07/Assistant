"""Petites questions posées à macOS, partagées par les modules."""

import subprocess


def sur_secteur() -> bool:
    """True si le Mac est branché (en cas de doute, on considère qu'il l'est)."""
    try:
        sortie = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True
    return "Battery Power" not in sortie
