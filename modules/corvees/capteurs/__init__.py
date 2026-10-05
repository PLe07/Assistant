"""Les capteurs : chacun observe une seule chose, s'active dans les réglages et échoue proprement."""

from __future__ import annotations

from typing import Any

from modules.corvees.capteurs.apps import Apps
from modules.corvees.capteurs.base import Capteur, Memoire, Sortie
from modules.corvees.capteurs.fenetres import Fenetres
from modules.corvees.capteurs.fichiers import Fichiers
from modules.corvees.capteurs.inactivite import Inactivite
from modules.corvees.capteurs.navigateur import Navigateur
from modules.corvees.capteurs.pressepapiers import PressePapiers
from modules.corvees.capteurs.shell import Shell


def construire(
    reglages: dict[str, Any],
    sortie: Sortie,
    memoire: Memoire,
    natif: Any,
    empreinte: Any,
    exclu: Any,
) -> list[Capteur]:
    """Les capteurs activés dans les réglages, prêts à démarrer (l'appli au premier plan d'abord : les autres
    s'en servent)."""
    actifs = reglages["capteurs"]
    apps = Apps(reglages, sortie, memoire, natif)
    liste: list[Capteur] = [apps] if actifs["apps"] else []
    if actifs["fenetres"]:
        liste.append(Fenetres(reglages, sortie, memoire, natif))
    if actifs["fichiers"]:
        liste.append(Fichiers(reglages, sortie, memoire, natif, empreinte=empreinte, exclu=exclu))
    if actifs["shell"]:
        liste.append(Shell(reglages, sortie, memoire, natif))
    if actifs["navigateur"]:
        liste.append(Navigateur(reglages, sortie, memoire, natif))
    if actifs["pressepapiers"]:
        liste.append(PressePapiers(reglages, sortie, memoire, natif, apps=apps, empreinte=empreinte))
    if actifs["inactivite"]:
        liste.append(Inactivite(reglages, sortie, memoire, natif))
    return liste
