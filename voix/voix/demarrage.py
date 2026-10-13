"""Ce dont Voix a besoin pour tourner sur ton Mac, lu au démarrage et en lecture seule : le catalogue (tes apps,
dossiers, sites, raccourcis Apple, alias et routines), tes modules installés et les modes d'Ambiance.

Chaque lecture passe par l'exécuteur de la liste blanche (`mdfind`, `shortcuts list`) : rien d'autre n'est lancé.
"""

from __future__ import annotations

from voix.actions.base import Outils
from voix.actions.executeur import Executeur, ProgrammeRefuse, dossiers_modules
from voix.actions.modules import decouvrir, modes_ambiance
from voix.actions.pont import Pont, PontAbsent
from voix.config import Chemins, Reglages
from voix.nlu import alias
from voix.nlu.catalogue import Catalogue, dossiers, sites
from voix.nlu.catalogue_apps import Executer, apps_installees, raccourcis_installes


def lecteur(executeur: Executeur) -> Executer:
    """Une lecture (`mdfind`, `shortcuts list`) par cet exécuteur, au format du lecteur de catalogue."""

    def lire(args: list[str], delai: float) -> tuple[int, str]:
        try:
            r = executeur.lancer(args[0], args[1:], delai)
        except ProgrammeRefuse:
            return 127, ""
        return r.code, r.sortie

    return lire


def outils(
    chemins: Chemins, reglages: Reglages, pont: Pont | None = None, executeur: Executeur | None = None
) -> Outils:
    x = executeur or Executeur(dossiers_modules=dossiers_modules(chemins.maison))
    lire = lecteur(x)
    commandes = alias.charger(chemins.commandes, chemins.maison)
    objets = apps_installees(chemins.maison, lire) + dossiers(chemins.maison) + sites() + raccourcis_installes(lire)
    modules = decouvrir(x)
    modes = modes_ambiance(modules["ambiance"]) if "ambiance" in modules else {}
    return Outils(
        x,
        chemins,
        reglages,
        Catalogue(objets + commandes.objets()),
        commandes,
        pont or PontAbsent(),
        modules=modules,
        modes_ambiance=modes,
    )
