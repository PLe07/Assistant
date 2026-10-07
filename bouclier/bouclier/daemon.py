"""Le démon de Bouclier (LaunchAgent `com.<session>.bouclier`, D-04) : une boucle qui ne s'arrête jamais sur une
erreur.

À chaque tour (toutes les 3 s, ou tout de suite quand FSEvents signale un nouveau fichier) :
- l'entrée iCloud du raccourci « Arnaque ? » (réponse en quelques secondes) ;
- Gmail toutes les 5 minutes (délai croissant après un échec : 10, 20, 40 puis 60 minutes) ;
- une fois par jour : les flux de liens piégés, la liste des fuites, le ménage de l'entrée iCloud ;
- une fois par semaine : l'inventaire des comptes ;
- tous les 6 mois : la revérification des numéros de la fiche urgence et le rappel de la relire ;
- les notifications gardées pour la nuit partent à 8 h ; le tableau de bord est mis à jour après chaque changement.

Les dates des prochaines tâches sont en base : un redémarrage ou une mise en veille ne les décale pas.
"""

from __future__ import annotations

import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bouclier import config, reseau, tableau_de_bord
from bouclier.arnaque import analyse
from bouclier.arnaque.flux import Flux
from bouclier.comptes.imap_lecture_seule import ErreurImap, Fabrique, _fabrique_reelle
from bouclier.db import Base
from bouclier.entree_icloud import BoiteEntree
from bouclier.journal import log
from bouclier.notifier import Notifieur
from bouclier.systeme import Systeme

PAS_S = 3.0
JOUR_S = 86400
SEMAINE_S = 7 * JOUR_S
SIX_MOIS_S = 182 * JOUR_S
RETRY_S = 3600


@dataclass
class Composants:
    telecharger: Callable[..., reseau.Reponse] = reseau.telecharger
    fabrique_imap: Fabrique = _fabrique_reelle
    outils: Callable[[dict[str, Any]], analyse.Outils] | None = None


@dataclass
class Tour:
    fait: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


class Demon:
    def __init__(self, chemins: config.Chemins, base: Base, systeme: Systeme, horloge: Callable[[], float] = time.time,
                 composants: Composants | None = None) -> None:  # fmt: skip
        self.chemins, self.base, self.systeme, self.horloge = chemins, base, systeme, horloge
        self.c = composants or Composants()
        self.boite = BoiteEntree(chemins, base, systeme, horloge)
        self.reveil = threading.Event()

    # --- Planification (en base : survit aux redémarrages) --------------------------------------------------------
    def _du(self, tache: str) -> bool:
        prochain = self.base.lire_meta(f"prochain:{tache}")
        return prochain is None or self.horloge() >= float(prochain)

    def _planifier(self, tache: str, dans: float) -> None:
        self.base.ecrire_meta(f"prochain:{tache}", str(self.horloge() + dans))

    def _outils(self, reglages: dict[str, Any]) -> analyse.Outils:
        if self.c.outils is not None:
            return self.c.outils(reglages)
        return analyse.outils_reels(self.chemins, reglages, self.base, self.systeme)

    # --- Les tâches -----------------------------------------------------------------------------------------------
    def _entree(self, reglages: dict[str, Any], notifieur: Notifieur, tour: Tour) -> None:
        prets = self.boite.prets()
        if not prets:
            return
        outils = self._outils(reglages)
        for chemin in prets:
            t = self.boite.traiter(chemin, outils, notifieur)
            tour.fait.append(f"entrée iCloud : {t.titre}")

    def _gmail(self, reglages: dict[str, Any], notifieur: Notifieur, tour: Tour) -> None:
        from bouclier import gmail, surveillance_gmail

        intervalle = max(1, int(reglages["gmail"].get("intervalle_minutes", 5))) * 60
        try:
            with gmail.ouvrir(reglages, self.systeme, self.c.fabrique_imap) as lecteur:
                r = surveillance_gmail.relever(lecteur, self.base, self._outils(reglages), notifieur)
        except gmail.GmailNonRelie as e:
            self.base.ecrire_meta("gmail_erreur", str(e))
            self._planifier("gmail", RETRY_S)
            return
        except ErreurImap as e:
            echecs = int(self.base.lire_meta("gmail_echecs", "0") or 0) + 1
            self.base.ecrire_meta("gmail_echecs", str(echecs))
            self.base.ecrire_meta("gmail_erreur", str(e))
            self._planifier("gmail", min(60 * 60, intervalle * 2**echecs))
            tour.erreurs.append(f"Gmail : {e}")
            return
        self.base.ecrire_meta("gmail_echecs", "0")
        self.base.ecrire_meta("gmail_erreur", "")
        self.base.ecrire_meta("gmail_releve_le", str(self.horloge()))
        self._planifier("gmail", intervalle)
        if r.analyses or r.premier_passage:
            tour.fait.append(f"Gmail : {r.analyses} message(s) analysé(s)")

    def _flux(self, tour: Tour) -> None:
        etats = Flux(self.chemins.caches, self.c.telecharger).mettre_a_jour()
        self._planifier("flux", JOUR_S)
        tour.fait.append("flux : " + ", ".join(f"{e.nom} {'OK' if not e.erreur else e.erreur}" for e in etats))

    def _inventaire(self, reglages: dict[str, Any], tour: Tour) -> None:
        from bouclier.comptes import lancer

        r = lancer.lancer(self.chemins, reglages, self.base, self.systeme, fabrique=self.c.fabrique_imap)
        self._planifier("inventaire", SEMAINE_S)
        tour.fait.append(f"inventaire : {r.comptes} comptes")

    def _fuites(self, reglages: dict[str, Any], notifieur: Notifieur, tour: Tour) -> None:
        from bouclier.fuites import rapport

        r = rapport.verifier(self.chemins, reglages, self.base, notifieur, self.c.telecharger)
        self._planifier("fuites", JOUR_S)
        tour.fait.append(f"fuites : {len(r.bilan.toutes)} te concernent ({len(r.bilan.nouvelles)} nouvelles)")

    def _urgence(self, notifieur: Notifieur, tour: Tour) -> None:
        from bouclier.urgence import service

        if self.base.lire_meta("fiche_generee_le") is None:
            service.generer(self.chemins, self.base)
            tour.fait.append("fiche urgence générée")
        if self._du("urgence-sources"):
            r = service.verifier(self.chemins, self.base, notifieur, self.c.telecharger)
            self._planifier("urgence-sources", SIX_MOIS_S if r.reverif.pages_lues else JOUR_S)
            tour.fait.append(f"numéros revérifiés : {len(r.reverif.confirmes)} confirmés")
        if service.rappel(self.base, notifieur, self.horloge):
            tour.fait.append("rappel : relire la fiche urgence")
        self._planifier("urgence", JOUR_S)

    def _menage(self, tour: Tour) -> None:
        retires = self.boite.purger()
        self._planifier("menage", JOUR_S)
        if retires:
            tour.fait.append(f"ménage : {retires} copie(s) de plus de 30 jours retirée(s)")

    # --- Un tour --------------------------------------------------------------------------------------------------
    def tour(self) -> Tour:
        t = Tour()
        self.base.ecrire_meta("demon_battement", str(self.horloge()))
        reglages, alerte = config.charger_ou_defauts(self.chemins)
        self.base.ecrire_meta("config_alerte", alerte or "")
        notifieur = Notifieur(self.base, self.systeme, reglages, self.horloge)
        taches: list[tuple[str, Callable[[], None]]] = [("entree", lambda: self._entree(reglages, notifieur, t))]
        if reglages["gmail"].get("active", True) and self._du("gmail"):
            taches.append(("gmail", lambda: self._gmail(reglages, notifieur, t)))
        if self._du("flux"):
            taches.append(("flux", lambda: self._flux(t)))
        if self._du("inventaire"):
            taches.append(("inventaire", lambda: self._inventaire(reglages, t)))
        if self._du("fuites"):
            taches.append(("fuites", lambda: self._fuites(reglages, notifieur, t)))
        if self._du("urgence"):
            taches.append(("urgence", lambda: self._urgence(notifieur, t)))
        if self._du("menage"):
            taches.append(("menage", lambda: self._menage(t)))
        for nom, tache in taches:
            try:
                tache()
            except Exception as e:  # noqa: BLE001 - une brique en panne n'arrête jamais les autres
                t.erreurs.append(f"{nom} : {e.__class__.__name__}")
                log().warning("tâche %s en échec (%s) : nouvel essai dans 1 h", nom, e.__class__.__name__)
                if nom != "entree":
                    self._planifier(nom, RETRY_S)
        try:
            notifieur.envoyer_en_attente()
        except Exception:  # noqa: BLE001
            t.erreurs.append("notifications")
        if t.fait and any(not f.startswith("entrée") for f in t.fait):
            try:
                tableau_de_bord.ecrire(self.base, self.chemins.tableau_de_bord)
            except Exception:  # noqa: BLE001
                t.erreurs.append("tableau de bord")
        for f in t.fait:
            log().info("%s", f)
        return t

    # --- La boucle ------------------------------------------------------------------------------------------------
    def _surveiller(self) -> object | None:
        """FSEvents (watchdog) sur les dossiers d'entrée : un nouveau fichier réveille la boucle tout de suite."""
        try:
            from watchdog.events import FileSystemEvent, FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:  # pragma: no cover - dépendance du projet
            return None
        reveil = self.reveil

        class Reveil(FileSystemEventHandler):
            def on_any_event(self, event: FileSystemEvent) -> None:
                reveil.set()

        observateur = Observer()
        dossiers = [d for d in self.chemins.entrees() if d.is_dir()]
        for d in dossiers:
            observateur.schedule(Reveil(), str(d), recursive=False)
        if not dossiers:
            return None
        observateur.daemon = True
        observateur.start()
        return observateur

    def lancer(self, arret: threading.Event, max_tours: int | None = None) -> int:
        observateur = self._surveiller()
        tours = 0
        log().info("démon démarré (pid de launchd)")
        while not arret.is_set():
            self.tour()
            tours += 1
            if max_tours is not None and tours >= max_tours:
                break
            self.reveil.wait(PAS_S)
            self.reveil.clear()
        if observateur is not None:
            observateur.stop()  # type: ignore[attr-defined]
        log().info("démon arrêté")
        return tours


def principal(chemins: config.Chemins | None = None) -> int:  # pragma: no cover - lancé par launchd
    from bouclier import db, journal

    reseau.installer_garde()
    chemins = chemins or config.chemins()
    reglages, _ = config.charger_ou_defauts(chemins)
    journal.configurer(chemins.logs, reglages.get("moi", {}))
    config.preparer_dossiers(chemins)
    arret = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: arret.set())
    signal.signal(signal.SIGINT, lambda *_: arret.set())
    demon = Demon(chemins, db.ouvrir(chemins.base), Systeme())
    return 0 if demon.lancer(arret) >= 0 else 1


def battement(base: Base) -> float | None:
    valeur = base.lire_meta("demon_battement")
    return float(valeur) if valeur else None


def journal_demon(chemins: config.Chemins) -> Path:
    return chemins.logs / "bouclier.log"
