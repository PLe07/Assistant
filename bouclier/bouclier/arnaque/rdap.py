"""La date de création d'un nom de domaine, par RDAP (le successeur public de « whois »).

Seul le **nom de domaine** part sur le réseau (vers rdap.org, qui renvoie au registre) : jamais l'adresse complète
d'un lien, jamais le lien lui-même. Réponses gardées en cache : une date ne change pas (1 an), un échec est
retenté le lendemain. Délai court (5 s) : un RDAP lent n'empêche pas de répondre.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from collections.abc import Callable

from bouclier import reseau
from bouclier.db import Base

CACHE_DATE_S = 365 * 86400
CACHE_ECHEC_S = 86400
_DOMAINE = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z0-9\-]{2,63}$")

Telecharger = Callable[..., reseau.Reponse]


def date_de_creation(reponse_json: dict) -> dt.date | None:
    for evenement in reponse_json.get("events", []) or []:
        if str(evenement.get("eventAction", "")).lower() == "registration":
            brut = str(evenement.get("eventDate", ""))[:10]
            try:
                return dt.date.fromisoformat(brut)
            except ValueError:
                return None
    return None


class ClientRdap:
    def __init__(
        self,
        base: Base,
        telecharger: Telecharger = reseau.telecharger,
        horloge: Callable[[], float] = time.time,
        delai: float = 5.0,
    ) -> None:
        self.base = base
        self.telecharger = telecharger
        self.horloge = horloge
        self.delai = delai

    def _cache(self, domaine: str) -> tuple[bool, dt.date | None]:
        ligne = self.base.cx.execute(
            "SELECT creation, verifie_le, erreur FROM rdap WHERE domaine = ?", (domaine,)
        ).fetchone()
        if not ligne:
            return False, None
        age = self.horloge() - float(ligne["verifie_le"])
        if ligne["creation"] and age < CACHE_DATE_S:
            return True, dt.date.fromisoformat(ligne["creation"])
        if not ligne["creation"] and age < CACHE_ECHEC_S:
            return True, None
        return False, None

    def _noter(self, domaine: str, creation: dt.date | None, erreur: str = "") -> None:
        with self.base.transaction() as cx:
            cx.execute(
                "INSERT OR REPLACE INTO rdap(domaine, creation, verifie_le, erreur) VALUES (?, ?, ?, ?)",
                (domaine, creation.isoformat() if creation else None, self.horloge(), erreur),
            )

    def __call__(self, domaine: str) -> dt.date | None:
        domaine = domaine.lower().strip(".")
        if not _DOMAINE.match(domaine):
            return None
        trouve, valeur = self._cache(domaine)
        if trouve:
            return valeur
        try:
            r = self.telecharger(
                f"https://rdap.org/domain/{domaine}",
                delai=self.delai,
                max_octets=2_000_000,
                entetes={"Accept": "application/rdap+json, application/json"},
                domaine_rdap=domaine,
            )
        except (reseau.ErreurReseau, reseau.HoteInterdit) as e:
            self._noter(domaine, None, e.__class__.__name__)
            return None
        if r.statut != 200:
            self._noter(domaine, None, f"HTTP {r.statut}")
            return None
        try:
            creation = date_de_creation(json.loads(r.corps))
        except (json.JSONDecodeError, AttributeError, TypeError):
            creation = None
        self._noter(domaine, creation, "" if creation else "sans date")
        return creation
