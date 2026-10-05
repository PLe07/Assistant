"""Les sorties réelles capturées sur le Mac (capturer.py) : anonymes, et comprises par chaque analyseur.

Dans le conteneur de construction, le dossier est vide (rien n'est versionné) : ces vérifications tournent pour de
vrai sur le Mac, après « python -m modules.demarrage.capturer ».
"""

import re

from modules.demarrage.collecteurs import launchd_etat as le
from modules.demarrage.signatures import analyser_codesign, analyser_mdls
from tests.demarrage.conftest import REELLES


def reelle(nom: str) -> str | None:
    chemin = REELLES / f"{nom}.txt"
    return chemin.read_text(encoding="utf-8") if chemin.exists() else None


def test_sorties_reelles_anonymes():
    for chemin in sorted(REELLES.glob("*.txt")):
        texte = chemin.read_text(encoding="utf-8")
        assert set(re.findall(r"/Users/([^/\s]+)", texte)) <= {"utilisateur", "Shared"}, chemin.name
        assert all(e.endswith("exemple.fr") for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texte)), chemin.name


def test_launchctl_reel():
    if (texte := reelle("launchctl_list")) is not None:
        services = le.analyser_list(texte)
        assert len(services) > 20 and any(label.startswith("com.apple.") for label in services)
    if (texte := reelle("launchctl_print_gui")) is not None:
        assert len(le.analyser_print_domaine(texte)) > 20
    if (texte := reelle("launchctl_print_disabled")) is not None:
        assert le.analyser_desactives(texte) or "disabled services = {\n}" in texte
    if (texte := reelle("launchctl_print_service")) is not None:
        assert le.analyser_print_service(texte).programme


def test_signatures_reelles():
    if (texte := reelle("codesign_apple")) is not None:
        assert analyser_codesign(0, texte).etat == "apple"
    if (texte := reelle("codesign_tiers")) is not None:
        assert analyser_codesign(0, texte).etat in ("developpeur", "app_store", "adhoc")
    if (texte := reelle("mdls_date")) is not None and texte.strip() != "(null)":
        assert analyser_mdls(texte) is not None
