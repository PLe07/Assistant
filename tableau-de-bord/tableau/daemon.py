"""Le démon du tableau de bord (LaunchAgent `com.<toi>.tableau`) : un tour par minute, en priorité basse.

Un tour : l'heure (veille et réveil), la découverte (toutes les 10 min), le gardien d'intégrité (toutes les 30 min
et sur signal FSEvents), l'observation de chaque module (adaptateurs, en lecture seule), les attentes, la santé,
les mesures gardées, les alertes, le rapport de la semaine, la page en direct, l'instantané iPhone, l'entretien de
la base. Chaque étape est isolée : une erreur est notée dans le journal (caviardé) et le tour continue.

Une seule instance à la fois (verrou), arrêt propre sur SIGTERM, aucune écriture si le disque est plein (le tour
est abandonné, `tableau doctor` le dit).
"""

from __future__ import annotations

import fcntl
import json
import logging
import logging.handlers
import os
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau import adaptateurs, caviardage, config, notifier, planif, registre, systeme, vues
from tableau.adaptateurs.contexte import Contexte
from tableau.analyse import attentes, credits, credits_reels, rapport_semaine, sante
from tableau.analyse.alertes import Alertes
from tableau.analyse.integrite import Gardien, Surveillance
from tableau.db import Base, DisquePlein
from tableau.decouverte import decouvrir
from tableau.instantane_icloud import Instantane
from tableau.module import DefModule, EtatModule
from tableau.notifier import Notificateur
from tableau.sondes import docker_n8n, processus
from tableau.sondes.docker_n8n import SondeDocker
from tableau.sondes.launchd import SondeLaunchd
from tableau.sondes.logs import LecteurJournaux
from tableau.sondes.processus import SondeProcessus
from tableau.sondes.sqlite_copie import LecteurBases
from tableau.vues import Source

VERSION = "1.0.0"
JOURNAL = logging.getLogger("tableau")
ENTRETIEN_S = 86400
CREDITS_REELS_S = 3600


class DejaLance(Exception):
    """Un autre démon tient déjà le verrou."""


class FiltreCaviardage(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = caviardage.caviarder(record.getMessage(), 600)
        record.args = ()
        return True


def configurer_journal(chemins: config.Chemins) -> None:
    chemins.logs.mkdir(parents=True, exist_ok=True)
    gestionnaire = logging.handlers.RotatingFileHandler(
        chemins.logs / "tableau.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    gestionnaire.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    gestionnaire.addFilter(FiltreCaviardage())
    JOURNAL.handlers[:] = [gestionnaire]
    JOURNAL.setLevel(logging.INFO)
    JOURNAL.propagate = False


@dataclass
class Branchements:
    """Ce que les tests (et le faux écosystème) remplacent : commandes, horloges, notifications, n8n."""

    notificateur: Notificateur = field(default_factory=notifier.choisir)
    launchctl: Callable[[list[str]], systeme.Resultat] | None = None
    docker: Callable[[list[str]], systeme.Resultat] | None = None
    healthz: Callable[[int], tuple[bool, str]] = docker_n8n.healthz
    mur: Callable[[], float] = time.time
    mono: Callable[[], float] = time.monotonic
    uid: int | None = None
    charge_du_mac: Callable[[], dict[str, float]] = processus.charge_du_mac
    surveiller_fichiers: bool = True


class Demon:
    def __init__(self, chemins: config.Chemins, reglages: config.Reglages, b: Branchements | None = None) -> None:
        self.chemins = chemins
        self.reglages = reglages
        self.b = b or Branchements()
        chemins.preparer()
        self.base = Base(chemins.base)
        self.intervalle = float(reglages["intervalles"]["sante_s"])
        self.horloge = planif.Horloge(self.base, self.b.mur, self.b.mono, self.intervalle)
        self.echeancier = planif.Echeancier()
        mur = self.b.mur
        self.ctx = Contexte(
            chemins=chemins,
            reglages=reglages,
            base=self.base,
            launchd=SondeLaunchd(self.b.launchctl, uid=self.b.uid, horloge=mur),
            processus=SondeProcessus(),
            journaux=LecteurJournaux(self.base, mur),
            bases=LecteurBases(chemins.copies, intervalle_s=float(reglages["intervalles"]["copie_base_s"]),
                               taille_max=int(reglages["seuils"]["copie_max_mo"]) * 1024 * 1024, horloge=mur),
            docker=SondeDocker(self.b.docker, horloge=mur),
            horloge=mur,
            healthz=self.b.healthz,
        )  # fmt: skip
        self.gardien = Gardien(self.base, chemins.maison, chemins.launch_agents, mur)
        self.surveillance = Surveillance(mur)
        self.alertes = Alertes(self.base, reglages, self.b.notificateur, mur)
        self.source = Source(self.base, reglages, chemins, {}, self.gardien, self.alertes, mur)
        self.jeton = config.jeton(chemins)
        self.instantane = Instantane(chemins.icloud, self.jeton)
        self.defs: list[DefModule] = []
        self.etats: list[EtatModule] = []
        self.arret = threading.Event()
        self.disque_plein = False
        self.erreurs_etapes: dict[str, str] = {}
        self.dernier_tour_s = 0.0

    # --- le tour ---------------------------------------------------------------------------------------------------

    def _etape(self, nom: str, faire: Callable[[], Any]) -> Any:
        try:
            resultat = faire()
            self.erreurs_etapes.pop(nom, None)
            return resultat
        except DisquePlein:
            raise
        except Exception as e:  # noqa: BLE001 - une étape en panne n'arrête jamais le démon
            raison = f"{e.__class__.__name__}: {e}"
            if self.erreurs_etapes.get(nom) != raison:
                JOURNAL.warning("étape %s en échec : %s", nom, raison)
            self.erreurs_etapes[nom] = raison
            return None

    def decouvrir(self) -> None:
        d = decouvrir(self.chemins, self.ctx.docker)
        defs, ajoutes, erreurs = registre.synchroniser(self.chemins.registre, self.reglages.prefixe(), d,
                                                       self.chemins.maison)  # fmt: skip
        for e in erreurs:
            JOURNAL.warning("registre : %s", e)
        if ajoutes:
            JOURNAL.info("modules ajoutés au registre : %s", ", ".join(ajoutes))
        change = [m.id for m in defs] != [m.id for m in self.defs]
        self.defs = defs
        self.ctx.modules = defs
        self.source.defs = {m.id: m for m in defs}
        if change and self.b.surveiller_fichiers:
            self.surveillance.arreter()
            n = self.surveillance.demarrer(self.gardien, defs)
            JOURNAL.info("FSEvents : %d dossier(s) de code suivis", n)

    def controler_integrite(self, maintenant: float) -> None:
        tous = self.echeancier.du("integrite", float(self.reglages["intervalles"]["integrite_s"]), maintenant)
        marques = set(self.surveillance.a_controler())
        for defn in self.defs:
            if (defn.perimetre_code or defn.labels) and (tous or defn.id in marques):
                r = self.gardien.controler(defn)
                if r.ecarts:
                    JOURNAL.info("intégrité : %s, %d fichier(s) changé(s)", defn.id, len(r.ecarts))

    def observer(self, maintenant: float) -> list[EtatModule]:
        etats = []
        for defn in self.defs:
            obs = adaptateurs.obtenir(defn.adaptateur).observer(defn, self.ctx)
            verdicts = attentes.evaluer(self.base, defn, obs, maintenant)
            etat = sante.evaluer(defn, obs, verdicts, self.base, self.reglages, maintenant,
                                 self.gardien.etat(defn.id))  # fmt: skip
            etats.append(etat)
        return etats

    def garder(self, etats: list[EtatModule], maintenant: float) -> None:
        with self.base.transaction():
            for e in etats:
                self.base.db.execute(
                    "INSERT OR REPLACE INTO echantillons VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e.id, maintenant, str(e.pastille), e.cpu_pct, e.rss_mo, e.erreurs_24h, None,
                     sum(int(f.get("n") or 0) for f in e.files) if e.files else None),
                )  # fmt: skip
                self.base.db.execute(
                    "INSERT INTO etat_modules (module, json, maj) VALUES (?, ?, ?) ON CONFLICT(module) DO UPDATE "
                    "SET json = excluded.json, maj = excluded.maj",
                    (e.id, json.dumps(e.en_dict(), ensure_ascii=False, default=str), maintenant),
                )
            ids = [e.id for e in etats]
            marques = ",".join("?" * len(ids)) or "''"
            self.base.db.execute(f"DELETE FROM etat_modules WHERE module NOT IN ({marques})", ids)  # noqa: S608
        credits.noter(self.base, etats, maintenant)

    def tour(self) -> list[EtatModule]:
        debut = time.monotonic()
        try:
            t = self.horloge.tour()
            maintenant = t.maintenant
            if t.reveil is not None:
                JOURNAL.info(
                    "réveil ou redémarrage : on laisse %s aux modules", self.reglages["alertes"]["reveil_grace_s"]
                )
            if self.base.lire_meta("premier_tour") is None:
                self.base.ecrire_meta("premier_tour", str(maintenant))
            iv = self.reglages["intervalles"]
            if self.echeancier.du("decouverte", float(iv["decouverte_s"]), maintenant) or not self.defs:
                self._etape("decouverte", self.decouvrir)
            self._etape("integrite", lambda: self.controler_integrite(maintenant))
            self.ctx.nouveau_tour(mesurer_tailles=self.echeancier.du("tailles", float(iv["tailles_s"]), maintenant))
            etats = self._etape("observation", lambda: self.observer(maintenant))
            if etats is None:
                return self.etats
            self.etats = etats
            self._etape("mesures", lambda: self.garder(etats, maintenant))
            self._etape("mac", lambda: self.base.ecrire_meta("mac", json.dumps(self.b.charge_du_mac())))
            if self.reglages["credits"]["api_admin"] and self.echeancier.du(
                "credits_reels", CREDITS_REELS_S, maintenant
            ):
                self._etape("credits_reels", lambda: self.credits_reels(maintenant))
            r = self._etape("rapport", lambda: self.rapport(etats, maintenant))
            if r is not None:
                cle = f"rapport:{time.strftime('%Y-%m-%d', time.localtime(r.fin))}"
                self.alertes.ajouter_info(
                    cle, r.resume + " Le rapport est dans le menu du tableau de bord.", maintenant
                )
            envoi = self._etape("alertes", lambda: self.alertes.traiter(etats, maintenant, [m.id for m in self.defs]))
            if envoi is not None:
                JOURNAL.info("notification %s : %s", "envoyée" if envoi.envoyee else "non affichée",
                             envoi.texte.replace("\n", " · "))  # fmt: skip
            self.source.publier(etats)
            self._etape("etat_json", lambda: self.ecrire_etat_json(etats, maintenant))
            if self.reglages["instantane"]["actif"]:
                self._etape("instantane", lambda: self.ecrire_instantane(etats, maintenant))
            if self.echeancier.du("entretien", ENTRETIEN_S, maintenant):
                self._etape("entretien", lambda: self.entretenir(maintenant))
            self.base.ecrire_meta("battement_demon", str(maintenant))
            self.disque_plein = False
            return etats
        except DisquePlein as e:
            if not self.disque_plein:
                JOURNAL.error("disque plein : tour abandonné (%s)", e)
            self.disque_plein = True
            return self.etats
        finally:
            self.dernier_tour_s = time.monotonic() - debut

    def rapport(self, etats: list[EtatModule], maintenant: float) -> rapport_semaine.Rapport | None:
        return rapport_semaine.faire_si_du(self.base, self.reglages, etats, self.chemins.rapports, maintenant)

    def ecrire_etat_json(self, etats: list[EtatModule], maintenant: float) -> None:
        """`etat.json` : l'état en bref, pour l'assistant ou un autre outil (INTEGRATION.md). Rien de personnel."""
        d = vues.bandeau(etats, self.alertes.retenue(maintenant))
        contenu = {
            "maj": maintenant,
            "bandeau": d["texte"],
            "niveau": d["niveau"],
            "modules": [{"id": e.id, "nom": e.nom, "pastille": str(e.pastille),
                         "phrase": caviardage.caviarder(e.phrase, 200)} for e in etats],
        }  # fmt: skip
        temporaire = self.chemins.etat_json.with_suffix(".tmp")
        descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            json.dump(contenu, f, ensure_ascii=False)
        temporaire.replace(self.chemins.etat_json)

    def ecrire_instantane(self, etats: list[EtatModule], maintenant: float) -> None:
        r = self.instantane.ecrire_si_utile(etats, credits.synthese(self.base, etats, maintenant), maintenant)
        if not r.ecrit and r.motif.startswith("bloqué"):
            JOURNAL.warning("instantané iPhone %s", r.motif)
        self.base.ecrire_meta("instantane", json.dumps({"ts": maintenant, "ecrit": r.ecrit, "motif": r.motif}))

    def credits_reels(self, maintenant: float) -> None:
        cle = credits_reels.lire_cle()
        if not cle:
            self.base.ecrire_meta("credits_reels_motif", "clé Admin absente du trousseau")
            return
        try:
            usd = credits_reels.cout_du_mois(cle, maintenant)
        except credits_reels.CoutReelIndisponible as e:
            self.base.ecrire_meta("credits_reels_motif", str(e))
            return
        mois = time.strftime("%Y-%m", time.localtime(maintenant))
        self.base.ecrire_meta("credits_reels", json.dumps({"mois": mois, "usd": usd, "ts": maintenant}))
        self.base.effacer_meta("credits_reels_motif")

    def entretenir(self, maintenant: float) -> None:
        self.base.entretenir(maintenant)
        rapport_semaine.nettoyer(self.chemins.rapports, maintenant)

    # --- la vie du démon ---------------------------------------------------------------------------------------------

    def boucle(self, tours_max: int | None = None) -> None:
        n = 0
        while not self.arret.is_set():
            self.tour()
            n += 1
            if tours_max is not None and n >= tours_max:
                break
            self.arret.wait(max(1.0, self.intervalle - self.dernier_tour_s))

    def arreter(self) -> None:
        self.arret.set()
        self.surveillance.arreter()

    def fermer(self) -> None:
        self.arreter()
        self.base.fermer()


class Verrou:
    """Un seul démon à la fois : un verrou de fichier, relâché par le système si le démon meurt."""

    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self._fd: int | None = None

    def prendre(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.chemin, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            raise DejaLance(str(self.chemin)) from e
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self._fd = fd

    def rendre(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


def lancer(barre: bool | None = None) -> int:
    """Le point d'entrée du LaunchAgent : `tableau demon`."""
    chemins = config.chemins()
    chemins.preparer()
    configurer_journal(chemins)
    reglages = config.charger(chemins.reglages)
    for e in reglages.erreurs:
        JOURNAL.warning("réglages : %s", e)
    try:
        os.nice(10)
    except OSError:
        pass
    verrou = Verrou(chemins.verrou)
    try:
        verrou.prendre()
    except DejaLance:
        JOURNAL.info("un autre démon tourne déjà : je m'arrête")
        return 0
    demon = Demon(chemins, reglages)
    from tableau.web import serveur as web

    page = web.ouvrir(demon.source, demon.jeton, int(reglages["serveur"]["port"]),
                      lambda p: config.enregistrer_port(p, chemins.reglages)).demarrer()  # fmt: skip
    demon.base.ecrire_meta("port", str(page.port))
    JOURNAL.info("démarré (version %s), page sur 127.0.0.1:%d", VERSION, page.port)

    def sur_signal(_signum: int, _frame: Any) -> None:
        demon.arreter()

    signal.signal(signal.SIGTERM, sur_signal)
    signal.signal(signal.SIGINT, sur_signal)
    try:
        avec_barre = reglages["barre_menus"]["active"] if barre is None else barre
        if avec_barre and systeme.est_un_mac():
            from tableau import barre_menus

            fil = threading.Thread(target=demon.boucle, name="tours", daemon=True)
            fil.start()
            try:
                barre_menus.lancer(demon.source, page.adresse, demon.arret)  # rend la main quand on quitte
            except Exception as e:  # noqa: BLE001 - sans icône (rumps absent, pas de session), le démon continue
                JOURNAL.warning("icône de la barre des menus impossible (%s) : le tableau de bord tourne sans elle",
                                e.__class__.__name__)  # fmt: skip
                while fil.is_alive() and not demon.arret.is_set():
                    demon.arret.wait(60)
            demon.arreter()
            fil.join(timeout=30)
        else:
            demon.boucle()
    finally:
        page.arreter()
        demon.fermer()
        verrou.rendre()
        JOURNAL.info("arrêté proprement")
    return 0
