"""Le démon de Bouclier (LaunchAgent `com.<session>.bouclier`, D-04) : une boucle qui ne s'arrête jamais sur une
erreur.

Toutes les 3 s (ou tout de suite quand FSEvents signale un nouveau fichier) : l'entrée iCloud du raccourci
« Arnaque ? » (réponse en quelques secondes). Dans un fil à part, pour ne jamais retarder cette réponse :
- Gmail toutes les 5 minutes (délai croissant après un échec : 10, 20, 40 puis 60 minutes) ;
- une fois par jour : les flux de liens piégés, la liste des fuites, le ménage de l'entrée iCloud ;
- une fois par semaine : l'inventaire des comptes ;
- tous les 6 mois : la revérification des numéros de la fiche urgence et le rappel de la relire ;
- les notifications gardées pour la nuit partent à 8 h ; le tableau de bord est mis à jour après chaque changement.

Les dates des prochaines tâches sont en base : un redémarrage ou une mise en veille ne les décale pas.
"""

from __future__ import annotations

import copy
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bouclier import config, db, reseau, tableau_de_bord
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
BATTEMENT_S = 30  # doctor juge le démon arrêté sans battement depuis 2 min : inutile d'écrire en base toutes les 3 s


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
    def __init__(
        self,
        chemins: config.Chemins,
        base: Base,
        systeme: Systeme,
        horloge: Callable[[], float] = time.time,
        composants: Composants | None = None,
        ouvrir_base: Callable[[], Base] | None = None,
    ) -> None:
        self.chemins, self.base, self.systeme, self.horloge = chemins, base, systeme, horloge
        self.c = composants or Composants()
        self.ouvrir_base = ouvrir_base or (lambda: db.ouvrir(chemins.base))
        self.boite = BoiteEntree(chemins, base, systeme, horloge)
        self.reveil = threading.Event()
        self._dernier_battement = float("-inf")
        self._reglages: tuple[tuple[int, int] | None, dict[str, Any], str | None] | None = None

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

    # --- Les tours ----------------------------------------------------------------------------------------------
    def reglages(self) -> dict[str, Any]:
        """Les réglages, relus seulement quand config.toml a changé (la boucle tourne toutes les 3 s)."""
        try:
            st = self.chemins.config.stat()
            cle: tuple[int, int] | None = (st.st_mtime_ns, st.st_size)
        except OSError:
            cle = None
        if self._reglages is None or self._reglages[0] != cle:
            reglages, alerte = config.charger_ou_defauts(self.chemins)
            if (self.base.lire_meta("config_alerte") or "") != (alerte or ""):
                self.base.ecrire_meta("config_alerte", alerte or "")
            self._reglages = (cle, reglages, alerte)
        return copy.deepcopy(self._reglages[1])

    def _debut(self) -> tuple[dict[str, Any], Notifieur]:
        reglages = self.reglages()
        return reglages, Notifieur(self.base, self.systeme, reglages, self.horloge)

    def _executer(self, taches: list[tuple[str, Callable[[], None]]], t: Tour) -> None:
        for nom, tache in taches:
            try:
                tache()
            except Exception as e:  # noqa: BLE001 - une brique en panne n'arrête jamais les autres
                t.erreurs.append(f"{nom} : {e.__class__.__name__}")
                log().warning("tâche %s en échec (%s) : nouvel essai dans 1 h", nom, e.__class__.__name__)
                if nom != "entree":
                    self._planifier(nom, RETRY_S)

    def _envoyer_en_attente(self, notifieur: Notifieur, t: Tour) -> None:
        try:
            notifieur.envoyer_en_attente()
        except Exception:  # noqa: BLE001
            t.erreurs.append("notifications")

    def _tableau(self, t: Tour) -> None:
        """Le tableau de bord est réécrit après chaque changement."""
        if not t.fait:
            return
        try:
            tableau_de_bord.ecrire(self.base, self.chemins.tableau_de_bord)
        except Exception:  # noqa: BLE001
            t.erreurs.append("tableau de bord")

    def taches_dues(self, reglages: dict[str, Any]) -> list[str]:
        noms = [n for n in ("flux", "inventaire", "fuites", "urgence", "menage") if self._du(n)]
        if reglages["gmail"].get("active", True) and self._du("gmail"):
            noms.insert(0, "gmail")
        return noms

    def tour_rapide(self) -> Tour:
        """Toutes les 3 s : le battement, l'entrée iCloud du raccourci (réponse en quelques secondes), les
        notifications gardées pour la nuit."""
        t = Tour()
        if self.horloge() - self._dernier_battement >= BATTEMENT_S:
            self._dernier_battement = self.horloge()
            self.base.ecrire_meta("demon_battement", str(self._dernier_battement))
        reglages, notifieur = self._debut()
        self._executer([("entree", lambda: self._entree(reglages, notifieur, t))], t)
        self._envoyer_en_attente(notifieur, t)
        self._tableau(t)
        for f in t.fait:
            log().info("%s", f)
        return t

    def tour_lent(self) -> Tour:
        """Les tâches datées (Gmail, listes, inventaire, fuites, fiche urgence, ménage) : sur le Mac, dans un fil à
        part, pour qu'un long inventaire ne retarde jamais la réponse au raccourci."""
        t = Tour()
        reglages, notifieur = self._debut()
        actions: dict[str, Callable[[], None]] = {
            "gmail": lambda: self._gmail(reglages, notifieur, t),
            "flux": lambda: self._flux(t),
            "inventaire": lambda: self._inventaire(reglages, t),
            "fuites": lambda: self._fuites(reglages, notifieur, t),
            "urgence": lambda: self._urgence(notifieur, t),
            "menage": lambda: self._menage(t),
        }
        self._executer([(nom, actions[nom]) for nom in self.taches_dues(reglages)], t)
        self._envoyer_en_attente(notifieur, t)
        self._tableau(t)
        for f in t.fait:
            log().info("%s", f)
        return t

    def tour(self) -> Tour:
        """Un tour complet, dans l'ordre (tests et `bouclier demon --une-fois`)."""
        rapide, lent = self.tour_rapide(), self.tour_lent()
        return Tour(rapide.fait + lent.fait, rapide.erreurs + lent.erreurs)

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

    def _fil_lent(self) -> None:
        """Le tour lent avec sa propre connexion à la base (SQLite : une connexion par fil)."""
        try:
            base = self.ouvrir_base()
        except Exception as e:  # noqa: BLE001
            log().warning("tour lent impossible : base illisible (%s)", e.__class__.__name__)
            return
        try:
            Demon(self.chemins, base, self.systeme, self.horloge, self.c, self.ouvrir_base).tour_lent()
        except Exception as e:  # noqa: BLE001 - le fil ne doit jamais mourir en silence
            log().warning("tour lent en échec (%s)", e.__class__.__name__)
        finally:
            base.cx.close()

    def lancer(self, arret: threading.Event, max_tours: int | None = None) -> int:
        observateur = self._surveiller()
        tours = 0
        fil: threading.Thread | None = None
        log().info("démon démarré")
        while not arret.is_set():
            self.tour_rapide()
            if fil is None or not fil.is_alive():
                if self.taches_dues(self.reglages()):
                    fil = threading.Thread(target=self._fil_lent, name="bouclier-taches", daemon=True)
                    fil.start()
            tours += 1
            if max_tours is not None and tours >= max_tours:
                break
            self.reveil.wait(PAS_S)
            self.reveil.clear()
        if fil is not None:
            fil.join(timeout=10)
        if observateur is not None:
            observateur.stop()  # type: ignore[attr-defined]
        log().info("démon arrêté")
        return tours


def principal(chemins: config.Chemins | None = None) -> int:  # pragma: no cover - lancé par launchd
    from bouclier import journal

    reseau.installer_garde()
    chemins = chemins or config.chemins()
    reglages, _ = config.charger_ou_defauts(chemins)
    journal.configurer(chemins.logs, reglages.get("moi", {}))
    config.preparer_dossiers(chemins)
    # Une erreur imprévue irait en clair dans demon.erreurs.log (launchd) : seul son type est noté, caviardé.
    sys.excepthook = lambda genre, *_: log().error("erreur imprévue : %s", genre.__name__)
    threading.excepthook = lambda a: log().error("erreur imprévue dans un fil : %s", a.exc_type.__name__)
    arret = threading.Event()
    demon = Demon(chemins, db.ouvrir(chemins.base), Systeme())

    def arreter(*_: object) -> None:  # launchd envoie SIGTERM puis, 20 s plus tard, SIGKILL : on s'arrête tout de suite
        arret.set()
        demon.reveil.set()

    signal.signal(signal.SIGTERM, arreter)
    signal.signal(signal.SIGINT, arreter)
    return 0 if demon.lancer(arret) >= 0 else 1


def battement(base: Base) -> float | None:
    valeur = base.lire_meta("demon_battement")
    return float(valeur) if valeur else None


def journal_demon(chemins: config.Chemins) -> Path:
    return chemins.logs / "bouclier.log"
