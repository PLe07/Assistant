"""L'ouverture de session : quand le Mac a démarré (sysctl), quand tu t'es connecté (last, ou le journal de
loginwindow, affiné par le plus ancien de tes processus), et quand le processeur s'est calmé.

« Calme » : le premier instant après la connexion où le processeur total reste sous 15 % de sa capacité pendant
30 secondes de suite (les deux seuils sont réglables).
"""

from __future__ import annotations

import calendar
import re
import time
from collections.abc import Iterable

from modules.demarrage.systeme import Systeme

_MOIS = {
    m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)
}
_LAST = re.compile(r"^(\S+)\s+console\s+\w{3} (\w{3})\s+(\d+) (\d{2}):(\d{2})")
_JOURNAL = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:([+-]\d{4}))?\s.*loginwindow")
_REPERES = re.compile(r"(?i)login ?success|performAutolaunch|sessionDidLogin|screenIsUnlocked")


def analyser_boottime(texte: str) -> float | None:
    m = re.search(r"sec = (\d+)", texte)
    return float(m.group(1)) if m else None


def _local_vers_utc(annee: int, mois: int, jour: int, h: int, mi: int, s: int = 0) -> float:
    """Une heure locale du Mac (sans fuseau écrit) → instant. time.mktime suit le fuseau et l'heure d'été."""
    return time.mktime((annee, mois, jour, h, mi, s, 0, 0, -1))


def analyser_last(texte: str, utilisateur: str, boot: float, maintenant: float | None = None) -> float | None:
    """La connexion « console » la plus récente après le démarrage (à la minute près ; last n'écrit pas l'année :
    celle du démarrage, ou la suivante pour une connexion juste après le Nouvel An)."""
    plafond = maintenant + 60 if maintenant is not None else boot + 31 * 86400
    for ligne in texte.splitlines():
        m = _LAST.match(ligne)
        if not m or m.group(1) != utilisateur or m.group(2) not in _MOIS:
            continue
        annee = time.localtime(boot).tm_year
        for a in (annee, annee + 1):
            quand = _local_vers_utc(a, _MOIS[m.group(2)], int(m.group(3)), int(m.group(4)), int(m.group(5)))
            if boot - 60 <= quand <= plafond:
                return quand
        return None  # la plus récente est d'avant ce démarrage : pas encore connecté depuis
    return None


def analyser_journal(texte: str, boot: float) -> float | None:
    """`log show … loginwindow` : la première ligne qui marque la connexion."""
    for ligne in texte.splitlines():
        m = _JOURNAL.match(ligne)
        if not m or not _REPERES.search(ligne):
            continue
        a, mo, j, h, mi, s = (int(x) for x in m.groups()[:6])
        if m.group(7):
            signe = 1 if m.group(7)[0] == "+" else -1
            decalage = signe * (int(m.group(7)[1:3]) * 3600 + int(m.group(7)[3:5]) * 60)
            quand = float(calendar.timegm((a, mo, j, h, mi, s, 0, 0, 0)) - decalage)
        else:
            quand = _local_vers_utc(a, mo, j, h, mi, s)
        if quand >= boot:
            return float(quand)
    return None


def demarrage(systeme: Systeme) -> float | None:
    r = systeme.executer(["sysctl", "-n", "kern.boottime"], delai=5)
    return analyser_boottime(r.sortie) if r.ok else None


def connexion(
    systeme: Systeme, boot: float, premier_processus: float | None, delai_journal: float = 15.0
) -> tuple[float | None, str]:
    """(instant de connexion, d'où il vient). premier_processus : le lancement de ton plus ancien processus."""
    quand, source = None, ""
    r = systeme.executer(["last", "-20", systeme.utilisateur], delai=5)
    if r.ok:
        quand, source = analyser_last(r.sortie, systeme.utilisateur, boot, systeme.maintenant()), "last"
    if quand is None and systeme.a_la_commande("log"):
        predicat = 'process == "loginwindow"'
        r = systeme.executer(["log", "show", "--last", "boot", "--style", "compact", "--predicate", predicat],
                             delai=delai_journal)  # fmt: skip
        if r.ok:
            quand, source = analyser_journal(r.sortie, boot), "journal"
    if premier_processus is not None and premier_processus >= boot:
        # last est à la minute près : ton premier processus donne la seconde, s'il est dans la même minute.
        if quand is None:
            return premier_processus, "processus"
        if 0 <= premier_processus - quand < 60:
            return premier_processus, f"{source} + processus"
    return quand, source if quand is not None else "inconnue"


def temps_jusquau_calme(
    releves: Iterable[tuple[float, float]], connexion: float, seuil_pct: float = 15.0, duree_s: float = 30.0
) -> float | None:
    """Secondes entre la connexion et le début de la première période calme d'au moins duree_s ; None si aucune.

    releves : (instant, processeur total en % de la capacité), triés ou non.
    """
    points = sorted((t, c) for t, c in releves if t >= connexion)
    debut: float | None = None
    for t, cpu in points:
        if cpu < seuil_pct:
            if debut is None:
                debut = t
            if t - debut >= duree_s:
                return debut - connexion
        else:
            debut = None
    return None
