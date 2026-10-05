"""S9 — les tâches planifiées : la crontab (`crontab -l`). Les clés StartInterval, StartCalendarInterval et
WatchPaths des plists sont lues avec chaque plist (déclencheurs de la fiche).
"""

from __future__ import annotations

import re
import shlex

from modules.demarrage.fichiers import existe, localiser
from modules.demarrage.modele import Declencheurs, Fiche, identifiant
from modules.demarrage.systeme import Systeme

_RACCOURCIS = {"@reboot": "au démarrage", "@yearly": "chaque année", "@annually": "chaque année",
               "@monthly": "chaque mois", "@weekly": "chaque semaine", "@daily": "chaque jour",
               "@midnight": "chaque nuit", "@hourly": "chaque heure"}  # fmt: skip


def analyser(systeme: Systeme, texte: str) -> list[Fiche]:
    fiches: list[Fiche] = []
    for ligne in texte.splitlines():
        brut = ligne.strip()
        if not brut or brut.startswith("#") or re.match(r"^\w+\s*=", brut):
            continue  # commentaire ou variable (MAILTO=…)
        mots = brut.split()
        if mots[0].startswith("@"):
            horaire, commande = _RACCOURCIS.get(mots[0], mots[0]), " ".join(mots[1:])
        elif len(mots) >= 6:
            horaire, commande = " ".join(mots[:5]), " ".join(mots[5:])
        else:
            continue
        try:
            premier = shlex.split(commande)[0] if commande else ""
        except ValueError:
            premier = commande.split()[0] if commande.split() else ""
        programme = localiser(systeme, premier) if premier else None
        fiches.append(
            Fiche(
                id=identifiant("cron", brut),
                label=f"cron : {premier.rsplit('/', 1)[-1] or '?'}",
                source="cron",
                programme=programme or premier or None,
                programme_existe=existe(systeme, programme) if programme else (False if premier else None),
                declencheurs=Declencheurs(au_chargement=mots[0] == "@reboot"),
                actif=True,
                desactive=False,
                details={"horaire": horaire},
            )
        )
    return fiches


def collecter(systeme: Systeme) -> tuple[list[Fiche], list[str]]:
    if not systeme.a_la_commande("crontab"):
        return [], ["crontab absent"]
    r = systeme.executer(["crontab", "-l"], delai=5.0)
    if not r.ok:
        if "no crontab" in r.erreur:
            return [], []
        return [], [f"crontab -l : {r.erreur.strip()[:100] or r.code}"]
    return analyser(systeme, r.sortie), []
