"""L'adaptateur de base (et générique) : état launchd, processus, journaux, files, tailles.

Chaque étape est isolée : une étape qui rencontre un format inattendu (colonne renommée, table absente, fichier
illisible) est notée « inconnue » dans l'observation, avec la raison technique ; les autres continuent. Un
adaptateur ne lève jamais d'exception.
"""

from __future__ import annotations

import json
import plistlib
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tableau.adaptateurs.contexte import Contexte
from tableau.caviardage import caviarder
from tableau.module import DefModule, Observation, StatsLogs
from tableau.sondes import files_attente, logs, tailles
from tableau.sondes.logs import Ligne
from tableau.sondes.sqlite_copie import colonnes, signature, tables

Etape = Callable[[DefModule, Contexte, Observation], None]


class Adaptateur:
    nom = "generique"
    battement_periode_s: float | None = None

    # --- l'enchaînement ---------------------------------------------------------------------------------------------

    def observer(self, defn: DefModule, ctx: Contexte) -> Observation:
        obs = Observation()
        try:
            obs.installe = self.est_installe(defn, ctx)
        except Exception as e:  # noqa: BLE001 - un adaptateur ne plante jamais
            obs.installe = False
            obs.technique["erreurs"] = {"installation": _raison(e)}
        if not obs.installe:
            return obs
        for nom, etape in self.etapes():
            try:
                etape(defn, ctx, obs)
            except Exception as e:  # noqa: BLE001 - une étape en panne n'emporte pas les autres
                obs.inconnus.append(nom)
                obs.technique.setdefault("erreurs", {})[nom] = _raison(e)
        return obs

    def etapes(self) -> list[tuple[str, Etape]]:
        return [
            ("launchd", self.lire_launchd),
            ("processus", self.lire_processus),
            ("journaux", self.lire_journaux),
            ("files", self.lire_files),
            ("tailles", self.lire_tailles),
            ("base", self.lire_base),
        ]

    # --- installé ? -------------------------------------------------------------------------------------------------

    def plist(self, ctx: Contexte, label: str) -> Path:
        return ctx.chemins.launch_agents / f"{label}.plist"

    def est_installe(self, defn: DefModule, ctx: Contexte) -> bool:
        if any(self.plist(ctx, label).exists() for label in defn.labels):
            return True
        liste = ctx.launchd.liste()
        return liste is not None and any(label in liste for label in defn.labels)

    # --- launchd et processus ---------------------------------------------------------------------------------------

    def lire_launchd(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        for label in defn.labels:
            etat = ctx.launchd.etat(label)
            if etat is None:
                obs.inconnus.append("launchd")
                obs.technique["launchd"] = ctx.launchd.erreur or "launchctl ne répond pas"
                return
            obs.launchd.append(etat)
            if defn.doit_tourner:
                # Un agent périodique est relancé à chaque passage : ce ne sont pas des plantages.
                noter_lancements(ctx, defn.id, label, etat.lancements, obs)

    def pids(self, defn: DefModule, ctx: Contexte, obs: Observation) -> list[int]:
        return [e.pid for e in obs.launchd if e.pid]

    def lire_processus(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        pids = self.pids(defn, ctx, obs)
        obs.processus = ctx.processus.mesurer(defn.id, pids) if pids else None
        if not pids:
            ctx.processus.oublier(defn.id)

    # --- journaux ---------------------------------------------------------------------------------------------------

    def fichiers_journaux(self, defn: DefModule, ctx: Contexte) -> list[Path]:
        fichiers: list[Path] = []
        for brut in defn.logs:
            chemin = ctx.chemin(defn, brut)
            if chemin is not None:
                fichiers.append(chemin)
        for label in defn.labels:
            for cle in ("StandardErrorPath", "StandardOutPath"):
                valeur = lire_plist(self.plist(ctx, label)).get(cle)
                if isinstance(valeur, str) and valeur:
                    fichiers.append(Path(valeur))
        dossier = ctx.chemin(defn, defn.dossier_logs)
        if dossier is not None and dossier.is_dir():
            fichiers.extend(sorted(dossier.glob("*.log")))
        uniques: list[Path] = []
        for f in fichiers:
            if f not in uniques:
                uniques.append(f)
        return uniques

    def lignes(self, defn: DefModule, ctx: Contexte) -> list[Ligne]:
        resultat: list[Ligne] = []
        for f in self.fichiers_journaux(defn, ctx):
            resultat.extend(ctx.journaux.nouvelles_lignes(f))
        return resultat

    def lire_journaux(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        lignes = self.lignes(defn, ctx)
        logs.compter(ctx.base, defn.id, lignes, ctx.maintenant)
        logs.nettoyer_dernieres_erreurs(ctx.base, defn.id)
        dates = [lg.ts for lg in lignes if lg.ts is not None]
        if dates:
            ctx.base.ecrire_meta(f"derniere_ligne:{defn.id}", str(max(dates)))
        self.apres_lignes(defn, ctx, obs, lignes)
        s = logs.statistiques(ctx.base, defn.id, ctx.maintenant)
        derniere = ctx.base.lire_meta(f"derniere_ligne:{defn.id}")
        obs.logs = StatsLogs(
            erreurs_1h=int(s["erreurs_1h"] or 0),
            erreurs_24h=int(s["erreurs_24h"] or 0),
            avert_1h=int(s["avert_1h"] or 0),
            avert_24h=int(s["avert_24h"] or 0),
            derniere_erreur=s["derniere_erreur"] if isinstance(s["derniere_erreur"], str) else None,
            derniere_erreur_ts=float(s["derniere_erreur_ts"]) if s["derniere_erreur_ts"] is not None else None,
            derniere_ligne_ts=float(derniere) if derniere else None,
        )
        obs.technique["moyenne_erreurs_horaire_7j"] = s["moyenne_horaire_7j"]
        if obs.activite is None:
            obs.activite = lire_activite(ctx, defn.id)

    def apres_lignes(self, defn: DefModule, ctx: Contexte, obs: Observation, lignes: list[Ligne]) -> None:
        """Ce qu'un adaptateur tire des nouvelles lignes (« dernière facture classée »…)."""

    # --- files et tailles -------------------------------------------------------------------------------------------

    def lire_files(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        for brut in defn.files:
            chemin = ctx.chemin(defn, brut)
            if chemin is None:
                continue
            f = files_attente.mesurer(chemin, ctx.base, ctx.maintenant, nom_de_file(brut, chemin))
            if f is not None:
                if f.seuil_min is None and defn.file_max_min:
                    f.seuil_min = defn.file_max_min  # le seuil propre au module, s'il en a un
                obs.files.append(f)

    def dossiers_donnees(self, defn: DefModule, ctx: Contexte) -> list[Path]:
        resultat = [ctx.chemin(defn, defn.dossier_donnees)]
        resultat += [p.parent for p in (ctx.chemin(defn, b) for b in defn.bases) if p is not None]
        return [p for p in resultat if p is not None]

    def lire_tailles(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        if not ctx.mesurer_tailles:
            return
        donnees = tailles.taille(self.dossiers_donnees(defn, ctx))
        journaux = tailles.taille([f for f in self.fichiers_journaux(defn, ctx) if f.exists()])
        tailles.noter(ctx.base, defn.id, ctx.maintenant, donnees, journaux)
        obs.tailles = (donnees or 0, journaux or 0)

    # --- base du module (copie) -------------------------------------------------------------------------------------

    def lire_base(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        """Rien pour l'adaptateur générique : il ne connaît pas le format des bases."""

    def chemin_base(self, defn: DefModule, ctx: Contexte, indice: int = 0) -> Path | None:
        if len(defn.bases) <= indice:
            return None
        return ctx.chemin(defn, defn.bases[indice])

    def battement_par_fichier(self, chemin: Path | None) -> float | None:
        """Entre deux copies : la date de la dernière écriture de la base (sans l'ouvrir)."""
        return signature(chemin).derniere_ecriture if chemin is not None else None


# --- outils communs ---------------------------------------------------------------------------------------------------


def _raison(e: BaseException) -> str:
    return f"{e.__class__.__name__} : {caviarder(str(e), 200)}"


_PLISTS: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}


def lire_plist(chemin: Path) -> dict[str, Any]:
    """Un plist de LaunchAgent (lecture seule), relu seulement s'il a changé."""
    try:
        st = chemin.stat()
    except OSError:
        return {}
    cle = (st.st_mtime_ns, st.st_size)
    memo = _PLISTS.get(str(chemin))
    if memo is not None and memo[0] == cle:
        return memo[1]
    try:
        with open(chemin, "rb") as f:
            donnees = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException, ValueError, TypeError):
        donnees = {}
    resultat = donnees if isinstance(donnees, dict) else {}
    _PLISTS[str(chemin)] = (cle, resultat)
    return resultat


def nom_de_file(brut: str, chemin: Path) -> str:
    if brut.startswith("icloud:"):
        return f"iCloud/{brut[len('icloud:') :]}"
    if brut.startswith("~/"):
        return brut
    return chemin.name


def noter_lancements(ctx: Contexte, module: str, label: str, lancements: int | None, obs: Observation) -> None:
    """`runs` de launchd a augmenté depuis le tour précédent : autant de relances, notées à cet instant."""
    if lancements is None:
        return
    cle = f"runs:{label}"
    avant = ctx.base.lire_meta(cle)
    ctx.base.ecrire_meta(cle, str(lancements))
    if avant is None:
        return
    try:
        ecart = lancements - int(avant)
    except ValueError:
        return
    if ecart <= 0:
        return  # premier passage, ou compteur remis à zéro (Mac redémarré, agent rechargé)
    instants = [ctx.maintenant - i * 0.001 for i in range(min(ecart, 50))]
    noter_relances(ctx, module, instants)
    obs.relances.extend(instants)


def noter_relances(ctx: Contexte, module: str, instants: list[float]) -> None:
    if instants:
        ctx.base.plusieurs("INSERT OR IGNORE INTO relances (module, ts) VALUES (?, ?)", [(module, t) for t in instants])


def retenir_activite(ctx: Contexte, module: str, texte: str, ts: float) -> None:
    ancienne = lire_activite(ctx, module)
    if ancienne is None or ts >= ancienne[1]:
        ctx.base.ecrire_meta(f"activite:{module}", json.dumps([texte, ts], ensure_ascii=False))


def lire_activite(ctx: Contexte, module: str) -> tuple[str, float] | None:
    brut = ctx.base.lire_meta(f"activite:{module}")
    if not brut:
        return None
    try:
        texte, ts = json.loads(brut)
        return str(texte), float(ts)
    except (ValueError, TypeError):
        return None


def mois_courant(ctx: Contexte) -> str:
    import time as _time

    return _time.strftime("%Y-%m", _time.localtime(ctx.maintenant))


def debut_du_mois(ctx: Contexte) -> float:
    import time as _time

    t = _time.localtime(ctx.maintenant)
    return _time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1))


def somme_couts(db: sqlite3.Connection, table: str, mois: str, debut_mois: float) -> float | None:
    """Le coût du mois dans une table de dépenses, quel que soit son nom de colonne de date (tolérant)."""
    if table not in tables(db):
        return None
    cols = colonnes(db, table)
    montant = next((c for c in ("cout_usd", "cout", "montant_usd", "cost_usd") if c in cols), None)
    if montant is None:
        return None
    if "mois" in cols:
        r = db.execute(f'SELECT COALESCE(SUM("{montant}"), 0) FROM "{table}" WHERE mois = ?', (mois,)).fetchone()
        return float(r[0])
    date = next((c for c in ("date", "quand", "ts", "horodatage") if c in cols), None)
    if date is None:
        return None
    r = db.execute(f'SELECT COALESCE(SUM("{montant}"), 0) FROM "{table}" WHERE "{date}" >= ?', (debut_mois,)).fetchone()
    return float(r[0])


def valeur_cle(db: sqlite3.Connection, table: str, cle: str) -> Any:
    """Une valeur d'une table clé/valeur (`meta`, `etat`, `cles`) ; JSON décodé si c'en est ; None si absente."""
    if table not in tables(db):
        return None
    cols = colonnes(db, table)
    if not {"cle", "valeur"} <= cols:
        return None
    r = db.execute(f'SELECT valeur FROM "{table}" WHERE cle = ?', (cle,)).fetchone()
    if r is None or r[0] is None:
        return None
    try:
        return json.loads(r[0])
    except (ValueError, TypeError):
        return r[0]


def en_nombre(valeur: Any) -> float | None:
    try:
        return float(valeur) if valeur is not None and not isinstance(valeur, bool) else None
    except (TypeError, ValueError):
        return None


Generique = Adaptateur
