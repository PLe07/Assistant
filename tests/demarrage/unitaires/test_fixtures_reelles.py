"""Les sorties réelles capturées sur le Mac (capturer.py) : anonymes. Ici, dans le conteneur, le dossier est vide.

Les phases suivantes ajoutent ici l'analyse de chaque sortie par son collecteur.
"""

import re

from tests.demarrage.conftest import REELLES


def reelles() -> list:
    return sorted(p for p in REELLES.glob("*.txt"))


def test_sorties_reelles_anonymes():
    for chemin in reelles():
        texte = chemin.read_text(encoding="utf-8")
        assert set(re.findall(r"/Users/([^/\s]+)", texte)) <= {"utilisateur", "Shared"}, chemin.name
        assert all(e.endswith("exemple.fr") for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texte)), chemin.name
