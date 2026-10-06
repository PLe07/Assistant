"""Les en-têtes d'un mail : l'expéditeur est-il vraiment qui il prétend être ?

- `Authentication-Results` (ajouté par le serveur qui a reçu le mail) : SPF, DKIM, DMARC.
- Le nom affiché (« Crédit Agricole ») face à l'adresse réelle (xyz@googlemail.com).
- Le `Reply-To` : où partent les réponses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RESULTAT = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.IGNORECASE)
_DOMAINE_DMARC = re.compile(r"header\.from\s*=\s*([a-z0-9.\-]+)", re.IGNORECASE)
_DOMAINE_DKIM = re.compile(r"header\.(?:i|d)\s*=\s*@?([a-z0-9.\-]+)", re.IGNORECASE)

WEBMAILS = frozenset(
    {"gmail.com", "googlemail.com", "outlook.com", "outlook.fr", "hotmail.com", "hotmail.fr", "live.com", "live.fr",
     "yahoo.com", "yahoo.fr", "protonmail.com", "proton.me", "icloud.com", "me.com", "aol.com", "gmx.fr", "gmx.com",
     "laposte.net", "orange.fr", "free.fr", "sfr.fr", "wanadoo.fr", "mail.com", "yandex.com", "tutanota.com"}
)  # fmt: skip


@dataclass(frozen=True)
class Authentification:
    spf: str = "absent"
    dkim: str = "absent"
    dmarc: str = "absent"
    domaine_dmarc: str = ""
    domaines_dkim: tuple[str, ...] = ()

    @property
    def authentifie(self) -> bool:
        return self.dmarc == "pass" or (self.dkim == "pass" and self.spf == "pass")

    @property
    def usurpe(self) -> bool:
        return self.dmarc == "fail"

    @property
    def douteux(self) -> bool:
        return self.spf in ("fail", "softfail") and self.dkim in ("none", "fail", "absent", "neutral")


def lire_authentification(entete: str) -> Authentification:
    if not entete:
        return Authentification()
    valeurs: dict[str, str] = {}
    for m in _RESULTAT.finditer(entete):
        valeurs.setdefault(m.group(1).lower(), m.group(2).lower())
    dmarc = _DOMAINE_DMARC.search(entete)
    return Authentification(
        spf=valeurs.get("spf", "absent"),
        dkim=valeurs.get("dkim", "absent"),
        dmarc=valeurs.get("dmarc", "absent"),
        domaine_dmarc=dmarc.group(1).lower() if dmarc else "",
        domaines_dkim=tuple(d.lower() for d in _DOMAINE_DKIM.findall(entete)),
    )


def domaine_adresse(adresse: str) -> str:
    return adresse.rsplit("@", 1)[-1].strip().lower() if "@" in adresse else ""
