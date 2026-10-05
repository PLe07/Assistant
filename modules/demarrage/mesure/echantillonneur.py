"""L'échantillonneur : un relevé = ps (processeur cumulé, mémoire), le PID de chaque label launchd, qui empêche la
veille (pmset), et parfois l'énergie (top). Chaque processus est rattaché à son élément ; on garde, par élément et
par relevé, le processeur consommé depuis le relevé précédent, la mémoire, l'énergie et la veille empêchée.

Modes : « session » (toutes les 5 s pendant les 5 minutes après la connexion), « croisiere » (toutes les 2 min,
énergie toutes les 10 min), « mesure » (`demarrage mesurer`, ponctuel et intensif).
"""

from __future__ import annotations

import gc
import logging
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from modules.demarrage.collecteurs import ouverture_session
from modules.demarrage.collecteurs.launchd_etat import analyser_list
from modules.demarrage.db import Base, DisquePlein
from modules.demarrage.mesure import energie, session, veille
from modules.demarrage.mesure.rattachement import Proc, rattacher
from modules.demarrage.modele import Fiche
from modules.demarrage.systeme import Systeme

log = logging.getLogger("demarrage")

COMMANDE_PS = ["ps", "-axo", "pid=,ppid=,uid=,%cpu=,rss=,etime=,time=,comm=", "-ww"]
MEME_PROCESSUS_S = 2.0  # un PID réutilisé par un autre processus : son heure de lancement change
_ETIME = re.compile(r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$")


def duree_ps(texte: str) -> float | None:
    """etime : [[jj-]hh:]mm:ss → secondes."""
    m = _ETIME.match(texte.strip())
    if not m:
        return None
    j, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return j * 86400 + h * 3600 + mi * 60 + s


def temps_ps(texte: str) -> float | None:
    """time : [jj-][hh:]mm:ss.cc (minutes parfois au-delà de 59) → secondes de processeur."""
    texte = texte.strip()
    jours = 0
    if "-" in texte:
        j, _, texte = texte.partition("-")
        if not j.isdigit():
            return None
        jours = int(j)
    morceaux = texte.split(":")
    try:
        valeurs = [float(x) for x in morceaux]
    except ValueError:
        return None
    if not 1 <= len(valeurs) <= 3:
        return None
    total = 0.0
    for v in valeurs:
        total = total * 60 + v
    return jours * 86400 + total


def analyser_ps(texte: str) -> list[Proc]:
    procs: list[Proc] = []
    for ligne in texte.splitlines():
        mots = ligne.split(None, 7)
        if len(mots) != 8 or not (mots[0].isdigit() and mots[1].isdigit()):
            continue
        age, cpu_s = duree_ps(mots[5]), temps_ps(mots[6])
        try:
            uid, cpu, rss = int(mots[2]), float(mots[3].replace(",", ".")), int(mots[4])
        except ValueError:
            continue
        if age is None or cpu_s is None:
            continue
        procs.append(Proc(int(mots[0]), int(mots[1]), uid, cpu, rss, age, cpu_s, mots[7].strip()))
    return procs


@dataclass
class Releve:
    ts: float
    mode: str
    cpu_total_pct: float | None  # % de la capacité totale (tous les cœurs), depuis le relevé précédent
    par_fiche: dict[str, dict[str, Any]] = field(default_factory=dict)  # id → cpu_s, rss_ko, puissance, veille
    procs: list[Proc] = field(default_factory=list)


class Echantillonneur:
    def __init__(
        self,
        systeme: Systeme,
        base: Base,
        reglages: dict[str, Any],
        fiches: Callable[[], list[Fiche]],
    ):
        self.systeme = systeme
        self.base = base
        self.reglages = reglages
        self.fiches = fiches  # les fiches du dernier scan (relues si un nouveau scan arrive)
        self.precedent: dict[int, tuple[float, float]] = {}  # pid → (lancement estimé, temps processeur cumulé)
        self.precedent_ts: float | None = None
        self._coeurs: int | None = None
        self.disque_plein = False

    @property
    def coeurs(self) -> int:
        if self._coeurs is None:
            r = self.systeme.executer(["sysctl", "-n", "hw.ncpu"], delai=5)
            n = r.sortie.strip()
            self._coeurs = int(n) if r.ok and n.isdigit() and int(n) > 0 else 1
        return self._coeurs

    def _pids_launchd(self) -> dict[str, int]:
        r = self.systeme.executer(["launchctl", "list"], delai=self.reglages["delais"]["commande_s"])
        if not r.ok:
            return {}
        return {label: s.pid for label, s in analyser_list(r.sortie).items() if s.pid}

    def prendre(self, mode: str, avec_energie: bool = False, depuis: float | None = None) -> Releve | None:
        """Un relevé. depuis : un processus lancé après cet instant compte en entier dès sa première apparition
        (au premier relevé d'une session : l'heure de connexion)."""
        ts = self.systeme.maintenant()
        r = self.systeme.executer(COMMANDE_PS, delai=self.reglages["delais"]["commande_s"])
        if not r.ok:
            log.warning("[demarrage] ps indisponible : %s", r.erreur.strip()[:120])
            return None
        procs = analyser_ps(r.sortie)
        reference = self.precedent_ts if self.precedent_ts is not None else depuis
        actuel: dict[int, tuple[float, float]] = {}
        deltas: dict[int, float] = {}
        for p in procs:
            lancement = ts - p.age_s  # etime est arrondi à la seconde : ±1 s d'un relevé à l'autre
            actuel[p.pid] = (lancement, p.cpu_s)
            connu = self.precedent.get(p.pid)
            ancien = connu[1] if connu and abs(connu[0] - lancement) <= MEME_PROCESSUS_S else None
            if ancien is None:
                # Nouveau : il compte en entier s'il est né après le relevé précédent (ou la connexion).
                ne_apres = reference is not None and lancement >= reference - 1
                deltas[p.pid] = p.cpu_s if ne_apres else 0.0
            else:
                deltas[p.pid] = max(0.0, p.cpu_s - ancien)
        cpu_total = None
        if self.precedent_ts is not None and ts > self.precedent_ts:
            cpu_total = 100.0 * sum(deltas.values()) / (ts - self.precedent_ts) / self.coeurs
        self.precedent, self.precedent_ts = actuel, ts

        pmset = self.systeme.executer(["pmset", "-g", "assertions"], delai=self.reglages["delais"]["commande_s"])
        bloqueurs = veille.pids_qui_empechent(veille.analyser(pmset.sortie)) if pmset.ok else set()
        puissances: dict[int, float] = {}
        if avec_energie:
            top = self.systeme.executer(energie.COMMANDE, delai=self.reglages["delais"]["commande_s"] + 5)
            if top.ok:
                puissances = {pid: e.puissance for pid, e in energie.analyser(top.sortie).items()}

        attribution = rattacher(procs, self.fiches(), self._pids_launchd())
        par_fiche: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"cpu_s": 0.0, "rss_ko": 0, "puissance": None, "veille": False, "pids": []}
        )
        for p in procs:
            fid = attribution.get(p.pid)
            if fid is None:
                continue
            m = par_fiche[fid]
            m["cpu_s"] += deltas.get(p.pid, 0.0)
            m["rss_ko"] += p.rss_ko
            m["pids"].append(p.pid)
            if p.pid in bloqueurs:
                m["veille"] = True
            if avec_energie:
                m["puissance"] = (m["puissance"] or 0.0) + puissances.get(p.pid, 0.0)
        releve = Releve(ts, mode, cpu_total, dict(par_fiche), procs)
        self._enregistrer(releve)
        return releve

    def _enregistrer(self, releve: Releve) -> None:
        try:
            self.base.enregistrer_releve(releve.ts, releve.mode, releve.cpu_total_pct, releve.par_fiche)
            self.disque_plein = False
        except DisquePlein:
            if not self.disque_plein:
                log.error("[demarrage] disque plein : les relevés ne sont plus enregistrés (le reste continue)")
            self.disque_plein = True

    def suivre_session(
        self,
        boot: float,
        connexion: float,
        arret: Callable[[], bool] = lambda: False,
        pendant: Callable[[float], None] = lambda t: None,
    ) -> dict[str, Any]:
        """Le mode « ouverture de session » : un relevé toutes les 5 s jusqu'à connexion + 5 min, puis le bilan.
        On note aussi les apps lancées par launchd dans les 2 premières minutes (S5, déduction)."""
        e = self.reglages["echantillonnage"]
        fin = connexion + e["session_minutes"] * 60
        premier = True
        lancements: dict[int, tuple[str, int, float]] = {}
        gc.disable()  # pas de ramasse-miettes au milieu d'une mesure courte et fréquente
        try:
            while self.systeme.maintenant() < fin and not arret():
                releve = self.prendre("session", depuis=connexion if premier else None)
                premier = False
                pendant(self.systeme.maintenant())
                for p in releve.procs if releve else []:
                    apres = releve.ts - p.age_s - connexion if releve else 0.0
                    if p.ppid == 1 and 0 <= apres <= ouverture_session.FENETRE_DEDUCTION_S:
                        lancements.setdefault(p.pid, (p.comm, p.ppid, apres))
                self.systeme.attendre(min(e["session_pas_s"], max(0.0, fin - self.systeme.maintenant())))
        finally:
            gc.enable()
        return self.bilan_session(boot, connexion, ouverture_session.deduire(list(lancements.values())))

    def bilan_session(self, boot: float, connexion: float, apps_lancees: list[str] | None = None) -> dict[str, Any]:
        calme = self.reglages["calme"]
        releves = self.base.releves(connexion, connexion + 3600, modes=("session",))
        jusqua = session.temps_jusquau_calme(
            [(t, c) for t, c in releves if c is not None], connexion, calme["seuil_cpu_pct"], calme["duree_s"]
        )
        bilan = {"demarrage_s": round(connexion - boot, 1), "calme_s": None if jusqua is None else round(jusqua, 1),
                 "releves": len(releves), "apps_lancees": apps_lancees or []}  # fmt: skip
        try:
            self.base.enregistrer_session(boot, connexion, None if jusqua is None else connexion + jusqua, bilan)
        except DisquePlein:
            log.error("[demarrage] disque plein : bilan de session non enregistré")
        return bilan

    def mesurer(self, minutes: float, pas_s: float = 5.0, rappel: Callable[[float], None] | None = None) -> int:
        """La mesure ponctuelle (`demarrage mesurer`) : un relevé toutes les pas_s secondes, l'énergie toutes les
        minutes. Renvoie le nombre de relevés."""
        fin = self.systeme.maintenant() + minutes * 60
        n, derniere_energie = 0, -1e18
        while True:
            maintenant = self.systeme.maintenant()
            avec_energie = maintenant - derniere_energie >= 60
            if self.prendre("mesure", avec_energie=avec_energie) is not None:
                n += 1
            if avec_energie:
                derniere_energie = maintenant
            if rappel:
                rappel(max(0.0, fin - self.systeme.maintenant()))
            if self.systeme.maintenant() >= fin:
                return n
            self.systeme.attendre(min(pas_s, fin - self.systeme.maintenant()))
