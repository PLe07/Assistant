"""L'adaptateur générique : pour tout module inconnu (un futur `com.<session>.xxx`). État launchd, processus,
journaux (ceux que son plist déclare, et `~/Library/Logs/<Nom>/`), tailles. Rien de plus : sans connaître son
format, on ne lit pas sa base."""

from tableau.adaptateurs.base import Adaptateur


class Generique(Adaptateur):
    nom = "generique"
