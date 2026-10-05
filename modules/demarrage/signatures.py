"""Qui a signé un programme (codesign), et quand tu as ouvert une app pour la dernière fois (mdls).

codesign coûte 50 à 200 ms par programme : les résultats sont gardés en cache par chemin, date de modification et
taille, et les appels manquants partent en parallèle.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from modules.demarrage.systeme import Systeme

PARALLELES = 8


@dataclass
class Signature:
    etat: str  # apple, developpeur, app_store, adhoc, non_signe, invalide, introuvable, inconnue
    editeur: str | None = None
    equipe: str | None = None
    autorite: str | None = None

    @property
    def valide(self) -> bool:
        return self.etat in ("apple", "developpeur", "app_store")


def analyser_codesign(code: int, texte: str) -> Signature:
    """La sortie de « codesign -dv --verbose=2 » (elle est écrite sur la sortie d'erreur)."""
    if "not signed at all" in texte:
        return Signature("non_signe")
    if "No such file" in texte or "No such file or directory" in texte:
        return Signature("introuvable")
    autorites = re.findall(r"^Authority=(.+)$", texte, re.M)
    equipe_m = re.search(r"^TeamIdentifier=(.+)$", texte, re.M)
    equipe = equipe_m.group(1).strip() if equipe_m and equipe_m.group(1).strip() != "not set" else None
    if code != 0 and not autorites:
        return Signature("invalide" if texte.strip() else "inconnue", equipe=equipe)
    if re.search(r"^Signature=adhoc$", texte, re.M) and not autorites:
        return Signature("adhoc", equipe=equipe)
    premiere = autorites[0].strip() if autorites else ""
    if premiere == "Software Signing":
        return Signature("apple", "Apple", equipe, premiere)
    if premiere == "Apple Mac OS Application Signing":
        return Signature("app_store", None, equipe, premiere)
    m = re.match(
        r"^(?:Developer ID Application|Apple Development|Apple Distribution|Mac Developer)\s*:\s*(.+)$", premiere
    )
    if m:
        editeur = re.sub(r"\s*\([A-Z0-9]{10}\)\s*$", "", m.group(1)).strip()
        return Signature("developpeur", editeur or None, equipe, premiere)
    if premiere:
        return Signature("inconnue", None, equipe, premiere)
    return Signature("inconnue", equipe=equipe)


class CacheSignatures:
    """Cache en mémoire, que la base remplit et sauvegarde (db.Base.signatures / sauver_signatures)."""

    def __init__(self, entrees: dict[str, dict[str, Any]] | None = None):
        self.entrees: dict[str, dict[str, Any]] = dict(entrees or {})
        self.modifie = False

    def lire(self, chemin: str, empreinte: str) -> Signature | None:
        e = self.entrees.get(chemin)
        if e and e.get("empreinte") == empreinte:
            return Signature(**e["signature"])
        return None

    def ecrire(self, chemin: str, empreinte: str, sig: Signature) -> None:
        self.entrees[chemin] = {"empreinte": empreinte, "signature": asdict(sig)}
        self.modifie = True


def empreinte(systeme: Systeme, chemin: str) -> str | None:
    try:
        st = systeme.chemin(chemin).stat()
    except OSError:
        return None
    return f"{int(st.st_mtime)}:{st.st_size}"


def signer(
    systeme: Systeme, chemins: Iterable[str], cache: CacheSignatures, delai: float = 5.0
) -> dict[str, Signature]:
    """La signature de chaque programme ; un programme absent vaut « introuvable » sans lancer codesign."""
    resultats: dict[str, Signature] = {}
    a_faire: list[tuple[str, str]] = []
    for chemin in dict.fromkeys(chemins):
        emp = empreinte(systeme, chemin)
        if emp is None:
            resultats[chemin] = Signature("introuvable")
            continue
        connu = cache.lire(chemin, emp)
        if connu:
            resultats[chemin] = connu
        else:
            a_faire.append((chemin, emp))
    if a_faire and not systeme.a_la_commande("codesign"):
        return {**resultats, **{c: Signature("inconnue") for c, _ in a_faire}}

    def un(chemin: str) -> Signature:
        r = systeme.executer(["codesign", "-dv", "--verbose=2", chemin], delai=delai)
        if r.code == 124:
            return Signature("inconnue")
        return analyser_codesign(r.code, r.erreur + r.sortie)

    with ThreadPoolExecutor(max_workers=PARALLELES) as pool:
        for (chemin, emp), sig in zip(a_faire, pool.map(un, [c for c, _ in a_faire]), strict=True):
            resultats[chemin] = sig
            if sig.etat != "inconnue":  # une panne passagère ne se garde pas
                cache.ecrire(chemin, emp, sig)
    return resultats


def analyser_mdls(texte: str) -> float | None:
    """« 2026-06-01 08:12:33 +0000 » → instant ; « (null) » → None."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})", texte)
    if not m:
        return None
    a, mo, j, h, mi, s = (int(x) for x in m.groups()[:6])
    decalage = (int(m.group(8)) * 3600 + int(m.group(9)) * 60) * (1 if m.group(7) == "+" else -1)
    try:
        return calendar.timegm((a, mo, j, h, mi, s, 0, 0, 0)) - decalage
    except (ValueError, OverflowError):
        return None


def dernieres_utilisations(systeme: Systeme, apps: Iterable[str], delai: float = 5.0) -> dict[str, float | None]:
    if not systeme.a_la_commande("mdls"):
        return {}
    resultats: dict[str, float | None] = {}
    for app in dict.fromkeys(apps):
        r = systeme.executer(["mdls", "-raw", "-name", "kMDItemLastUsedDate", app], delai=delai)
        quand = analyser_mdls(r.sortie) if r.ok else None
        resultats[app] = quand if quand is None or quand <= systeme.maintenant() + 86400 else None  # date absurde
    return resultats
