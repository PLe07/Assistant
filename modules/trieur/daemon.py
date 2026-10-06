"""La surveillance en fond (§9), lancée par le superviseur de l'Assistant quand le module est actif.

Toutes les 2 secondes : regarder les entrées (boîte iCloud, « À trier », Téléchargements), traiter la file,
envoyer les notifications. Chaque matin (9 h) : les garanties qui finissent dans 30 ou 7 jours. Après chaque lot :
les pages HTML de la boîte. Un fichier déplacé à la main dans « Classés » est suivi (et le Trieur apprend).

Rien ici ne fait tomber le démon : une erreur sur un fichier est notée, la boucle continue.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.journal import journal

log = journal("trieur")
PAS_S = 2.0
RELIRE_REGLAGES_S = 60.0
BATTEMENT_S = 30.0


class Demenagements:
    """Les fichiers renommés ou déplacés à la main dans « Classés » (FSEvents par watchdog)."""

    def __init__(self) -> None:
        self.verrou = threading.Lock()
        self.vus: list[tuple[Path, Path]] = []
        self.observateur: Any = None

    def demarrer(self, dossier: Path) -> bool:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return False
        parent = self

        class Gestion(FileSystemEventHandler):
            def on_moved(self, event: Any) -> None:
                if not event.is_directory:
                    with parent.verrou:
                        parent.vus.append((Path(str(event.src_path)), Path(str(event.dest_path))))

        dossier.mkdir(parents=True, exist_ok=True)
        self.observateur = Observer()
        self.observateur.schedule(Gestion(), str(dossier), recursive=True)
        self.observateur.daemon = True
        self.observateur.start()
        return True

    def prendre(self) -> list[tuple[Path, Path]]:
        with self.verrou:
            lot, self.vus = self.vus, []
        return lot

    def arreter(self) -> None:
        if self.observateur is not None:
            self.observateur.stop()
            self.observateur.join(timeout=5)


class Demon:
    def __init__(self, reglages: dict[str, Any], outils: Any = None, systeme_: Any = None,
                 horloge: Any = time.time) -> None:  # fmt: skip
        from modules.trieur import traitement
        from modules.trieur.entrees.surveillance import Entrees
        from modules.trieur.notifications import Notifieur

        self.reglages, self.horloge = reglages, horloge
        self.o = outils or traitement.outils(reglages, systeme_=systeme_)
        self.notifieur = Notifieur(reglages, horloge=horloge)
        self.o.avertir = self._avertir
        self.entrees = Entrees(reglages, self.o.base, self.o.systeme, horloge)
        self.metas: dict[int, Path] = {}
        self.demenagements = Demenagements()
        self.dernier_battement = 0.0

    def _battre(self) -> None:
        """Le battement lu par doctor et « assistant.py etat » : au début de chaque tour (le premier dès le
        lancement), et après chaque document d'une longue file (un gros envoi ne passe pas pour un démon muet)."""
        maintenant = self.horloge()
        if maintenant - self.dernier_battement >= BATTEMENT_S:
            self.o.base.ecrire_meta("battement", str(maintenant))
            self.dernier_battement = maintenant

    def _avertir(self, el: Any) -> None:
        self._battre()
        garantie = None
        if el.etat == "classe" and self.o.coffre is not None:
            fiches = [f for f in self.o.coffre.fiches() if f.element == el.id]
            garantie = fiches[0].fin.strftime("%d/%m/%Y") if fiches else None
        self.notifieur.element(el, garantie)

    def demarrer(self) -> None:
        from modules.trieur import config

        self.entrees.creer_les_dossiers()
        repris = self.o.base.relacher_les_interrompus()
        if repris:
            log.info("%s élément(s) interrompu(s) repris", repris)
        self.demenagements.demarrer(config.chemin(self.reglages, "classes"))
        self._pages()

    def tour(self) -> int:
        """Un passage : renvoie le nombre d'éléments traités."""
        from modules.trieur import traitement
        from modules.trieur.base import FINIS

        self._battre()
        for pret in self.entrees.regarder():
            element = self.o.base.ajouter(pret.chemin, pret.source, pret.note)
            if pret.meta is not None:
                self.metas[element] = pret.meta
        faits = traitement.traiter_la_file(self.o)
        for el in faits:
            meta = self.metas.pop(el.id, None)
            if meta is not None and el.etat in (*FINIS, "doublon") and not Path(el.chemin).exists():
                meta.unlink(missing_ok=True)  # la note a voyagé avec son document : elle n'a plus lieu d'être
        for ancien, nouveau in self.demenagements.prendre():
            try:
                traitement.apprendre_deplacement(self.o, ancien, nouveau)
            except Exception as e:
                log.warning("déplacement non suivi (%s) : %s", nouveau.name, e)
        if faits:
            self._pages()
        self.notifieur.vider()
        self._chaque_matin()
        return len(faits)

    def _pages(self) -> None:
        from modules.trieur import pages

        try:
            pages.mettre_a_jour(self.reglages, self.o.base, self.o.coffre)
        except Exception as e:  # iCloud absent, disque plein… : le tri continue
            log.warning("pages HTML non écrites : %s", e)

    def _chaque_matin(self) -> None:
        heure = str(self.reglages["garanties"]["verification_quotidienne"])
        maintenant = datetime.fromtimestamp(self.horloge())
        aujourd_hui = maintenant.date().isoformat()
        if maintenant.strftime("%H:%M") < heure or self.o.base.lire_meta("verifie_le") == aujourd_hui:
            return
        self.o.base.ecrire_meta("verifie_le", aujourd_hui)
        for fiche, jours in self.o.coffre.echeances(date.fromisoformat(aujourd_hui)):
            self.notifieur.echeance(fiche.produit, jours, fiche.fin.strftime("%d/%m/%Y"))
        self._pages()

    def arreter(self) -> None:
        self.notifieur.vider(forcer=True)
        self.demenagements.arreter()
        self.o.base.fermer()


def boucle(ctx: Any) -> None:
    from modules.trieur import config

    reglages, erreurs = config.charger()
    for e in erreurs:
        log.warning("%s", e)
    demon = Demon(reglages)
    demon.demarrer()
    relu = time.time()
    try:
        while True:
            try:
                demon.tour()
            except Exception as e:  # un tour raté ne doit pas arrêter la surveillance
                log.error("tour en échec : %s", e)
            if ctx.attendre(PAS_S):
                break
            if time.time() - relu >= RELIRE_REGLAGES_S:
                relu = time.time()
                nouveaux, _ = config.charger()
                if nouveaux != demon.reglages:
                    demon.reglages.clear()
                    demon.reglages.update(nouveaux)
    finally:
        demon.arreter()


def status(reglages: dict[str, Any], base: Any, maintenant: float) -> dict[str, Any]:
    """Pour « python assistant.py etat » et « trieur statut »."""
    battement = base.lire_meta("battement")
    age = maintenant - float(battement) if battement else None
    comptes = base.compter()
    return {"actif": reglages["actif"], "vivant": age is not None and age < 3 * BATTEMENT_S, "battement_age": age,
            "a_verifier": comptes.get("a_verifier", 0), "ranges": comptes.get("classe", 0),
            "en_attente": comptes.get("en_attente", 0), "erreurs": comptes.get("erreur", 0)}  # fmt: skip
