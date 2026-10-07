"""Les dates d'anniversaire (§6) : lecture des formats courants, prochaine occurrence, âge, 29 février, fuseau.

- « 1999-03-14 », « 14/03/1999 », « 14/03 », « 03-14 », « --03-14 » (format vCard sans année) sont compris ;
- né un 29 février : fêté le 28 février les années non bissextiles (réglage `date_29_fevrier`, ou « 01-03 ») ;
- sans année : pas d'âge ;
- « aujourd'hui » se calcule dans le fuseau des réglages (Europe/Paris par défaut), pas dans celui du Mac en voyage.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

ANNEE_MIN = 1900


@dataclass(frozen=True)
class DateNaissance:
    jour: int
    mois: int
    annee: int | None = None

    def texte(self) -> str:
        return f"{self.jour:02d}/{self.mois:02d}" + (f"/{self.annee}" if self.annee else "")


class DateInvalide(ValueError):
    pass


_ISO = re.compile(r"^(?:(?P<a>\d{4})|-?-?)-?(?P<m>\d{1,2})-(?P<j>\d{1,2})$")
_FR = re.compile(r"^(?P<j>\d{1,2})[/.\-](?P<m>\d{1,2})(?:[/.\-](?P<a>\d{4}))?$")


def lire(texte: str, aujourdhui: date | None = None) -> DateNaissance:
    """Une date d'anniversaire écrite à la main ; lève DateInvalide avec un message clair."""
    t = str(texte).strip()
    m = _ISO.match(t) or _FR.match(t)
    if not m:
        raise DateInvalide(f"« {t} » n'est pas une date (écris 14/03/1999, 14/03 ou 1999-03-14)")
    jour, mois = int(m.group("j")), int(m.group("m"))
    annee = int(m.group("a")) if m.group("a") else None
    return valider(jour, mois, annee, aujourdhui)


def valider(jour: int, mois: int, annee: int | None = None, aujourdhui: date | None = None) -> DateNaissance:
    if not 1 <= mois <= 12:
        raise DateInvalide(f"mois {mois} impossible")
    # Sans année, le 29 février est permis ; avec une année, il faut qu'elle soit bissextile.
    maxi = calendar.monthrange(annee if annee else 2000, mois)[1]
    if not 1 <= jour <= maxi:
        raise DateInvalide(f"le {jour:02d}/{mois:02d}" + (f"/{annee}" if annee else "") + " n'existe pas")
    if annee is not None:
        limite = (aujourdhui or date.today()).year
        if not ANNEE_MIN <= annee <= limite:
            raise DateInvalide(f"année {annee} improbable : elle est ignorée")
    return DateNaissance(jour, mois, annee)


def dans_l_annee(d: DateNaissance, annee: int, regle_29: str = "28-02") -> date:
    """La date fêtée cette année-là (29 février → 28 février ou 1er mars les années non bissextiles)."""
    if d.mois == 2 and d.jour == 29 and not calendar.isleap(annee):
        return date(annee, 3, 1) if regle_29 == "01-03" else date(annee, 2, 28)
    return date(annee, d.mois, d.jour)


def prochaine(d: DateNaissance, aujourdhui: date, regle_29: str = "28-02") -> date:
    """Le prochain anniversaire, aujourd'hui compris."""
    cette_annee = dans_l_annee(d, aujourdhui.year, regle_29)
    return cette_annee if cette_annee >= aujourdhui else dans_l_annee(d, aujourdhui.year + 1, regle_29)


def age(d: DateNaissance, le_jour: date) -> int | None:
    """L'âge atteint ce jour-là (l'anniversaire du jour compte). None sans année, ou si l'âge est absurde."""
    if d.annee is None:
        return None
    a = le_jour.year - d.annee
    fete_le_28 = d.mois == 2 and d.jour == 29 and (le_jour.month, le_jour.day) == (2, 28)
    if (le_jour.month, le_jour.day) < (d.mois, d.jour) and not (fete_le_28 and not calendar.isleap(le_jour.year)):
        a -= 1
    return a if 1 <= a <= 120 else None


def aujourdhui(maintenant: float, fuseau: str = "Europe/Paris") -> date:
    return datetime.fromtimestamp(maintenant, ZoneInfo(fuseau)).date()


def moment(jour: date, heure: str, fuseau: str = "Europe/Paris") -> float:
    """L'horodatage de `jour` à `heure` (HH:MM) dans le fuseau (heure d'été comprise)."""
    h, m = (int(x) for x in heure.split(":"))
    return datetime(jour.year, jour.month, jour.day, h, m, tzinfo=ZoneInfo(fuseau)).timestamp()
