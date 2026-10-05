"""La surveillance en fond (`demarrage surveiller on`), lancée et relancée par le superviseur de l'Assistant.

- À son lancement juste après ta connexion : le mode « ouverture de session » (un relevé toutes les 5 s pendant
  5 min), puis le bilan de la session (temps jusqu'au calme).
- Ensuite, toutes les 2 min : un relevé (l'énergie toutes les 10 min). Un nouveau scan chaque jour, ou tout de
  suite si un dossier de démarrage change ; un nouvel élément est signalé par une notification.
- Chaque semaine : le temps de zsh, et un récap s'il y a un élément lourd qui ne sert à rien.
- Robuste : base corrompue (mise de côté, reconstruite), disque plein, veille du Mac (les trous sont ignorés),
  commande absente (collecteur dégradé). Il ne plante pas ; une panne d'un tour est notée et le tour suivant
  repart.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from modules.demarrage import config, travail
from modules.demarrage.analyse import analyser
from modules.demarrage.db import Base, DisquePlein
from modules.demarrage.mesure import session
from modules.demarrage.mesure.echantillonneur import COMMANDE_PS, Echantillonneur, analyser_ps
from modules.demarrage.modele import Fiche, Inventaire
from modules.demarrage.notifier import Notifieur, nouveaux_message
from modules.demarrage.systeme import Mac, Systeme

log = logging.getLogger("demarrage")
BATTEMENT_S = 60
SCAN_S = 86400
RECAP_S = 7 * 86400
PURGE_S = 86400
# Les dossiers où un nouveau programme de démarrage apparaît : surveillés à chaque tour (une date par dossier).
DOSSIERS = [
    "{maison}/Library/LaunchAgents",
    "/Library/LaunchAgents",
    "/Library/LaunchDaemons",
    "/Library/PrivilegedHelperTools",
    "/Applications",
]


class Demon:
    def __init__(
        self,
        systeme: Systeme,
        base: Base,
        reglages: dict[str, Any],
        notifieur: Notifieur,
        arret: Callable[[], bool] = lambda: False,
        rouvrir: Callable[[], Base] | None = None,
    ):
        self.systeme = systeme
        self.base = base
        self.reglages = reglages
        self.notifieur = notifieur
        self.arret = arret
        self.rouvrir = rouvrir
        self.inventaire: Inventaire | None = base.dernier_scan()
        self.echantillonneur = Echantillonneur(systeme, base, reglages, self.fiches)
        self.derniere_energie = -1e18
        self.signature: tuple[tuple[str, int], ...] | None = None

    def fiches(self) -> list[Fiche]:
        return self.inventaire.fiches if self.inventaire else []

    # --- le scan et les nouveaux éléments ---------------------------------------------------------------------

    def signature_dossiers(self) -> tuple[tuple[str, int], ...]:
        resultat = []
        for modele in DOSSIERS:
            chemin = modele.format(maison=self.systeme.maison)
            try:
                resultat.append((chemin, self.systeme.chemin(chemin).stat().st_mtime_ns))
            except OSError:
                resultat.append((chemin, 0))
        return tuple(resultat)

    def scanner(self, maintenant: float) -> list[str]:
        inventaire, nouveaux, premier = travail.scanner(self.systeme, self.base, self.reglages)
        self.inventaire = inventaire
        self.base.ecrire("dernier_scan", maintenant)
        if premier:
            return []  # le premier scan sert de référence : tout y serait « nouveau »
        self.notifier_nouveaux(nouveaux, maintenant)
        return nouveaux

    def notifier_nouveaux(self, nouveaux: list[str], maintenant: float) -> None:
        if not nouveaux or self.inventaire is None:
            return
        bilan = analyser(self.inventaire, self.base, self.reglages, maintenant)
        a_dire = []
        for id_ in nouveaux:
            el = bilan.element(id_)
            if el is None or el.verdict.code == "apple" or el.fiche.c_est_moi or el.fiche.actif is False:
                continue
            if el.fiche.source == "launchd":
                continue  # chargé sans fichier : souvent passager, le prochain scan le dira s'il reste
            a_dire.append(f"{el.nom} ({el.editeur or 'éditeur inconnu'})")
        if a_dire:
            self.notifieur.proposer("nouveau", nouveaux_message(a_dire), maintenant, a_dire)

    def recap(self, maintenant: float) -> None:
        if self.inventaire is None:
            return
        bilan = analyser(self.inventaire, self.base, self.reglages, maintenant)
        lourds = [el for el in bilan.couteux(self.reglages) if el.verdict.code in ("inutile", "orphelin")]
        self.base.ecrire("dernier_recap", maintenant)
        if not lourds:
            return
        from modules.demarrage.rapport import memoire, secondes

        mem = sum(el.metriques.memoire_mo or 0 for el in lourds)
        cpu = sum(el.metriques.cpu_session_s or 0 for el in lourds)
        message = (
            f"💤 {len(lourds)} élément{'s' if len(lourds) > 1 else ''} te coûte{'nt' if len(lourds) > 1 else ''} "
            f"pour rien : environ {memoire(mem)} et {secondes(cpu)} à chaque ouverture de session. "
            "Détails : demarrage rapport"
        )
        self.notifieur.proposer("recap", message, maintenant)

    # --- l'ouverture de session ------------------------------------------------------------------------------

    def premier_processus(self) -> float | None:
        r = self.systeme.executer(COMMANDE_PS, delai=self.reglages["delais"]["commande_s"])
        if not r.ok:
            return None
        maintenant = self.systeme.maintenant()
        lancements = [maintenant - p.age_s for p in analyser_ps(r.sortie) if p.uid == self.systeme.uid]
        return min(lancements) if lancements else None

    def demarrer(self) -> dict[str, Any] | None:
        """Au lancement : suivre l'ouverture de session si elle vient d'avoir lieu (et n'est pas déjà suivie)."""
        boot = session.demarrage(self.systeme)
        if boot is None or self.base.session(boot) is not None:
            return None
        connexion, source = session.connexion(
            self.systeme, boot, self.premier_processus(), self.reglages["delais"]["journal_systeme_s"]
        )
        if self.inventaire is None:
            self.scanner(self.systeme.maintenant())
        fenetre = self.reglages["echantillonnage"]["session_minutes"] * 60
        if connexion is not None and self.systeme.maintenant() - connexion < fenetre:
            bilan = self.echantillonneur.suivre_session(boot, connexion, self.arret)
            log.info("[demarrage] ouverture de session suivie (%s) : %s", source, bilan)
            return bilan
        details = {
            "demarrage_s": None if connexion is None else round(connexion - boot, 1),
            "calme_s": None,
            "note": "pas observée : la surveillance a démarré trop tard",
        }
        self.base.enregistrer_session(boot, connexion, None, details)
        return details

    # --- un tour de croisière -----------------------------------------------------------------------------------

    def tour(self, maintenant: float) -> None:
        self.base.ecrire("battement", maintenant)
        signature = self.signature_dossiers()
        dernier = float(self.base.lire("dernier_scan", 0) or 0)
        if (
            self.inventaire is None
            or maintenant - dernier >= SCAN_S
            or (self.signature and signature != self.signature)
        ):
            self.scanner(maintenant)
        self.signature = signature
        e = self.reglages["echantillonnage"]
        energie = maintenant - self.derniere_energie >= e["energie_pas_s"]
        if self.echantillonneur.prendre("croisiere", avec_energie=energie) is not None and energie:
            self.derniere_energie = maintenant
        if maintenant - float(self.base.lire("derniere_purge", 0) or 0) >= PURGE_S:
            self.base.purger(
                self.reglages["retention_jours"], maintenant, lambda t: time.strftime("%Y-%m-%d", time.localtime(t))
            )
            self.base.ecrire("derniere_purge", maintenant)
        if maintenant - float(self.base.lire("dernier_recap", 0) or 0) >= RECAP_S:
            travail.mesurer_zsh(self.systeme, self.base, self.reglages)
            self.recap(maintenant)
        self.notifieur.relancer(maintenant)

    def tour_protege(self, maintenant: float) -> bool:
        """Un tour qui ne fait jamais tomber le démon. Renvoie False si le tour a échoué."""
        try:
            self.tour(maintenant)
            return True
        except DisquePlein:
            log.error("[demarrage] disque plein : ce tour n'est pas enregistré")
        except sqlite3.DatabaseError as e:
            log.error("[demarrage] base en panne (%s) : je la rouvre", e)
            if self.rouvrir:
                try:
                    self.base.fermer()
                except sqlite3.Error:
                    pass
                self.base = self.rouvrir()
                self.notifieur.base = self.base
                self.echantillonneur.base = self.base
        except Exception:
            log.exception("[demarrage] tour en panne")
        return False

    def tourner(self, attendre: Callable[[float], bool]) -> None:
        """attendre(s) : attend s secondes ; renvoie True s'il faut s'arrêter."""
        try:
            self.demarrer()
        except Exception:
            log.exception("[demarrage] suivi de l'ouverture de session en panne")
        while not self.arret():
            self.tour_protege(self.systeme.maintenant())
            if attendre(self.reglages["echantillonnage"]["croisiere_pas_s"]):
                break


def boucle(ctx: Any) -> None:
    reglages, erreurs = config.charger()
    for erreur in erreurs:
        ctx.log.warning(erreur)
    base = travail.ouvrir_base(reglages)
    notifieur = Notifieur(base, reglages)
    demon = Demon(Mac(), base, reglages, notifieur, ctx.arret.is_set, lambda: travail.ouvrir_base(reglages))
    try:
        demon.tourner(ctx.attendre)
    finally:
        demon.base.fermer()


def status(base: Base, maintenant: float) -> dict[str, Any]:
    battement = base.lire("battement")
    return {
        "vivant": bool(battement and maintenant - float(battement) < 3 * 120 + BATTEMENT_S),
        "battement": battement,
        "dernier_scan": base.lire("dernier_scan"),
        "en_attente": base.lire("en_attente"),
        "sessions": len(base.sessions()),
        "releves": len(base.releves()),
    }
