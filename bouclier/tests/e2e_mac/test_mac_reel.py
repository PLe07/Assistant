"""Bout en bout réels, sur ton Mac seulement et à la demande (ACTIONS_HUMAINES.md) :

    .venv/bin/python -m pytest -m reel tests/e2e_mac -s

- Apple Vision lit une capture d'écran (en local) ;
- les actions rapides installées sont des paquets Automator valides (`plutil -lint`) ;
- les 2 raccourcis se signent (`shortcuts sign`, compte iCloud) ;
- Gmail : drapeaux et libellés identiques avant et après l'analyse des 3 derniers messages et la lecture des
  en-têtes (EXAMINE, BODY.PEEK) ; aucune notification envoyée, une base jetable.
Rien n'est laissé derrière : tout est écrit dans un dossier temporaire.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from bouclier import db, gmail, surveillance_gmail
from bouclier.arnaque import analyse, ocr
from bouclier.config import Chemins, charger_ou_defauts
from bouclier.installation import image_de_test
from bouclier.notifier import Notifieur
from bouclier.raccourcis import actions_rapides, generer
from bouclier.systeme import Resultat, Systeme

pytestmark = [
    pytest.mark.reel,
    pytest.mark.skipif(platform.system() != "Darwin", reason="sur ton Mac seulement"),
]

VRAIE_MAISON = Path.home()


def test_vision_lit_une_capture(tmp_path: Path) -> None:
    lire = ocr.lecteur(True)
    assert lire is not None, "Apple Vision introuvable (pyobjc-framework-Vision) : relance ./install.sh"
    capture = tmp_path / "capture.png"
    assert image_de_test(capture)
    texte, confiance = lire(capture)
    print(f"\nVision : « {texte} » (confiance {confiance:.2f})")
    assert "Bouclier" in texte and "test" in texte


def test_actions_rapides_installees_valides() -> None:
    services = Chemins(VRAIE_MAISON).services
    etat = actions_rapides.etat(services)
    if not any(etat.values()):
        pytest.skip("actions rapides pas encore installées : lance ./install.sh")
    for action in actions_rapides.ACTIONS:
        paquet = services / f"{action.fichier}.workflow" / "Contents"
        for f in ("Info.plist", "document.wflow"):
            r = subprocess.run(["plutil", "-lint", str(paquet / f)], capture_output=True, text=True, timeout=30)
            assert r.returncode == 0, r.stdout + r.stderr


def test_raccourcis_signes(tmp_path: Path) -> None:
    if not shutil.which("shortcuts"):
        pytest.skip("commande shortcuts absente (macOS 12 ou plus)")
    for fichier in generer.ecrire(tmp_path):
        assert generer.plutil_lint(fichier)[0]
        ok, message = generer.signer(fichier, tmp_path / fichier.name.replace(".non-signé", ""))
        assert ok, f"{fichier.name} : {message} (connecte-toi à iCloud dans Réglages Système)"


def test_gmail_reel_lecture_seule(tmp_path: Path) -> None:
    fichier = Chemins(VRAIE_MAISON).config
    adresse = ""
    if fichier.exists():
        with fichier.open("rb") as f:
            adresse = str(tomllib.load(f).get("gmail", {}).get("adresse", ""))
    if not adresse:
        pytest.skip("Gmail pas relié (ACTIONS_HUMAINES.md)")
    reglages = charger_ou_defauts()[0]
    reglages["gmail"]["adresse"] = adresse
    systeme = Systeme()
    if not gmail.etat(reglages, systeme)[0]:
        pytest.skip("mot de passe d'application absent du trousseau : bouclier gmail-relier")
    base = db.ouvrir(tmp_path / "jetable.db")
    muet = Systeme(lambda a, e, d: Resultat(0, ""), mac=True)  # aucune notification pendant le test
    notifieur = Notifieur(base, muet, reglages)
    with gmail.ouvrir(reglages, systeme) as lecteur:
        lecteur.examiner("INBOX")
        uids = lecteur.uids_depuis(0)
        assert uids, "boîte de réception vide : rien à vérifier"
        temoins = uids[-20:]
        avant = lecteur.drapeaux(temoins)
        assert surveillance_gmail.relever(lecteur, base, analyse.Outils(reglages, base), notifieur).premier_passage
        with base.transaction() as cx:  # on fait comme si les 3 derniers messages venaient d'arriver
            cx.execute("UPDATE gmail SET dernier_uid = ?", (temoins[-4] if len(temoins) > 3 else 0,))
        r = surveillance_gmail.relever(lecteur, base, analyse.Outils(reglages, base), notifieur)
        entetes = list(lecteur.entetes(temoins))
        apres = lecteur.drapeaux(temoins)
    print(f"\nGmail : {r.analyses} message(s) analysé(s), {len(entetes)} en-têtes lus, {len(avant)} témoins")
    assert r.analyses >= 1 and len(entetes) == len(temoins)
    assert apres == avant, "drapeaux ou libellés modifiés"
    base.fermer()
