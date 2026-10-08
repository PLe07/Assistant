"""Le démon de bout en bout, sur le faux Mac (avec un vrai petit superviseur et ses vrais processus fils) : états
justes, une seule alerte et sa résolution, redémarrage sans doublon, intégrité, disque plein, verrou, instantané,
et la CLI `tableau` sur ce que le démon a enregistré."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tableau import caviardage, cli, config, daemon, systeme
from tableau.db import DisquePlein
from tableau.module import Pastille
from tableau.notifier import NotificateurMemoire
from tests import fabrique

SUPERVISEUR = (
    "import subprocess, sys, time\n"
    "fils = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)', '-m', 'modules.' + n])"
    " for n in sys.argv[1:]]\n"
    "time.sleep(3600)\n"
)


@dataclass
class Ecosysteme:
    maison: Path
    mac: Any
    demon: daemon.Demon
    notif: NotificateurMemoire
    t: list[float]
    mono: list[float]
    superviseur: subprocess.Popen[bytes]
    branchements: daemon.Branchements
    etats: dict[str, Any] = field(default_factory=dict)

    def tours(self, n: int = 1) -> dict[str, Any]:
        for _ in range(n):
            self.mac.vivre(self.t[0] - 5)  # les modules ont travaillé juste avant le tour
            self.etats = {e.id: e for e in self.demon.tour()}
            self.t[0] += 60
            self.mono[0] += 60
        return self.etats

    def redemarrer(self) -> None:
        self.demon.fermer()
        self.demon = daemon.Demon(self.demon.chemins, self.demon.reglages, self.branchements)


def lancer_superviseur() -> subprocess.Popen[bytes]:
    p = subprocess.Popen([sys.executable, "-c", SUPERVISEUR, "corvees", "demarrage", "trieur", "mails"],
                         start_new_session=True)  # fmt: skip
    fin = time.monotonic() + 15
    import psutil

    while time.monotonic() < fin:
        try:
            if len(psutil.Process(p.pid).children()) == 4:
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(0.05)
    return p


@pytest.fixture
def eco(maison: Path, horloge: Any) -> Iterator[Ecosysteme]:
    t = [horloge()]
    mono = [1000.0]
    mac = fabrique.faux_mac(maison, t[0])
    sup = lancer_superviseur()
    mac.launchd.agents["com.assistant.superviseur"]["pid"] = sup.pid
    chemins = config.Chemins(maison)
    reglages = config.charger(chemins.reglages)
    reglages.valeurs["installation"]["prefixe_label"] = fabrique.PREFIXE
    notif = NotificateurMemoire()
    b = daemon.Branchements(
        notificateur=notif, launchctl=mac.launchd, docker=mac.docker, healthz=lambda _p: (True, "HTTP 200"),
        mur=lambda: t[0], mono=lambda: mono[0], uid=501,
        charge_du_mac=lambda: {"cpu_pct": 50.0, "memoire_totale_mo": 8192.0}, surveiller_fichiers=False,
    )  # fmt: skip
    e = Ecosysteme(maison, mac, daemon.Demon(chemins, reglages, b), notif, t, mono, sup, b)
    try:
        yield e
    finally:
        e.demon.fermer()
        mac.fermer()
        try:
            os.killpg(sup.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        sup.wait(timeout=10)


def test_un_ecosysteme_sain_sans_fausse_alerte(eco: Ecosysteme) -> None:
    """30 minutes d'un écosystème qui travaille : tout est 🟢, aucune notification."""
    etats = eco.tours(30)
    pastilles = {i: str(e.pastille) for i, e in etats.items()}
    assert pastilles == {"assistant": "vert", "corvees": "vert", "nettoyeur": "vert", "trieur": "vert",
                         "bouclier": "vert", "quotidien": "vert", "ambiance": "gris", "n8n": "gris"}, (
        {i: e.phrase for i, e in etats.items()})  # fmt: skip
    assert eco.notif.envoyees == [] and eco.demon.erreurs_etapes == {}
    base = eco.demon.base
    assert base.valeur("SELECT COUNT(DISTINCT module) FROM echantillons") == 8
    assert len(base.etats_modules()) == 8 and base.lire_meta("battement_demon") is not None
    assert eco.demon.source.etat("trieur") is not None and eco.demon.dernier_tour_s < 2
    resume = json.loads(eco.demon.chemins.etat_json.read_text(encoding="utf-8"))
    assert resume["bandeau"] == "✅ Tout va bien" and len(resume["modules"]) == 8
    assert {"id", "nom", "pastille", "phrase"} == set(resume["modules"][0])
    assert oct(eco.demon.chemins.etat_json.stat().st_mode & 0o777) == "0o600"
    # L'instantané iPhone : écrit, sans rien de sensible, lisible par toi seul.
    page = eco.demon.chemins.icloud / "Etat.html"
    texte = page.read_text(encoding="utf-8")
    assert caviardage.contient_sensible(texte, (eco.demon.jeton,)) == []
    assert "✅ Tout va bien" in texte and str(eco.maison) not in texte and oct(page.stat().st_mode & 0o777) == "0o600"


def test_une_panne_une_alerte_puis_sa_resolution(eco: Ecosysteme) -> None:
    eco.tours(12)
    # Bouclier s'arrête (son LaunchAgent n'a plus de processus).
    agent = eco.mac.launchd.agents[f"com.{fabrique.PREFIXE}.bouclier"]
    pid = agent["pid"]
    agent["pid"] = None
    agent["statut"] = 1
    etats = eco.tours(10)
    assert etats["bouclier"].pastille == Pastille.ROUGE
    assert [t for _, t in eco.notif.envoyees] == [
        "🔴 Bouclier est arrêté alors qu'il devrait tourner. Tape « bouclier doctor » pour voir pourquoi."
    ]
    # Le démon redémarre pendant la panne : pas de seconde alerte.
    eco.redemarrer()
    eco.tours(20)
    assert len(eco.notif.envoyees) == 1
    # Bouclier repart : la résolution part une fois.
    agent["pid"] = pid
    agent["statut"] = 0
    etats = eco.tours(10)
    assert etats["bouclier"].pastille == Pastille.VERT
    assert [t for _, t in eco.notif.envoyees][1:] == ["✅ Bouclier tourne de nouveau."]
    eco.tours(10)
    assert len(eco.notif.envoyees) == 2


def test_code_change_puis_accepte(eco: Ecosysteme) -> None:
    eco.tours(2)
    (eco.mac.assistant / "modules" / "trieur" / "config.py").write_text("SEUIL = 0.10\n")
    eco.demon.echeancier.forcer("integrite")
    etats = eco.tours(5)
    assert etats["trieur"].integrite == "changé"
    assert any(p.genre == "integrite" for p in etats["trieur"].problemes)
    assert any("Le code de Trieur a changé" in t for _, t in eco.notif.envoyees)
    message = eco.demon.source.nouvelle_reference("trieur")
    assert message.startswith("C'est noté")
    eco.demon.echeancier.forcer("integrite")
    etats = eco.tours(5)
    assert etats["trieur"].integrite == "référence" and not etats["trieur"].problemes
    assert not any("Le code de Trieur est de nouveau" in t for _, t in eco.notif.envoyees)  # accepté : sans message


def test_disque_plein_puis_retour(eco: Ecosysteme, monkeypatch: pytest.MonkeyPatch) -> None:
    eco.tours(1)
    avant = eco.demon.etats

    def plein(*_a: Any, **_k: Any) -> Any:
        raise DisquePlein("database or disk is full")

    monkeypatch.setattr(eco.demon.base, "ecrire_meta", plein)
    assert eco.demon.tour() is avant and eco.demon.disque_plein
    monkeypatch.undo()
    eco.tours(1)
    assert not eco.demon.disque_plein


def test_une_etape_en_panne_n_arrete_pas_le_tour(eco: Ecosysteme, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eco.demon, "controler_integrite", lambda _m: 1 / 0)
    etats = eco.tours(2)
    assert len(etats) == 8 and "ZeroDivisionError" in eco.demon.erreurs_etapes["integrite"]
    monkeypatch.setattr(eco.demon, "observer", lambda _m: 1 / 0)
    assert eco.demon.tour() == list(etats.values())


def test_verrou_une_seule_instance(tmp_path: Path) -> None:
    v1 = daemon.Verrou(tmp_path / "v")
    v1.prendre()
    v2 = daemon.Verrou(tmp_path / "v")
    with pytest.raises(daemon.DejaLance):
        v2.prendre()
    assert (tmp_path / "v").read_text() == str(os.getpid())
    v1.rendre()
    v2.prendre()
    v2.rendre()
    v2.rendre()


def test_la_cli_sur_ce_que_le_demon_a_ecrit(eco: Ecosysteme, capsys: pytest.CaptureFixture[str]) -> None:
    eco.tours(3)
    eco.demon.base.ecrire_meta("battement_demon", str(time.time()))
    (eco.maison / "Library" / "Application Support" / "TableauDeBord" / "reglages.toml").write_text(
        f'[installation]\nprefixe_label = "{fabrique.PREFIXE}"\n', encoding="utf-8"
    )

    def lancer(*args: str) -> tuple[int, str]:
        code = cli.main(list(args))
        return code, capsys.readouterr().out

    code, sortie = lancer("etat")
    assert code == 0 and sortie.startswith("✅ Tout va bien") and "🟢 Bouclier :" in sortie
    assert "⚪ Ambiance : Pas installé" in sortie
    assert lancer()[1] == sortie  # sans argument : l'état
    _, sortie = lancer("module", "bouclier")
    assert sortie.startswith("🛡️ Bouclier — 🟢 tout va bien") and "Pour aller plus loin : bouclier doctor" in sortie
    _, sortie = lancer("module", "Trieur")
    assert "Trieur" in sortie
    assert "Module « zut » inconnu" in lancer("module", "zut")[1]
    _, sortie = lancer("credits")
    assert sortie.startswith("Crédits Claude · 2026-10")
    _, sortie = lancer("integrite")
    assert "Intégrité du code" in sortie and "✓ Trieur : conforme" in sortie
    (eco.mac.assistant / "trieur.py").write_text("# changé\n")
    eco.demon.echeancier.forcer("integrite")
    eco.tours(1)
    _, sortie = lancer("integrite")
    assert "⚠️ Trieur : changé" in sortie and "tableau integrite accepter trieur" in sortie
    _, sortie = lancer("integrite", "accepter", "trieur")
    assert sortie.startswith("C'est noté : le code actuel de Trieur devient la référence")
    assert "inconnu" in lancer("integrite", "accepter", "zut")[1]
    assert lancer("sourdine", "1h")[1].startswith("Alertes en sourdine jusqu'à")
    assert lancer("sourdine", "fin")[1] == "Sourdine levée.\n"
    assert cli.main(["sourdine", "demain"]) == 2
    _, sortie = lancer("rapport")
    assert sortie.startswith("Rapport des 7 derniers jours : ~/Library/Application Support/TableauDeBord/rapports/")
    eco.demon.base.ecrire_meta("battement_demon", str(time.time()))  # la CLI lit l'heure réelle
    _, sortie = lancer("doctor")
    for morceau in ("Tableau de bord 1.0.0", "Démon : ✅", "Page locale : http://127.0.0.1:", "droits 600",
                    "Réglages : OK", "Registre : OK", "Modules découverts (8)", "adaptateur bouclier",
                    "Commandes de lecture", "Instantané iPhone : écrit"):  # fmt: skip
        assert morceau in sortie, morceau
    assert config.jeton(eco.demon.chemins) not in sortie
    _, sortie = lancer("ouvrir")
    assert f"http://127.0.0.1:{config.PORT_DEFAUT}/?t=" in sortie
    _, sortie = lancer("diagnostic", "zut")
    assert "inconnu" in sortie


def test_cli_demon_arrete_et_registre_casse(maison: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["etat"]) == 0
    sortie = capsys.readouterr().out
    assert "le démon n'a encore jamais tourné" in sortie and "Aucun module observé" in sortie
    c = config.chemins()
    c.registre.write_text("[[module]\ncassé", encoding="utf-8")
    assert cli.main(["doctor"]) == 0
    sortie = capsys.readouterr().out
    assert "Démon : ❌" in sortie and "Registre : " in sortie and "Registre : OK" not in sortie
    s = cli.source(c)
    s.base.ecrire_meta("battement_demon", str(time.time() - 3600))
    assert "pas de tour depuis 1 h" in cli.demon_vivant(s)[1]
    s.base.fermer()


def test_diagnostic_depuis_le_terminal(eco: Ecosysteme, monkeypatch: pytest.MonkeyPatch) -> None:
    vus: list[Any] = []

    def espion(commande: list[str], dossier: Path, demande: Any, delai: float = 120) -> systeme.Resultat:
        vus.append((commande, dossier, demande))
        return systeme.Resultat(0, "tout va bien pour alice@example.com\n")

    monkeypatch.setattr(systeme, "executer_diagnostic", espion)
    s = cli.source(eco.demon.chemins)
    defn = s.defs["bouclier"]
    dossier = defn.chemin(defn.dossier_projet, eco.maison)
    assert dossier is not None
    dossier.mkdir(parents=True, exist_ok=True)
    assert cli.diagnostic(s, "bouclier") == "tout va bien pour [e-mail]"
    assert vus == [(defn.commande_diagnostic, dossier, systeme.DemandeExplicite("terminal", "bouclier"))]
    s.base.fermer()


def test_lancer_le_demon_pour_un_tour(maison: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`tableau demon --sans-barre` : verrou, page locale, un tour, arrêt propre (journal écrit, verrou rendu)."""
    origine = daemon.Demon.boucle
    monkeypatch.setattr(daemon.Demon, "boucle", lambda self, tours_max=None: origine(self, 1))
    monkeypatch.setenv("TABLEAU_NOTIFICATIONS", "coupees")
    assert cli.main(["demon", "--sans-barre"]) == 0
    c = config.chemins()
    journal = (c.logs / "tableau.log").read_text(encoding="utf-8")
    assert "démarré (version 1.0.0)" in journal and "arrêté proprement" in journal
    assert config.jeton(c) not in journal
    v = daemon.Verrou(c.verrou)
    v.prendre()  # rendu à l'arrêt
    assert daemon.lancer(barre=False) == 0  # un autre « démon » tient le verrou : il s'arrête tout de suite
    v.rendre()


def test_cout_reel_option(eco: Ecosysteme, monkeypatch: pytest.MonkeyPatch) -> None:
    from tableau.analyse import credits_reels

    eco.demon.reglages.valeurs["credits"]["api_admin"] = True
    monkeypatch.setattr(credits_reels, "lire_cle", lambda: None)
    eco.tours(1)
    assert eco.demon.base.lire_meta("credits_reels_motif") == "clé Admin absente du trousseau"
    monkeypatch.setattr(credits_reels, "lire_cle", lambda: "sk-ant-admin-test")

    def indisponible(_cle: str, _m: float) -> float:
        raise credits_reels.CoutReelIndisponible("HTTP 401")

    monkeypatch.setattr(credits_reels, "cout_du_mois", indisponible)
    eco.demon.echeancier.forcer("credits_reels")
    eco.tours(1)
    assert eco.demon.base.lire_meta("credits_reels_motif") == "HTTP 401"
    monkeypatch.setattr(credits_reels, "cout_du_mois", lambda _c, _m: 2.5)
    eco.demon.echeancier.forcer("credits_reels")
    eco.tours(1)
    assert eco.demon.base.lire_meta("credits_reels_motif") is None
    assert '"usd": 2.5' in (eco.demon.base.lire_meta("credits_reels") or "")
    from tableau import vues

    assert vues.vue_credits(eco.demon.source)["reel_usd"] == 2.5


def test_lancer_avec_la_barre_des_menus(maison: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sur le Mac : les tours dans un fil, l'icône dans le fil principal ; quitter l'icône arrête tout proprement."""
    from tableau import barre_menus

    vus: list[str] = []

    def fausse_barre(source: Any, adresse: str, arret: Any) -> None:
        vus.append(adresse)
        time.sleep(0.2)

    monkeypatch.setattr(systeme, "est_un_mac", lambda: True)
    monkeypatch.setattr(barre_menus, "lancer", fausse_barre)
    monkeypatch.setenv("TABLEAU_NOTIFICATIONS", "coupees")
    assert daemon.lancer() == 0
    assert len(vus) == 1 and vus[0].startswith("http://127.0.0.1:") and "?t=" in vus[0]
    journal = (config.chemins().logs / "tableau.log").read_text(encoding="utf-8")
    assert "arrêté proprement" in journal


def test_sans_rumps_le_demon_tourne_quand_meme(maison: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sur un Mac où l'icône est impossible (rumps absent) : pas de boucle de plantages, le démon continue."""
    from tableau import barre_menus

    def sans_rumps(*_a: Any) -> None:
        raise ImportError("No module named 'rumps'")

    tours: list[int] = []
    origine = daemon.Demon.tour

    def un_tour(self: daemon.Demon) -> Any:
        tours.append(1)
        etats = origine(self)
        self.arret.set()  # un tour suffit
        return etats

    monkeypatch.setattr(systeme, "est_un_mac", lambda: True)
    monkeypatch.setattr(barre_menus, "lancer", sans_rumps)
    monkeypatch.setattr(daemon.Demon, "tour", un_tour)
    monkeypatch.setenv("TABLEAU_NOTIFICATIONS", "coupees")
    assert daemon.lancer() == 0 and tours == [1]
    journal = (config.chemins().logs / "tableau.log").read_text(encoding="utf-8")
    assert "icône de la barre des menus impossible (ImportError)" in journal and "arrêté proprement" in journal
