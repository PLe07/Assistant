"""Le démon : fait tourner les capteurs, écrit par paquets, analyse chaque soir. Lancé et relancé par le superviseur
de l'Assistant (python -m modules.corvees), comme les autres modules en fond.

Une boucle courte (une demi-seconde) : chaque capteur est relevé à son rythme, les événements sont écrits toutes les
30 secondes, un battement de cœur est noté chaque minute. L'analyse a lieu à 21 h ; si le Mac dormait, au réveil
suivant (branché, ou batterie au-dessus de 30 %). « corvees pause » coupe tous les capteurs dans la seconde.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from modules.corvees import config, privacy
from modules.corvees.capteurs import construire
from modules.corvees.capteurs.base import Capteur
from modules.corvees.db import Base, DisquePlein, Evenement
from modules.corvees.detection.moteur import analyser
from modules.corvees.normalize import debut_du_jour, instant_du_jour, veille

PAS_S = 0.5  # la boucle
BATTEMENT_S = 60
RELANCE_MAX_S = 300  # un capteur qui plante attend au plus 5 minutes avant d'être relancé
RACINE = Path(__file__).resolve().parents[2]  # le dossier de l'Assistant (pour lancer l'analyse à part)
ANALYSE_MAX_S = 45 * 60  # Claude compris (3 essais, et l'attente d'une pause après un quota)
A_EFFACER = [
    "analyse.log",
    "corvees.db",
    "corvees.db-*",
    "corvees.db.corrompue-*",
    "sel",
    "propositions",
    "sauvegardes",
    "rapport.html",
    "notifications.log",
    "alias.zsh",
    "installations.json",
]
TAMPON_MAX = 20000  # au-delà (disque plein longtemps), les plus anciens événements en attente sont abandonnés


def occupee(e: Exception) -> bool:
    """La base est verrouillée par un autre programme (la commande) : passager, rien n'est abîmé."""
    texte = str(e).lower()
    return isinstance(e, sqlite3.OperationalError) and ("locked" in texte or "busy" in texte)


class Demon:
    def __init__(
        self,
        reglages: dict[str, Any] | None = None,
        natif: Any = None,
        journal: Callable[[str], None] | None = None,
        capteurs: list[Capteur] | None = None,
        apres_analyse: Callable[[Demon, list[dict[str, Any]], float], None] | None = None,
        isolee: bool = False,
    ):
        self.reglages = reglages or config.charger()[0]
        self.dossier = config.dossier_donnees(self.reglages)
        brut = journal or (lambda message: None)
        self.journal = lambda message: brut(privacy.caviarder(message))  # un message d'erreur peut citer un secret
        self.gardien = privacy.Gardien(self.reglages, privacy.sel(self.dossier))
        self.base = Base(self.dossier / "corvees.db", self.gardien, journal=self.journal)
        self.natif = natif
        self.tampon: list[Evenement] = []
        self.session = int(self.base.lire("session", 0) or 0)
        self.dernier_evt = 0.0
        self.dernier_vidage = 0.0
        self.dernier_battement = 0.0
        self.en_pause = False
        self.relance: dict[str, float] = {}  # capteur → instant avant lequel on ne le relance pas
        self.apres_analyse = apres_analyse
        self.capteurs_construits = capteurs is None
        self.isolee = isolee
        self.analyse: subprocess.Popen[str] | None = None
        self.analyse_debut = 0.0
        self.capteurs = (
            capteurs
            if capteurs is not None
            else construire(
                self.reglages, self.recevoir, self.base, natif, self.gardien.empreinte, self.gardien.chemin_exclu
            )
        )
        self.deja_dit: set[str] = set()

    # --- les événements -------------------------------------------------------------------------------------

    def recevoir(self, evt: Evenement) -> None:
        """La sortie de tous les capteurs : on numérote la session (coupée après 10 min sans action)."""
        pause = float(self.reglages["sessions"]["inactivite_min"]) * 60
        if evt.kind == "inactif" or (self.dernier_evt and evt.ts - self.dernier_evt > pause):
            self.session += 1
        if evt.kind != "inactif":
            self.dernier_evt = max(self.dernier_evt, evt.ts)
        evt.session_id = self.session
        self.tampon.append(evt)
        if len(self.tampon) > TAMPON_MAX:
            del self.tampon[: len(self.tampon) - TAMPON_MAX]

    def vider(self, maintenant: float) -> int:
        """Écrit le paquet en attente (un seul accès disque). Disque plein : rien ne tombe, on le dit une fois."""
        self.dernier_vidage = maintenant
        if not self.tampon:
            return 0
        paquet, self.tampon = self.tampon, []
        try:
            n = self.base.ajouter(paquet)
        except DisquePlein as e:
            self._dire_une_fois("disque", f"Disque plein : {len(paquet)} événements abandonnés ({e})")
            return 0
        except sqlite3.DatabaseError as e:
            if occupee(e):  # la commande écrit en même temps : rien n'est abîmé, le paquet attend le prochain essai
                self.tampon = (paquet + self.tampon)[-TAMPON_MAX:]
                self._dire_une_fois("occupee", f"Base occupée ({e}) : les événements attendent le prochain essai")
                return 0
            # la base s'est abîmée en cours de route : on la reconstruit
            self.journal(f"Base illisible en écrivant ({e}) : reconstruction")
            self.base.fermer()
            self.base = Base(self.dossier / "corvees.db", self.gardien, journal=self.journal)
            n = self.base.ajouter(paquet)
        self.deja_dit.discard("disque")
        self.deja_dit.discard("occupee")
        self.base.ecrire("session", self.session)
        return n

    def _dire_une_fois(self, cle: str, message: str) -> None:
        if cle not in self.deja_dit:
            self.deja_dit.add(cle)
            self.journal(message)

    # --- les capteurs ---------------------------------------------------------------------------------------

    def demarrer_capteurs(self) -> None:
        for c in self.capteurs:
            try:
                c.demarrer()
            except Exception as e:
                c.degrader(privacy.caviarder(f"démarrage impossible ({e.__class__.__name__} : {e})"))
                self.relance[c.nom] = 0.0

    def arreter_capteurs(self) -> None:
        for c in self.capteurs:
            try:
                c.arreter()
            except Exception as e:
                self.journal(f"Arrêt du capteur {c.nom} : {e}")

    def relever(self, maintenant: float) -> None:
        for c in self.capteurs:
            if c.statut == "désactivé" or maintenant < self.relance.get(c.nom, 0.0):
                continue
            if maintenant - c.dernier_releve < c.intervalle:
                continue
            try:
                if c.erreurs:  # il avait planté : on le relance proprement
                    c.arreter()
                    c.demarrer()
                c.relever(maintenant)
                c.dernier_releve = maintenant
                if c.erreurs:
                    self.journal(f"Capteur {c.nom} relancé")
                c.erreurs = 0
            except Exception as e:
                c.erreurs += 1
                attente = min(RELANCE_MAX_S, 2**c.erreurs)
                self.relance[c.nom] = maintenant + attente
                panne = f"{e.__class__.__name__} : {e}"
                c.degrader(privacy.caviarder(f"a planté ({panne}) ; nouvel essai dans {attente} s"))
                self.journal(f"Capteur {c.nom} : {e.__class__.__name__} : {e} (nouvel essai dans {attente} s)")

    # --- la pause -------------------------------------------------------------------------------------------

    def pause_demandee(self, maintenant: float) -> bool:
        etat = self.base.lire("pause")
        if not etat:
            return False
        jusqua = etat.get("jusqua")
        if jusqua is not None and maintenant >= float(jusqua):
            self.base.effacer("pause")
            return False
        return True

    # --- le battement, la santé, l'entretien ----------------------------------------------------------------

    def battre(self, maintenant: float) -> None:
        self.dernier_battement = maintenant
        self.base.ecrire("battement", maintenant)
        self.base.ecrire("sante", [c.sante() for c in self.capteurs])

    def entretenir(self, maintenant: float) -> None:
        """Une fois par jour : les événements de plus de 30 jours deviennent des comptes par jour."""
        jour = debut_du_jour(maintenant)
        if float(self.base.lire("derniere_purge", 0) or 0) >= jour:
            return
        n = self.base.purger(int(self.reglages["retention_jours"]), maintenant)
        self.base.ecrire("derniere_purge", maintenant)
        if n:
            self.journal(f"Purge : {n} événements de plus de {self.reglages['retention_jours']} jours résumés")

    # --- l'analyse ------------------------------------------------------------------------------------------

    def alimentation_ok(self) -> bool:
        if self.natif is None:
            return True
        secteur, pourcentage = self.natif.alimentation()
        return secteur or pourcentage is None or pourcentage > self.reglages["analyse"]["batterie_min"]

    def doit_analyser(self, maintenant: float) -> bool:
        """Le dernier « 21 h » passé n'a pas encore eu son analyse (Mac endormi : elle a lieu au réveil)."""
        heure = self.reglages["analyse"]["heure"]
        cible = instant_du_jour(maintenant, heure)
        if maintenant < cible:
            cible = instant_du_jour(veille(maintenant), heure)
        return float(self.base.lire("derniere_analyse", 0) or 0) < cible and self.alimentation_ok()

    def analyser(self, maintenant: float) -> list[dict[str, Any]]:
        self.vider(maintenant)
        if self.isolee:
            self.lancer_analyse(maintenant)
            return []
        candidats = analyser_base(self.base, self.reglages, maintenant, self.journal)
        if self.apres_analyse:
            try:
                self.apres_analyse(self, candidats, maintenant)
            except Exception as e:  # l'IA, le rapport ou la notification ne font jamais tomber le démon
                self.journal(f"Après l'analyse : {e.__class__.__name__} : {e}")
        return candidats

    # --- un tour de boucle ----------------------------------------------------------------------------------

    def tour_protege(self, maintenant: float) -> None:
        """Un tour ; si la commande occupe la base à ce moment-là, on réessaie au tour suivant."""
        try:
            self.tour(maintenant)
        except sqlite3.OperationalError as e:
            if not occupee(e):
                raise  # une autre panne : le superviseur relancera le module
            self._dire_une_fois("occupee", f"Base occupée ({e}) : nouvel essai au tour suivant")

    def tour(self, maintenant: float) -> None:
        if self.pause_demandee(maintenant):
            if not self.en_pause:
                self.en_pause = True
                self.arreter_capteurs()
                self.vider(maintenant)
                self.base.ecrire("en_pause", True)  # la commande « pause » attend cette confirmation
                self.journal("En pause : tous les capteurs sont coupés")
        else:
            if self.en_pause:
                self.en_pause = False
                self.demarrer_capteurs()
                self.base.ecrire("en_pause", False)
                self.journal("Reprise : capteurs rallumés")
            self.relever(maintenant)
        if maintenant - self.dernier_vidage >= self.reglages["ecriture_groupee_s"] or len(self.tampon) >= 5000:
            self.vider(maintenant)
        if maintenant - self.dernier_battement >= BATTEMENT_S:
            self.battre(maintenant)
            self.entretenir(maintenant)
            self.prevenir(maintenant)
        self.traiter_demande(maintenant)
        self.suivre_analyse()
        if self.doit_analyser(maintenant):
            self.analyser(maintenant)

    # --- ce que la commande demande au démon (vider le tampon, tout effacer) ---------------------------------

    def traiter_demande(self, maintenant: float) -> None:
        demande = self.base.lire("demande")
        if not demande:
            return
        self.base.effacer("demande")
        quoi = demande.get("quoi")
        if quoi == "vider":
            self.vider(maintenant)
        elif quoi == "purge":
            self.recommencer(maintenant)
        self.base.ecrire("demande_faite", {"quoi": quoi, "quand": demande.get("quand")})

    def recommencer(self, maintenant: float) -> None:
        """« corvees purge » : tout est effacé, puis le détecteur repart de zéro (la pause éventuelle est gardée)."""
        pause = self.base.lire("pause")
        self.arreter_capteurs()
        self.tampon = []
        self.base.fermer()
        effacer_donnees(self.reglages, self.journal)
        self.gardien = privacy.Gardien(self.reglages, privacy.sel(self.dossier))
        self.base = Base(self.dossier / "corvees.db", self.gardien, journal=self.journal)
        self.session, self.dernier_evt = 0, 0.0
        if self.capteurs_construits:
            self.capteurs = construire(
                self.reglages, self.recevoir, self.base, self.natif, self.gardien.empreinte, self.gardien.chemin_exclu
            )
        else:
            for c in self.capteurs:
                c.memoire = self.base
        if pause:
            self.base.ecrire("pause", pause)
        self.base.ecrire("derniere_analyse", maintenant)  # pas d'analyse sur une base vide ce soir
        if not self.en_pause:
            self.demarrer_capteurs()
        self.journal("Purge : toutes les données effacées, le détecteur repart de zéro")

    def prevenir(self, maintenant: float) -> None:
        """La notification en attente (préparée après l'analyse) part dès que c'est permis."""
        from modules.corvees import notifier

        try:
            notifier.tenter(self.base, self.reglages, maintenant, journal=self.journal)
        except Exception as e:
            self._dire_une_fois("notification", f"Notification : {e.__class__.__name__} : {e}")

    # --- l'analyse dans un programme à part (sous le superviseur) ---------------------------------------------

    def lancer_analyse(self, maintenant: float) -> None:
        """L'analyse et sa suite tournent à part : la mémoire du démon reste petite, ses capteurs continuent."""
        if self.analyse is not None and self.analyse.poll() is None:
            self.journal("Analyse précédente encore en cours : celle-ci attendra demain")
            return
        self.base.ecrire("derniere_analyse", maintenant)
        sortie = self.dossier / "analyse.log"
        with open(os.open(sortie, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            self.analyse = subprocess.Popen(
                [sys.executable, "-m", "modules.corvees.analyse", repr(maintenant)],
                stdin=subprocess.PIPE,
                stdout=f,
                stderr=subprocess.STDOUT,
                cwd=RACINE,
                text=True,
            )
        assert self.analyse.stdin is not None
        self.analyse.stdin.write(json.dumps(self.reglages))
        self.analyse.stdin.close()
        self.analyse_debut = time.monotonic()
        self.journal(f"Analyse lancée à part (pid {self.analyse.pid})")

    def suivre_analyse(self) -> None:
        """L'analyse à part est-elle finie ? Ses messages rejoignent le journal du démon."""
        if self.analyse is None:
            return
        code = self.analyse.poll()
        if code is None:
            if time.monotonic() - self.analyse_debut < ANALYSE_MAX_S:
                return
            self.analyse.kill()
            code = self.analyse.wait()
            self.journal(f"Analyse arrêtée : plus de {ANALYSE_MAX_S // 60} minutes")
        sortie = self.dossier / "analyse.log"
        try:
            for ligne in sortie.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]:
                if ligne.strip():
                    self.journal(ligne.strip())
            sortie.unlink()
        except OSError:
            pass
        if code != 0:
            self.journal(f"Analyse : échec (code {code}), nouvel essai à la prochaine analyse")
        self.analyse = None

    def fermer(self, maintenant: float | None = None) -> None:
        if self.analyse is not None and self.analyse.poll() is None:
            self.analyse.terminate()  # le module s'arrête : son analyse aussi
            try:
                self.analyse.wait(10)
            except subprocess.TimeoutExpired:
                self.analyse.kill()
        self.arreter_capteurs()
        self.vider(maintenant or time.time())
        self.base.fermer()


def analyser_base(
    base: Base, reglages: dict[str, Any], maintenant: float, journal: Callable[[str], None] | None = None
) -> list[dict[str, Any]]:
    """L'analyse des 30 derniers jours : les corvées repérées sont enregistrées dans la base et renvoyées."""
    from modules.corvees.detection.moteur import ATTRIBUTS_UTILES

    depuis = maintenant - int(reglages["detection"]["fenetre_jours"]) * 86400
    evenements = base.evenements(depuis, attrs_pour=ATTRIBUTS_UTILES)
    candidats = analyser(evenements, reglages, base.decisions(), maintenant, fin=maintenant)
    base.enregistrer_candidats(candidats, maintenant)
    base.ecrire("derniere_analyse", maintenant)
    if journal:
        journal(f"Analyse : {len(evenements)} événements, {len(candidats)} corvées repérées")
    return candidats


def effacer_donnees(
    reglages: dict[str, Any], journal: Callable[[str], None] | None = None, lancer: Callable[..., Any] | None = None
) -> list[str]:
    """Efface tout ce que le détecteur a écrit (base, sel, propositions, rapport, sauvegardes…), après avoir
    désinstallé ce que tu avais installé avec « accept --installer ». Renvoie ce qui a été désinstallé."""
    import shutil

    from modules.corvees import propositions

    desinstalles = []
    for id_ in list(propositions.installations(reglages)):
        try:
            if lancer is None:
                propositions.desinstaller(reglages, id_)
            else:
                propositions.desinstaller(reglages, id_, lancer=lancer)
            desinstalles.append(id_)
        except Exception as e:
            if journal:
                journal(f"Purge : désinstallation de {id_} impossible ({e})")
    dossier = config.dossier_donnees(reglages)
    for motif in A_EFFACER:  # seulement ce que le détecteur a créé, même si le dossier a été mal réglé
        for chose in dossier.glob(motif):
            if chose.is_dir() and not chose.is_symlink():
                shutil.rmtree(chose)
            else:
                chose.unlink(missing_ok=True)
    return desinstalles


def boucle(ctx: Any) -> None:
    """Le module « corvees » de l'Assistant, sous le superviseur."""
    from modules.corvees.capteurs.natif import natif
    from modules.corvees.suite import apres_analyse

    reglages, erreurs = config.charger()
    for e in erreurs:
        ctx.log.warning(e)
    demon = Demon(reglages, natif(), journal=ctx.log.info, apres_analyse=apres_analyse, isolee=True)
    demon.demarrer_capteurs()
    ctx.log.info("Détecteur de corvées : %d capteurs", len(demon.capteurs))
    try:
        while not ctx.arret.is_set():
            demon.tour_protege(time.time())
            if demon.natif is not None:
                demon.natif.pomper(PAS_S)  # laisse macOS tenir à jour l'appli au premier plan
            else:
                ctx.attendre(PAS_S)
    finally:
        demon.fermer()


# --- L'interface de module (start, stop, status, health) ---------------------------------------------------------


def start() -> None:
    """Allume le module : le superviseur de l'Assistant le lance dans les 2 secondes, et le relance s'il tombe."""
    from core import config as reglages_assistant

    reglages_assistant.activer_module("corvees", True)


def stop() -> None:
    from core import config as reglages_assistant

    reglages_assistant.activer_module("corvees", False)


def status(base: Base | None = None, maintenant: float | None = None) -> dict[str, Any]:
    from core import config as reglages_assistant

    maintenant = maintenant or time.time()
    base = base or ouvrir()
    battement = base.lire("battement")
    pause = base.lire("pause")
    return {
        "actif": reglages_assistant.module_actif("corvees"),
        "vivant": bool(battement and maintenant - float(battement) < 3 * BATTEMENT_S),
        "battement": battement,
        "pause": pause,
        "evenements": base.compter(),
        "derniere_analyse": base.lire("derniere_analyse"),
        "corvees": len(base.candidats()),
    }


def health(base: Base | None = None, maintenant: float | None = None) -> dict[str, Any]:
    from modules.corvees.normalize import mois_de

    maintenant = maintenant or time.time()
    base = base or ouvrir()
    return {
        "capteurs": base.lire("sante", []),
        "taille_octets": base.taille(),
        "cout_du_mois_usd": round(base.cout_du_mois(mois_de(maintenant)), 4),
        **status(base, maintenant),
    }


def ouvrir(reglages: dict[str, Any] | None = None) -> Base:
    """La base du détecteur, pour la commande (le démon a la sienne)."""
    reglages = reglages or config.charger()[0]
    dossier = config.dossier_donnees(reglages)
    return Base(dossier / "corvees.db", privacy.Gardien(reglages, privacy.sel(dossier)))
