"""Petits outils pour garnir un faux Mac : plists, programmes, apps."""

from __future__ import annotations

import plistlib
from typing import Any

from modules.demarrage.systeme import Resultat
from tests.demarrage.faux_mac.systeme_faux import FauxMac


def plist(mac: FauxMac, chemin: str, binaire: bool = False, **cles: Any) -> str:
    fmt = plistlib.FMT_BINARY if binaire else plistlib.FMT_XML
    mac.fichier(chemin, plistlib.dumps(cles, fmt=fmt))
    return chemin


def programme(mac: FauxMac, chemin: str) -> str:
    p = mac.fichier(chemin, b"\xcf\xfa\xed\xfe binaire")
    p.chmod(0o755)
    return chemin


def app(mac: FauxMac, chemin: str, bundle_id: str, nom: str | None = None, executable: str | None = None) -> str:
    executable = executable or chemin.rsplit("/", 1)[-1].removesuffix(".app")
    info: dict[str, Any] = {"CFBundleIdentifier": bundle_id, "CFBundleExecutable": executable}
    if nom:
        info["CFBundleName"] = nom
    plist(mac, f"{chemin}/Contents/Info.plist", **info)
    programme(mac, f"{chemin}/Contents/MacOS/{executable}")
    return chemin


def codesign(table: dict[str, str]):
    """Une réponse de codesign selon le chemin : table chemin → sortie (sur la sortie d'erreur, comme le vrai)."""

    def repondre(commande: list[str], mac: FauxMac) -> Resultat:
        sortie = table.get(commande[-1])
        if sortie is None:
            return Resultat(1, "", f"{commande[-1]}: code object is not signed at all\n")
        return Resultat(0, "", sortie)

    return repondre


def signe_par(editeur: str, equipe: str) -> str:
    return (
        f"Authority=Developer ID Application: {editeur} ({equipe})\nAuthority=Developer ID Certification Authority\n"
        f"Authority=Apple Root CA\nTeamIdentifier={equipe}\n"
    )


SIGNE_APPLE = (
    "Authority=Software Signing\nAuthority=Apple Code Signing Certification Authority\nTeamIdentifier=not set\n"
)
