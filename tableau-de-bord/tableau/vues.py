"""Ce que montrent la page, la CLI, l'instantané iPhone et la barre des menus : une seule source.

`Source` réunit ce que le démon sait (états des modules publiés à chaque tour, notre base, le registre, le gardien,
les alertes). Les fonctions de ce fichier en tirent des dictionnaires simples, déjà caviardés : chaque interface les
met en forme à sa façon. Rien ici n'écrit chez un autre module ; les seules actions (nouvelle référence, sourdine,
diagnostic à la demande) sont des méthodes explicites de `Source`.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

from tableau import caviardage, systeme, textes
from tableau.analyse import attentes, credits, ressources
from tableau.analyse.alertes import Alertes, lire_duree
from tableau.analyse.integrite import Gardien
from tableau.config import Chemins, Reglages
from tableau.db import Base
from tableau.module import EMOJI, LIBELLE, ORDRE, DefModule, EtatModule, Pastille
from tableau.web.sse import Diffuseur

JOUR = 86400
SORTIE_DIAGNOSTIC_MAX = 6000


class Source:
    def __init__(
        self,
        base: Base,
        reglages: Reglages,
        chemins: Chemins,
        defs: dict[str, DefModule],
        gardien: Gardien,
        alertes_: Alertes,
        horloge: Callable[[], float] = time.time,
    ) -> None:
        self.base = base
        self.reglages = reglages
        self.chemins = chemins
        self.defs = defs
        self.gardien = gardien
        self.alertes = alertes_
        self.horloge = horloge
        self.diffuseur = Diffuseur()
        self._verrou = threading.Lock()
        self._etats: list[EtatModule] | None = None
        self._actions = threading.Lock()  # une action à la fois (deux clics rapides ne lancent pas deux diagnostics)

    # --- états publiés -----------------------------------------------------------------------------------------------

    def publier(self, etats: list[EtatModule]) -> int:
        with self._verrou:
            self._etats = list(etats)
        return self.diffuseur.publier()

    def etats(self) -> list[EtatModule]:
        with self._verrou:
            etats = self._etats
        if etats is None:
            etats = [EtatModule.depuis_dict(d) for d in self.base.etats_modules().values()]
        return sorted(etats, key=lambda e: (ORDRE[e.pastille], e.nom.lower()))

    def etat(self, module: str) -> EtatModule | None:
        return next((e for e in self.etats() if e.id == module), None)

    # --- actions (POST avec le jeton, ou la CLI) ---------------------------------------------------------------------

    def nouvelle_reference(self, module: str) -> str:
        defn = self.defs.get(module)
        if defn is None:
            raise KeyError(module)
        with self._actions:
            n = self.gardien.prendre_reference(defn)
            maintenant = self.horloge()
            self.alertes.accepter(module, maintenant)
            self.base.noter_evenement(maintenant, module, "reference", "info", f"Nouvelle référence : {n} fichiers")
        self.diffuseur.publier()
        return f"C'est noté : le code actuel de {defn.nom} devient la référence ({textes.pluriel(n, 'fichier')})."

    def pas_normal(self, module: str) -> dict[str, Any]:
        defn = self.defs.get(module)
        if defn is None:
            raise KeyError(module)
        etat = self.gardien.etat(module) or {}
        self.base.noter_evenement(
            self.horloge(), module, "pas_normal", "attention", "Code changé signalé « pas normal »"
        )
        return {
            "message": "Rien n'a été restauré. Pour voir les changements, lance toi-même dans le Terminal :",
            "commande": self.gardien.commande_diff(defn),
            "ecarts": etat.get("ecarts", []),
        }

    def sourdine(self, texte: str) -> str:
        duree = lire_duree(texte)
        if duree is None:
            raise ValueError("durée illisible (exemples : 1h, 30min, 2h30, fin)")
        fin = self.alertes.sourdine(duree, self.horloge())
        self.diffuseur.publier()
        return "Sourdine levée." if fin is None else f"Alertes en sourdine jusqu'à {textes.heure(fin)}."

    def diagnostic(self, module: str, demande: systeme.DemandeExplicite) -> dict[str, Any]:
        """La commande de diagnostic du module, à ta demande seulement ; sa sortie, caviardée."""
        defn = self.defs.get(module)
        if defn is None:
            raise KeyError(module)
        if not defn.commande_diagnostic:
            return {"ok": False, "sortie": "Pas de commande de diagnostic connue pour ce module."}
        dossier = defn.chemin(defn.dossier_projet, self.chemins.maison) if defn.dossier_projet else None
        if dossier is None or not dossier.is_dir():
            return {"ok": False, "sortie": "Le dossier du module est introuvable."}
        with self._actions:
            r = systeme.executer_diagnostic(defn.commande_diagnostic, dossier, demande)
        sortie = (r.sortie + ("\n" + r.erreur if r.erreur else "")).strip()
        propre = "\n".join(caviardage.caviarder(ligne, 300, compacter=False) for ligne in sortie.splitlines())
        self.base.noter_evenement(self.horloge(), module, "diagnostic", "info", f"Diagnostic lancé (code {r.code})")
        return {"ok": r.ok, "code": r.code, "sortie": propre[-SORTIE_DIAGNOSTIC_MAX:]}


# --- accueil -----------------------------------------------------------------------------------------------------


def bandeau(etats: list[EtatModule], retenue: str | None = None) -> dict[str, Any]:
    a_regarder = sum(max(1, len(e.problemes)) for e in etats if e.pastille in (Pastille.ROUGE, Pastille.JAUNE))
    if a_regarder == 0:
        texte, niveau = "✅ Tout va bien", "vert"
    else:
        niveau = "rouge" if any(e.pastille == Pastille.ROUGE for e in etats) else "jaune"
        texte = f"{'🔴' if niveau == 'rouge' else '🟡'} {textes.pluriel(a_regarder, 'chose')} à regarder"
    return {"texte": texte, "niveau": niveau, "retenue": retenue}


def carte(e: EtatModule) -> dict[str, Any]:
    pct = e.credits_mois / e.plafond_usd * 100 if e.credits_mois is not None and e.plafond_usd else None
    return {
        "id": e.id,
        "nom": e.nom,
        "emoji": e.emoji,
        "pastille": str(e.pastille),
        "pastille_emoji": EMOJI[e.pastille],
        "pastille_libelle": LIBELLE[e.pastille],
        "phrase": caviardage.caviarder(e.phrase, 200),
        "derniere_activite": caviardage.caviarder(e.derniere_activite or "", 120) or None,
        "erreurs_24h": e.erreurs_24h,
        "cpu_pct": e.cpu_pct,
        "rss_mo": e.rss_mo,
        "credits_mois": e.credits_mois,
        "plafond_usd": e.plafond_usd,
        "credits_pct": pct,
        "credits_estimes": (e.technique or {}).get("credits_source") == "estimation",
        "prochaine": e.prochaine,
    }


def accueil(source: Source) -> dict[str, Any]:
    etats = source.etats()
    maintenant = source.horloge()
    return {
        "bandeau": bandeau(etats, source.alertes.retenue(maintenant)),
        "cartes": [carte(e) for e in etats],
        "maj": max((e.maj for e in etats), default=None),
    }


# --- détail d'un module ------------------------------------------------------------------------------------------


def series(base: Base, module: str, jours: int, maintenant: float) -> list[dict[str, Any]]:
    """Un point par jour local : part du temps en 🟢, erreurs, processeur et mémoire moyens (None : pas observé)."""
    from tableau.planif import debut_du_jour

    premier = debut_du_jour(maintenant - (jours - 1) * JOUR)
    bornes = [debut_du_jour(premier + i * JOUR + 3 * 3600) for i in range(jours)] + [maintenant + 1]
    resultat = []
    for i in range(jours):
        a, b = bornes[i], bornes[i + 1]
        r1 = base.ligne(
            "SELECT COUNT(*), SUM(pastille = 'vert'), SUM(pastille != 'gris'), AVG(cpu), AVG(rss_mo) "
            "FROM echantillons WHERE module = ? AND ts >= ? AND ts < ?",
            (module, a, b),
        )
        r2 = base.ligne(
            "SELECT SUM(n), SUM(vert), SUM(vert + jaune + rouge), SUM(cpu_moy * n), SUM(rss_moy * n) "
            "FROM agregats WHERE periode = 'h' AND module = ? AND debut >= ? AND debut < ?",
            (module, a, b),
        )
        n = int((r1[0] if r1 else 0) or 0) + int((r2[0] if r2 else 0) or 0)
        vert = int((r1[1] if r1 else 0) or 0) + int((r2[1] if r2 else 0) or 0)
        observes = int((r1[2] if r1 else 0) or 0) + int((r2[2] if r2 else 0) or 0)
        cpu_somme = float((r1[3] or 0) * (r1[0] or 0) if r1 else 0) + float((r2[3] if r2 else 0) or 0)
        rss_somme = float((r1[4] or 0) * (r1[0] or 0) if r1 else 0) + float((r2[4] if r2 else 0) or 0)
        erreurs = base.valeur(
            "SELECT SUM(erreurs) FROM compteurs_logs WHERE module = ? AND heure >= ? AND heure < ?", (module, a, b)
        )
        resultat.append({
            "jour": a,
            "etiquette": time.strftime("%d/%m", time.localtime(a)),
            "part_vert": vert / observes * 100 if observes else None,
            "erreurs": int(erreurs) if erreurs is not None else None,
            "cpu_moy": cpu_somme / n if n else None,
            "rss_moy": rss_somme / n if n else None,
        })  # fmt: skip
    return resultat


def detail(source: Source, module: str, jours: int = 7) -> dict[str, Any] | None:
    e = source.etat(module)
    defn = source.defs.get(module)
    if e is None and defn is None:
        return None
    maintenant = source.horloge()
    if e is None:
        assert defn is not None
        e = EtatModule(defn.id, defn.nom, defn.emoji, Pastille.GRIS, "Pas encore observé")
    jours = 30 if jours >= 30 else 7
    erreurs = [
        {"ts": r["ts"], "quand": textes.quand(r["ts"], maintenant), "message": caviardage.caviarder(r["message"], 300)}
        for r in source.base.lignes(
            "SELECT ts, message FROM dernieres_erreurs WHERE module = ? ORDER BY ts DESC LIMIT 10", (module,)
        )
    ]
    integ = source.gardien.etat(module)
    return {
        "carte": carte(e),
        "problemes": [{"gravite": p.gravite, "message": caviardage.caviarder(p.message, 300)} for p in e.problemes],
        "attentes": e.attentes,
        "historique_attentes": [
            {**h, "quand": textes.quand(h["echeance"], maintenant)}
            for h in reversed(attentes.historique(source.base, module, maintenant - jours * JOUR))
        ][:30],
        "files": e.files,
        "jours": jours,
        "series": series(source.base, module, jours, maintenant),
        "erreurs": erreurs,
        "integrite": integ,
        "commande_diff": source.gardien.commande_diff(defn) if defn else None,
        "diagnostic": bool(defn and defn.commande_diagnostic),
        "aide": defn.aide if defn else "",
    }


# --- vues transverses --------------------------------------------------------------------------------------------


def vue_credits(source: Source) -> dict[str, Any]:
    maintenant = source.horloge()
    reel = None
    brut = source.base.lire_meta("credits_reels")
    if brut:
        try:
            donnees = json.loads(brut)
            if donnees.get("mois") == time.strftime("%Y-%m", time.localtime(maintenant)):
                reel = float(donnees["usd"])
        except (ValueError, KeyError, TypeError):
            reel = None
    s = credits.synthese(source.base, source.etats(), maintenant, reel_usd=reel)
    s["api_admin"] = bool(source.reglages["credits"]["api_admin"])
    return s


def vue_ressources(source: Source) -> dict[str, Any]:
    maintenant = source.horloge()
    try:
        mac = json.loads(source.base.lire_meta("mac") or "null")
    except ValueError:
        mac = None
    b = ressources.bilan(source.etats(), mac if isinstance(mac, dict) else None, source.reglages,
                         ressources.moyennes(source.base, maintenant - JOUR))  # fmt: skip
    return {
        "phrase": b.phrase,
        "cpu_pct": b.cpu_pct,
        "rss_mo": b.rss_mo,
        "part_cpu_mac": b.part_cpu_mac,
        "part_memoire_mac": b.part_memoire_mac,
        "minutes_batterie_jour": b.minutes_batterie_jour,
        "modules": b.par_module,
    }


def vue_integrite(source: Source) -> list[dict[str, Any]]:
    maintenant = source.horloge()
    lignes = []
    for defn in sorted(source.defs.values(), key=lambda d: d.nom.lower()):
        if not defn.perimetre_code and not defn.labels:
            continue
        etat = source.gardien.etat(defn.id)
        ecarts = (etat or {}).get("ecarts", [])
        lignes.append({
            "id": defn.id,
            "nom": defn.nom,
            "emoji": defn.emoji,
            "statut": "pas encore de référence" if etat is None else ("changé" if ecarts else "conforme"),
            "ecarts": ecarts,
            "reference": textes.quand(etat["reference_le"], maintenant) if etat and etat["reference_le"] else None,
            "controle": textes.il_y_a(etat["controle_le"], maintenant) if etat and etat["controle_le"] else None,
            "commit_change": bool(etat and etat["commit_change"]),
            "commande_diff": source.gardien.commande_diff(defn),
        })  # fmt: skip
    return lignes


def journal(source: Source, module: str | None = None, jours: int = 7, limite: int = 200) -> list[dict[str, Any]]:
    maintenant = source.horloge()
    noms = {d.id: d.nom for d in source.defs.values()}
    noms["tableau"] = "Tableau de bord"
    return [
        {
            "ts": r["ts"],
            "quand": textes.quand(r["ts"], maintenant),
            "module": r["module"],
            "nom": noms.get(r["module"], r["module"]),
            "genre": r["genre"],
            "gravite": r["gravite"],
            "message": caviardage.caviarder(r["message"], 300),
        }
        for r in source.base.evenements(maintenant - jours * JOUR, module, limite)
    ]
