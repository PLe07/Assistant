"""Le superviseur : lance les modules activés, les surveille et les relance s'ils tombent.

    python superviseur.py

Toutes les 2 secondes, il relit reglages.json :
- pause globale → arrête tous les modules (le micro et l'écran se coupent aussitôt) ;
- module désactivé → arrêté ; module activé → lancé ;
- module tombé → relancé après 1 min, puis 5 min, puis toutes les 15 min.
Un module qui tourne 10 minutes sans tomber repart de zéro pour ce compte.
"""

import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from core import config, etat
from core.journal import LOGS, faire_tourner, journal

INTERVALLE = 2
DELAIS_RELANCE = [int(x) for x in os.getenv("ASSISTANT_TEST_DELAIS", "60,300,900").split(",")]
STABLE_APRES = 600
RELANCES_AVANT_ALERTE = 3

log = journal("superviseur", ecran=True)


@dataclass
class Suivi:
    nom: str
    processus: subprocess.Popen | None = None
    demarre_le: float = 0.0
    relances: int = 0
    prochain_essai: float = 0.0
    derniere_erreur: str = ""
    introuvable: bool = False
    alerte_envoyee: bool = False
    extras: dict = field(default_factory=dict)

    def vivant(self) -> bool:
        return self.processus is not None and self.processus.poll() is None


def _fichier_module(nom: str):
    simple, paquet = config.RACINE / "modules" / f"{nom}.py", config.RACINE / "modules" / nom / "__main__.py"
    return simple if simple.exists() else paquet if paquet.exists() else None


def _fichier_erreurs(nom: str):
    return LOGS / f"{nom}.erreurs.log"


def lancer(s: Suivi) -> None:
    if _fichier_module(s.nom) is None:
        if not s.introuvable:
            log.error("Module « %s » activé dans reglages.json mais introuvable dans modules/", s.nom)
        s.introuvable = True
        return
    s.introuvable = False
    erreurs = open(_fichier_erreurs(s.nom), "w", encoding="utf-8")  # sorties brutes, en cas de plantage dur
    s.processus = subprocess.Popen(
        [sys.executable, "-m", f"modules.{s.nom}"], cwd=config.RACINE,
        stdout=erreurs, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    erreurs.close()
    s.demarre_le = time.time()
    log.info("Module « %s » lancé (pid %d)", s.nom, s.processus.pid)


def arreter(s: Suivi, raison: str) -> None:
    if not s.vivant():
        s.processus = None
        return
    s.processus.terminate()  # demande polie (SIGTERM)
    try:
        s.processus.wait(timeout=5)
    except subprocess.TimeoutExpired:
        s.processus.kill()  # il n'a pas obéi : arrêt forcé
        s.processus.wait()
    log.info("Module « %s » arrêté (%s)", s.nom, raison)
    s.processus = None
    s.relances, s.prochain_essai, s.alerte_envoyee = 0, 0.0, False


def _derniere_ligne_utile(nom: str) -> str:
    try:
        lignes = [l.strip() for l in _fichier_erreurs(nom).read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return ""
    lignes = [l for l in lignes if l]
    return lignes[-1][:200] if lignes else ""


def constater_chute(s: Suivi) -> None:
    code = s.processus.returncode
    s.processus = None
    if time.time() - s.demarre_le >= STABLE_APRES:
        s.relances = 0
    s.relances += 1
    delai = DELAIS_RELANCE[min(s.relances - 1, len(DELAIS_RELANCE) - 1)]
    s.prochain_essai = time.time() + delai
    s.derniere_erreur = _derniere_ligne_utile(s.nom) or f"code de sortie {code}"
    log.warning("Module « %s » tombé (code %s) : %s · relance dans %d s", s.nom, code, s.derniere_erreur, delai)
    if s.relances >= RELANCES_AVANT_ALERTE and not s.alerte_envoyee:
        from core.notifications import notifier

        notifier("Assistant", f"Le module « {s.nom} » plante à répétition. Détails : python assistant.py journal",
                 module="superviseur")
        s.alerte_envoyee = True


def _capteur_coupe(nom: str, reglages: dict) -> str | None:
    """« micro » ou « ecran » si ce module utilise un capteur que tu as coupé."""
    capteur = config.CAPTEURS.get(nom)
    return capteur if capteur and reglages.get(f"pause_{capteur}") else None


def _voulu(nom: str, reglages: dict) -> bool:
    actif = reglages["modules"].get(nom, {}).get("actif", False)
    return actif and not reglages["pause_globale"] and not _capteur_coupe(nom, reglages)


def _statut(s: Suivi, reglages: dict) -> tuple:
    actif = reglages["modules"].get(s.nom, {}).get("actif", False)
    if s.vivant():
        return (s.nom, "actif", "", s.processus.pid, s.relances)
    if s.introuvable:
        return (s.nom, "introuvable", "fichier absent dans modules/", None, s.relances)
    if reglages["pause_globale"] and actif:
        return (s.nom, "en pause", "", None, s.relances)
    if actif and _capteur_coupe(s.nom, reglages):
        return (s.nom, "en pause", f"{_capteur_coupe(s.nom, reglages)} coupé", None, s.relances)
    if not actif:
        return (s.nom, "désactivé", "", None, s.relances)
    if s.prochain_essai > time.time():
        attente = int(s.prochain_essai - time.time())
        return (s.nom, "relance", f"dans {attente} s · {s.derniere_erreur}", None, s.relances)
    return (s.nom, "démarrage", "", None, s.relances)


def nettoyer_orphelins() -> None:
    """Après un arrêt brutal du superviseur, ses anciens modules ont pu rester en vie
    (micro, écran…). On les arrête avant de relancer quoi que ce soit."""
    for m in etat.modules():
        pid = m.get("pid")
        if not pid:
            continue
        commande = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
        if f"-m modules.{m['nom']}" not in commande:
            continue  # ce numéro appartient à un autre programme : on n'y touche pas
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode != 0:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
        log.warning("Module « %s » resté orphelin (pid %d) : arrêté", m["nom"], pid)


def main() -> int:
    config.DONNEES.mkdir(exist_ok=True)
    verrou = open(config.DONNEES / "superviseur.verrou", "w")
    try:
        fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Un superviseur tourne déjà. Pour voir son état : python assistant.py etat")
        return 1

    arret = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: arret.set())
    signal.signal(signal.SIGINT, lambda *_: arret.set())
    log.info("Superviseur démarré (pid %d)", os.getpid())
    nettoyer_orphelins()

    suivis: dict[str, Suivi] = {}
    erreurs_vues: list[str] = []
    pause_vue = None
    while not arret.is_set():
        reglages, erreurs = config.charger_avec_erreurs()
        if erreurs != erreurs_vues:
            for e in erreurs:
                log.error("Réglage : %s", e)
            erreurs_vues = erreurs
        pause = reglages["pause_globale"]
        if pause != pause_vue:
            log.info("⏸  PAUSE GLOBALE : tout est arrêté" if pause else "▶️  Actif")
            pause_vue = pause

        voulus = {n for n in reglages["modules"] if _voulu(n, reglages)}
        for nom in reglages["modules"]:
            suivis.setdefault(nom, Suivi(nom))

        for s in suivis.values():
            if s.processus is not None and not s.vivant():
                constater_chute(s)
            if s.nom not in voulus:
                coupe = _capteur_coupe(s.nom, reglages)
                arreter(s, "pause globale" if pause else f"{coupe} coupé" if coupe else "désactivé")
                s.introuvable = False
            elif not s.vivant() and time.time() >= s.prochain_essai:
                lancer(s)

        if faire_tourner():
            log.info("Journal archivé (assistant.log.1)")
        etat.maj_modules([_statut(s, reglages) for s in suivis.values()])
        etat.ecrire("superviseur_vivant", time.time())
        arret.wait(INTERVALLE)

    for s in suivis.values():
        arreter(s, "arrêt du superviseur")
    etat.maj_modules([])
    etat.effacer("superviseur_vivant")
    log.info("Superviseur arrêté")
    return 0


if __name__ == "__main__":
    sys.exit(main())
