"""Bout en bout, en vrai (§9.4) : un démon avec ses vrais capteurs, de vraies actions dans un bac à sable, puis
« corvees analyser --maintenant ».

- Fichiers : 5 fois, un « Devis_….pdf » est créé dans CorveesSandbox/Telechargements puis rangé dans
  CorveesSandbox/Documents/Devis. Le capteur watchdog le voit comme sur le Mac.
- zsh : des commandes répétées sont vraiment exécutées dans un sous-shell, avec un HISTFILE de test. Avec zsh
  (sur le Mac), c'est zsh qui écrit son historique ; sans zsh (le conteneur de construction), les lignes sont
  écrites au format de zsh.
- Applis (sur le Mac seulement, avec CORVEES_E2E_MAC=1) : TextEdit et Calculette ouvertes à tour de rôle, puis
  refermées.

Rien ne touche ton vrai dossier ni ton vrai historique : HOME pointe vers un dossier temporaire, nettoyé à la fin.
Toute l'activité tient en quelques secondes : les seuils « sur plusieurs jours » sont ramenés à 1 jour ici.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from modules.corvees import cli, config, daemon

COMMANDE = "cd ~/CorveesSandbox && ls -la"
SECRET = "mysql -u moi -p MotDePasseBidon42"


class DemonEnFil:
    """Un vrai démon (vrais capteurs) qui tourne dans un fil, comme sous le superviseur."""

    def __init__(self, reglages: dict, natif=None):
        self.reglages = reglages
        self.natif = natif
        self.pret = threading.Event()
        self.stop = threading.Event()
        self.erreur: BaseException | None = None
        self.journal: list[str] = []
        self.fil = threading.Thread(target=self._tourner, daemon=True)

    def _tourner(self) -> None:
        try:
            demon = daemon.Demon(self.reglages, self.natif, journal=self.journal.append)
            demon.base.ecrire("derniere_analyse", time.time())  # l'analyse, c'est la commande qui la lance
            for c in demon.capteurs:
                c.intervalle = min(c.intervalle, 0.3)  # pour ne pas attendre une minute le capteur zsh
            demon.demarrer_capteurs()
            demon.tour(time.time())
            self.capteurs = {c.nom: c.statut for c in demon.capteurs}
            self.pret.set()
            while not self.stop.is_set():
                demon.tour(time.time())
                time.sleep(0.1)
            demon.fermer()
        except BaseException as e:  # le test le signale
            self.erreur = e
            self.pret.set()

    def __enter__(self) -> DemonEnFil:
        self.fil.start()
        assert self.pret.wait(20), "le démon n'a pas démarré"
        assert self.erreur is None, self.erreur
        return self

    def __exit__(self, *_) -> None:
        self.stop.set()
        self.fil.join(20)


@pytest.fixture
def bac(tmp_path, monkeypatch):
    maison = tmp_path / "maison"
    sandbox = maison / "CorveesSandbox"
    (sandbox / "Telechargements").mkdir(parents=True)
    (sandbox / "Documents" / "Devis").mkdir(parents=True)
    historique = maison / ".zsh_history_test"
    historique.touch()
    monkeypatch.setenv("HOME", str(maison))
    reglages, erreurs = config.charger(
        {
            "dossier": str(tmp_path / "donnees"),
            "fichiers": {"dossiers": [str(sandbox)], "profondeur": 3},
            "shell": {"historique": str(historique)},
            "capteurs": {"navigateur": False},
            "notifications": {"vers_journal": True},
            "ia": {"actif": False},
            "detection": {
                "sequences": {"jours_min": 1},
                "fichiers": {"jours_min": 1},
                "shell": {"jours_min": 1},
                "ponts": {"jours_min": 1},
            },
        }
    )
    assert erreurs == []
    yield reglages, sandbox, historique
    shutil.rmtree(sandbox, ignore_errors=True)
    assert not sandbox.exists()


def ranger_des_devis(sandbox: Path, fois: int = 5) -> None:
    for i in range(1, fois + 1):
        fichier = sandbox / "Telechargements" / f"Devis_2026-10-0{i}.pdf"
        fichier.write_bytes(b"%PDF-1.4 devis de test\n")
        time.sleep(0.4)
        shutil.move(fichier, sandbox / "Documents" / "Devis" / fichier.name)
        time.sleep(0.4)


def taper_des_commandes(historique: Path, fois: int = 5) -> str:
    """Exécute vraiment les commandes dans un sous-shell, avec un historique de test. Renvoie « zsh » ou « bash »."""
    env = {**os.environ, "HISTFILE": str(historique)}
    zsh = shutil.which("zsh")
    for _ in range(fois):
        for ligne in (COMMANDE, SECRET):
            if zsh:
                script = (
                    "setopt EXTENDED_HISTORY INC_APPEND_HISTORY; HISTSIZE=100; SAVEHIST=100; "
                    f"print -s -- {_guillemets(ligne)}; fc -AI; " + (ligne if ligne == COMMANDE else "true")
                )
                subprocess.run([zsh, "-f", "-i", "-c", script], env=env, capture_output=True, timeout=30)
            else:
                if ligne == COMMANDE:  # la vraie commande (le faux mysql n'est jamais lancé)
                    subprocess.run(["bash", "-c", ligne], env=env, capture_output=True, timeout=30, check=True)
                with open(historique, "a", encoding="utf-8") as f:
                    f.write(f": {int(time.time())}:0;{ligne}\n")
            time.sleep(0.3)
    if zsh and COMMANDE not in historique.read_text(errors="replace"):  # zsh n'a pas écrit : on le dit
        pytest.fail("zsh n'a pas écrit son historique de test")
    return "zsh" if zsh else "bash"


def _guillemets(texte: str) -> str:
    return "'" + texte.replace("'", "'\\''") + "'"


def test_de_vraies_actions_remontent_jusqu_au_rapport(bac, capsys):
    reglages, sandbox, historique = bac
    with DemonEnFil(reglages) as demon:
        assert demon.capteurs["fichiers"] == "ok" and demon.capteurs["shell"] == "ok", demon.capteurs
        ranger_des_devis(sandbox)
        coquille = taper_des_commandes(historique)
        time.sleep(3)  # le capteur de fichiers garde 2 s pour apparier créations et suppressions
        ctx = cli.Contexte(reglages)
        assert ctx.demon_vivant()
        code = cli.main(["analyser", "--maintenant"], ctx)  # le démon vide d'abord son tampon
    assert demon.erreur is None, demon.erreur
    sortie = capsys.readouterr().out
    assert code == 0, sortie

    base = daemon.ouvrir(reglages)
    try:
        jetons = [e.token for e in base.evenements(0)]
        deplacement = "fmove:CorveesSandbox/Telechargements→CorveesSandbox/Documents/Devis [pdf, Devis_*]"
        assert jetons.count(deplacement) == 5, sorted(set(jetons))
        assert jetons.count(f"cmd:{COMMANDE}") == 5
        assert not any("MotDePasseBidon42" in t for t in jetons)  # caviardé avant d'être écrit
        candidats = {c["tokens"][0] for c in base.candidats()}
        assert deplacement in candidats or any(deplacement in c["tokens"] for c in base.candidats()), candidats
        assert f"cmd:{COMMANDE}" in candidats, candidats
    finally:
        base.fermer()
    assert "corvée(s) repérée(s)" in sortie and "Ranger les « Devis_*.pdf » dans Devis" in sortie
    brut = b"".join(p.read_bytes() for p in Path(reglages["dossier"]).rglob("*") if p.is_file())
    assert b"MotDePasseBidon42" not in brut  # ni dans la base, ni dans les propositions, ni dans le rapport
    print(sortie + f"(historique écrit par {coquille})")


@pytest.mark.skipif(
    sys.platform != "darwin" or os.getenv("CORVEES_E2E_MAC") != "1",
    reason="sur le Mac seulement, à la demande : CORVEES_E2E_MAC=1 (ouvre et referme TextEdit et Calculatrice)",
)
def test_sur_le_mac_les_applis_alternees(bac):  # pragma: no cover - lancé à la main sur le Mac
    """Comme le vrai démon : sa boucle sur le fil principal, qui laisse macOS tenir à jour l'appli au premier plan
    (natif.pomper), pendant qu'un autre fil ouvre TextEdit et Calculette à tour de rôle, puis les referme."""
    from modules.corvees.capteurs.natif import natif

    reglages, _, _ = bac
    mac = natif()
    journal: list[str] = []
    demon = daemon.Demon(reglages, mac, journal=journal.append)
    demon.base.ecrire("derniere_analyse", time.time())
    for c in demon.capteurs:
        c.intervalle = min(c.intervalle, 0.5)
    demon.demarrer_capteurs()

    def activite() -> None:
        try:
            for _ in range(3):
                for appli in ("TextEdit", "Calculator"):
                    subprocess.run(["open", "-a", appli], check=True)
                    time.sleep(3)
        finally:
            for appli in ("TextEdit", "Calculator"):
                subprocess.run(["osascript", "-e", f'quit app "{appli}"'], capture_output=True)

    fil = threading.Thread(target=activite)
    fil.start()
    try:
        while fil.is_alive():
            demon.tour_protege(time.time())
            mac.pomper(daemon.PAS_S)
        demon.tour_protege(time.time())
        demon.vider(time.time())
        jetons = [e.token for e in demon.base.evenements(0)]
        sante = {c.nom: (c.statut, c.detail) for c in demon.capteurs}
    finally:
        fil.join(30)
        demon.fermer()
    print(f"\nApplis vues : {[t for t in jetons if t.startswith('app:')]}\nSanté : {sante}")
    assert sante["apps"][0] == "ok", sante["apps"]  # la méthode principale, pas celle de secours
    assert jetons.count("app:TextEdit") >= 2, jetons
    calculette = sum(jetons.count(f"app:{nom}") for nom in ("Calculator", "Calculatrice", "Calculette"))
    assert calculette >= 2, jetons  # son nom dépend de la langue du Mac (« Calculatrice » en français)
    assert not any(t in jetons for t in ("app:WindowManager", "app:Dock")), jetons
