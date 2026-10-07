"""Les mots de l'interface : durées, heures et montants, en français simple."""

from __future__ import annotations

import time


def duree(secondes: float) -> str:
    """« 40 s », « 5 min », « 2 h », « 2 h 30 », « 3 j »."""
    s = max(0, int(secondes))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        h, m = divmod(s // 60, 60)
        return f"{h} h" if m == 0 or h >= 10 else f"{h} h {m:02d}"
    return f"{s // 86400} j"


def il_y_a(ts: float | None, maintenant: float) -> str:
    if ts is None:
        return "jamais"
    ecart = maintenant - ts
    if ecart < 60:
        return "à l'instant"
    return f"il y a {duree(ecart)}"


def heure(ts: float) -> str:
    """« 7h15 »."""
    t = time.localtime(ts)
    return f"{t.tm_hour}h{t.tm_min:02d}"


def heure_texte(hhmm: str) -> str:
    """« 07:15 » → « 7h15 »."""
    h, _, m = hhmm.partition(":")
    try:
        return f"{int(h)}h{int(m):02d}"
    except ValueError:
        return hhmm


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def quand(ts: float, maintenant: float) -> str:
    """« aujourd'hui à 7h15 », « demain à 7h15 », « hier à 21h00 », « jeudi à 7h15 »."""
    a, b = time.localtime(ts), time.localtime(maintenant)
    jours = (time.mktime((a.tm_year, a.tm_mon, a.tm_mday, 12, 0, 0, 0, 0, -1))
             - time.mktime((b.tm_year, b.tm_mon, b.tm_mday, 12, 0, 0, 0, 0, -1))) / 86400  # fmt: skip
    jours = round(jours)
    mot = {0: "aujourd'hui", 1: "demain", -1: "hier"}.get(jours)
    if mot is None:
        mot = JOURS[a.tm_wday] if 0 < jours < 7 else time.strftime("%d/%m", a)
    return f"{mot} à {heure(ts)}"


def dollars(montant: float | None) -> str:
    if montant is None:
        return "inconnu"
    return f"{montant:.2f} $".replace(".", ",")


def pourcent(valeur: float | None, decimales: int = 0) -> str:
    if valeur is None:
        return "inconnu"
    return f"{valeur:.{decimales}f} %".replace(".", ",")


def mo(valeur: float | None) -> str:
    if valeur is None:
        return "inconnu"
    if valeur >= 1024:
        return f"{valeur / 1024:.1f} Go".replace(".", ",")
    return f"{valeur:.0f} Mo"


def pluriel(n: int, singulier: str, pluriel_: str | None = None) -> str:
    return f"{n} {singulier if n <= 1 else (pluriel_ or singulier + 's')}"
