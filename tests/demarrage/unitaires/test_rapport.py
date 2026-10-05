import os
import re
import stat
import time

import pytest

from modules.demarrage import rapport
from modules.demarrage.analyse import Bilan, analyser
from modules.demarrage.db import Base
from modules.demarrage.modele import Fiche, Inventaire
from tests.demarrage.faux_mac.demo import fabriquer


@pytest.fixture(autouse=True)
def paris(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def test_rapport_complet_sur_le_faux_mac(tmp_path):
    chemin = fabriquer(tmp_path / "travail", tmp_path / "rapport.html")
    html = chemin.read_text(encoding="utf-8")
    assert stat.S_IMODE(os.stat(chemin).st_mode) == 0o600
    assert html.startswith("<!doctype html>") and '<html lang="fr">' in html
    assert "se lancent tout seuls (sans compter les 18 de macOS)" in html and "te coûtent vraiment" in html
    assert "Si tu coupes les" in html and "mise en veille débloquée" in html
    for nom in ("Docker (réseau et socket)", "Adobe Creative Cloud", "Google Updater (Keystone)", "com.mystere.agent"):
        assert nom in html
    assert (
        html.index("Docker (réseau et socket)") < html.index("Adobe Creative Cloud") < html.index("com.mystere.agent")
    )
    assert (
        "demarrage desactiver" in html
        and "demarrage restaurer" in html
        and "Ne le supprime pas à l&#x27;aveugle" in html
    )
    assert "À taper toi-même" in html and "Pour annuler" in html
    assert html.count('class="point s-calme"') >= 2 and "Voir les chiffres" in html and "pas calme en 5 min" in html
    assert "prefers-color-scheme:dark" in html and 'data-theme="dark"' in html
    assert "nvm (Node.js)" in html and "412 ms" in html
    assert not re.search(r"https?://", html)  # rien chargé d'Internet
    assert "<script>" in html and html.count("<script") == 1


def bilan_minimal(tmp_path, reglages, fiches):
    b = Base(tmp_path / "d.db")
    inv = Inventaire(ts=1_791_176_000.0, fiches=fiches)
    bilan = analyser(inv, b, reglages, inv.ts)
    b.fermer()
    return bilan


def test_echappement_et_resume_sans_mesure(tmp_path, reglages):
    piege = Fiche(id="p", label="<script>alert(1)</script>", source="agent_utilisateur", programme="/opt/<b>",
                  programme_existe=True, signature="developpeur", editeur="É & Cie", actif=True)  # fmt: skip
    bilan = bilan_minimal(tmp_path, reglages, [piege])
    html = rapport.construire(bilan, reglages, [], [], 501)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "É &amp; Cie" in html
    phrase, gain = rapport.resume(bilan, reglages)
    assert phrase.startswith("1 élément se lance tout seul.") and "pas encore mesuré" in phrase
    assert gain == "Rien à couper : aucun élément 💤 ni 👻."
    assert "Pas encore d'ouverture de session observée" in html and "Pas encore mesuré." in html


def test_resume_quand_rien_ne_coute(tmp_path, reglages):
    b = Base(tmp_path / "d.db")
    f = Fiche(id="a", label="com.x", source="agent_utilisateur", programme="/opt/x", programme_existe=True,
              signature="developpeur", editeur="X", actif=True)  # fmt: skip
    b.enregistrer_releve(1.0, "mesure", 1.0, {"a": {"cpu_s": 0.0, "rss_ko": 1024, "puissance": None, "veille": False}})
    bilan = analyser(Inventaire(ts=2.0, fiches=[f]), b, reglages, 2.0)
    b.fermer()
    assert "ton démarrage est sain" in rapport.resume(bilan, reglages)[0]


def test_courbe():
    assert "prochaine connexion" in rapport.courbe([])
    assert "à partir de la deuxième" in rapport.courbe([{"connexion": 100.0, "demarrage_s": 50.0, "calme_s": 30.0}])
    sessions = [{"connexion": 1e9 + i * 86400, "demarrage_s": 40.0 + i, "calme_s": None if i == 3 else 20.0 + i}
                for i in range(6)]  # fmt: skip
    svg = rapport.courbe(sessions)
    assert svg.count('class="zone"') == 6 and svg.count('class="point s-calme"') == 5
    assert svg.count('class="serie s-calme"') == 2  # le trou coupe la ligne
    assert ">0 s<" in svg and "min" not in svg.split("<svg")[1].split("</svg>")[0].split('class="axe"')[1][:40]
    long = rapport.courbe([{"connexion": 1e9, "demarrage_s": 90.0, "calme_s": 400.0},
                           {"connexion": 1e9 + 86400, "demarrage_s": 80.0, "calme_s": 300.0}])  # fmt: skip
    assert ">0<" in long and " min<" in long


def test_formats():
    assert rapport.nombre(1234567.891, 2) == "1 234 567,89"
    assert rapport.memoire(None) == "—" and rapport.memoire(512) == "512 Mo" and rapport.memoire(1536) == "1,5 Go"
    assert rapport.secondes(None) == "—" and rapport.secondes(4.25) == "4,2 s" and rapport.secondes(45) == "45 s"
    assert rapport.secondes(150) == "2,5 min"
    maintenant = 1_791_176_000.0
    assert (
        rapport.il_y_a(None, maintenant).startswith("jamais")
        and rapport.il_y_a(maintenant, maintenant) == "aujourd'hui"
    )
    assert (
        rapport.il_y_a(maintenant - 86400, maintenant) == "hier"
        and rapport.il_y_a(maintenant - 5 * 86400, maintenant) == "il y a 5 jours"
    )
    assert rapport.date_courte(maintenant) == "lun 5/10" and rapport.date_longue(maintenant) == "5 octobre 2026 à 06:53"


def test_ecrire_remplace(tmp_path):
    chemin = tmp_path / "x" / "rapport.html"
    rapport.ecrire(chemin, "a")
    rapport.ecrire(chemin, "b")
    assert chemin.read_text() == "b" and not list(chemin.parent.glob("*.tmp"))
    assert isinstance(Bilan, type)
