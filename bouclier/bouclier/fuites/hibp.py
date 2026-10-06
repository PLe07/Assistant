"""La liste publique des fuites de Have I Been Pwned (`/api/v3/breaches`, sans clé), téléchargée une fois par jour
et gardée en cache. Respect des conditions : User-Agent identifiable (`reseau.AGENT`) et attribution visible
(« Have I Been Pwned, CC BY 4.0 ») dans le tableau de bord.

Option payante (désactivée) : avec ta propre clé HIBP dans config.toml, la vérification exacte de ton adresse
(`/api/v3/breachedaccount/<adresse>`). Sans clé, rien d'autre que la liste publique ne part ni n'arrive.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bouclier import reseau

URL_LISTE = "https://haveibeenpwned.com/api/v3/breaches"
URL_ADRESSE = "https://haveibeenpwned.com/api/v3/breachedaccount/"
ATTRIBUTION = "Données des fuites : Have I Been Pwned (haveibeenpwned.com), licence CC BY 4.0."
FRAICHEUR_S = 23 * 3600

Telecharger = Callable[..., reseau.Reponse]


@dataclass(frozen=True)
class Fuite:
    nom: str
    titre: str
    domaine: str
    date: dt.date | None
    ajoutee: dt.date | None
    donnees: tuple[str, ...]
    verifiee: bool
    sensible: bool
    comptes_touches: int


def _date(texte: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(texte)[:10])
    except ValueError:
        return None


def lire(corps: bytes) -> list[Fuite]:
    """Les fuites utilisables : avec un domaine, ni retirées, ni simples listes de spam, ni fabriquées."""
    try:
        brut = json.loads(corps)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    fuites = []
    for b in brut if isinstance(brut, list) else []:
        if not isinstance(b, dict) or not b.get("Domain") or not b.get("Name"):
            continue
        if b.get("IsRetired") or b.get("IsSpamList") or b.get("IsFabricated"):
            continue
        fuites.append(
            Fuite(
                str(b["Name"]),
                str(b.get("Title") or b["Name"]),
                str(b["Domain"]).lower(),
                _date(b.get("BreachDate")),
                _date(b.get("AddedDate")),
                tuple(b.get("DataClasses") or ()),
                bool(b.get("IsVerified")),
                bool(b.get("IsSensitive")),
                int(b.get("PwnCount") or 0),
            )  # fmt: skip
        )
    return fuites


class ListeFuites:
    def __init__(self, dossier: Path, telecharger: Telecharger = reseau.telecharger,
                 horloge: Callable[[], float] = time.time) -> None:  # fmt: skip
        self.fichier = dossier / "hibp-fuites.json"
        self.telecharger, self.horloge = telecharger, horloge

    def date(self) -> float | None:
        return self.fichier.stat().st_mtime if self.fichier.exists() else None

    def mettre_a_jour(self, forcer: bool = False) -> tuple[bool, str]:
        """(à jour ?, explication). Une panne garde la copie de la veille."""
        date = self.date()
        if not forcer and date is not None and self.horloge() - date < FRAICHEUR_S:
            return True, "liste des fuites déjà à jour aujourd'hui"
        try:
            r = self.telecharger(URL_LISTE, delai=60, max_octets=30_000_000)
        except (reseau.ErreurReseau, reseau.HoteInterdit) as e:
            return date is not None, f"liste des fuites injoignable ({e}) : copie précédente gardée"
        if r.statut != 200 or not lire(r.corps):
            return date is not None, f"liste des fuites illisible (code {r.statut}) : copie précédente gardée"
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        temporaire = self.fichier.with_suffix(".tmp")
        temporaire.write_bytes(r.corps)
        os.replace(temporaire, self.fichier)
        return True, "liste des fuites mise à jour"

    def fuites(self) -> list[Fuite]:
        return lire(self.fichier.read_bytes()) if self.fichier.exists() else []


def par_adresse(adresse: str, cle: str, telecharger: Telecharger = reseau.telecharger) -> set[str] | None:
    """Option payante : les noms des fuites qui contiennent exactement ton adresse. None si indisponible."""
    if not cle or "@" not in adresse:
        return None
    url = URL_ADRESSE + urllib.parse.quote(adresse) + "?truncateResponse=true"
    try:
        r = telecharger(url, delai=30, max_octets=2_000_000, entetes={"hibp-api-key": cle})
    except (reseau.ErreurReseau, reseau.HoteInterdit):
        return None
    if r.statut == 404:
        return set()
    if r.statut != 200:
        return None
    try:
        return {str(b["Name"]) for b in json.loads(r.corps) if isinstance(b, dict) and "Name" in b}
    except (json.JSONDecodeError, TypeError):
        return None
