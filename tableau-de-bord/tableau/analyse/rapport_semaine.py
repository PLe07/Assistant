"""Le rapport de la semaine (dimanche 20 h, réglable) : une page et une notification (§6).

Il dit **ce qui a tourné** (part du temps en bonne santé, attentes tenues ou manquées), **ce qui a coincé** (les
problèmes confirmés, réglés ou encore en cours), **les crédits** (dépensés cette semaine, total du mois, projection,
tendance) et **l'intégrité** (code changé, références acceptées).

- Fait une fois par semaine. Si le Mac dormait à 20 h, il est fait au réveil (rattrapage) ; jamais pour une semaine
  qu'on n'a pas observée au moins un jour.
- La page est autonome (aucune ressource extérieure), lisible au téléphone, en mode clair ou sombre. Elle ne contient
  que nos propres phrases : aucun contenu de journal, aucun chemin personnel.
- Gardée 90 jours dans `rapports/` (lisible par toi seul).
"""

from __future__ import annotations

import html
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau import planif, textes
from tableau.analyse import credits
from tableau.config import Reglages
from tableau.db import Base
from tableau.module import EMOJI, ORDRE, EtatModule, Pastille

SEMAINE = 7 * 86400
GARDE_S = 90 * 86400
GENRES_PROBLEMES = (
    "arrete", "boucle", "fige", "echec", "attente", "file", "pic_erreurs", "budget80", "budget100", "donnees",
    "integrite", "n8n", "cpu",
)  # fmt: skip


@dataclass
class LigneModule:
    id: str
    nom: str
    emoji: str
    pastille: Pastille
    part_vert: float | None  # de 0 à 1, sur le temps observé (hors ⚪)
    tenues: int = 0
    manquees: int = 0
    soucis: int = 0


@dataclass
class Rapport:
    debut: float
    fin: float
    modules: list[LigneModule] = field(default_factory=list)
    soucis: list[dict[str, Any]] = field(default_factory=list)
    credits: dict[str, Any] = field(default_factory=dict)
    credits_semaine: float | None = None
    tendance: str | None = None
    integrite: list[dict[str, Any]] = field(default_factory=list)
    chemin: Path | None = None
    resume: str = ""


def echeance(maintenant: float, jour: int, hhmm: str) -> float:
    """Le dernier « jour à hh:mm » (0 = lundi … 6 = dimanche) passé, à l'heure locale."""
    recul = (time.localtime(maintenant).tm_wday - jour) % 7
    e = planif.echeance_locale(maintenant, hhmm, -recul)
    return e if e <= maintenant else planif.echeance_locale(maintenant, hhmm, -recul - 7)


def du(base: Base, reglages: Reglages, maintenant: float) -> float | None:
    """L'échéance du rapport à faire maintenant (rattrapage compris), ou None."""
    r = reglages["rapport"]
    e = echeance(maintenant, int(r["jour"]), str(r["heure"]))
    fait = float(base.lire_meta("rapport_fait") or 0)
    observe_depuis = float(base.lire_meta("premier_tour") or maintenant)
    if e <= fait or e - observe_depuis < 86400:
        return None
    return e


def _parts(base: Base, module: str, debut: float, fin: float) -> tuple[int, int]:
    """(tours verts, tours observés hors ⚪), mesures brutes et agrégats réunis."""
    brut = base.ligne(
        "SELECT SUM(pastille = 'vert'), SUM(pastille != 'gris') FROM echantillons WHERE module = ? AND ts >= ? "
        "AND ts < ?",
        (module, debut, fin),
    )
    agr = base.ligne(
        "SELECT SUM(vert), SUM(vert + jaune + rouge) FROM agregats WHERE module = ? AND debut >= ? AND debut < ?",
        (module, debut, fin),
    )
    vert = int((brut[0] if brut else 0) or 0) + int((agr[0] if agr else 0) or 0)
    observes = int((brut[1] if brut else 0) or 0) + int((agr[1] if agr else 0) or 0)
    return vert, observes


def _soucis(base: Base, debut: float, fin: float, noms: dict[str, str]) -> list[dict[str, Any]]:
    marques = ",".join("?" * len(GENRES_PROBLEMES))
    confirmes = base.lignes(
        f"SELECT ts, module, genre, gravite, message, details FROM evenements WHERE ts >= ? AND ts < ? "  # noqa: S608
        f"AND genre IN ({marques}) ORDER BY ts",
        (debut, fin, *GENRES_PROBLEMES),
    )
    # Ceux confirmés avant la semaine et encore ouverts au début de la semaine.
    anciens = base.lignes(
        "SELECT confirme_le AS ts, module, genre, gravite, message, cle AS details FROM problemes "
        "WHERE confirme_le IS NOT NULL AND confirme_le < ? AND (resolu_le IS NULL OR resolu_le >= ?)",
        (debut, debut),
    )
    resultat = []
    for r in [*anciens, *confirmes]:
        regle = base.ligne(
            "SELECT ts FROM evenements WHERE genre = 'resolution' AND details = ? AND ts >= ? ORDER BY ts LIMIT 1",
            (r["details"], r["ts"]),
        )
        resultat.append({
            "module": r["module"], "nom": noms.get(r["module"], r["module"]), "gravite": r["gravite"],
            "message": r["message"], "depuis": r["ts"], "regle_le": regle["ts"] if regle else None,
        })  # fmt: skip
    return resultat


def _attentes(base: Base, module: str, debut: float, fin: float) -> tuple[int, int]:
    r = base.ligne(
        "SELECT SUM(statut = 'tenue'), SUM(statut = 'manquee') FROM attentes WHERE module = ? AND echeance >= ? "
        "AND echeance < ?",
        (module, debut, fin),
    )
    return (int(r[0] or 0), int(r[1] or 0)) if r else (0, 0)


def _credits_semaine(base: Base, total: float, mois: str) -> float | None:
    """Dépensé depuis le rapport précédent (on garde le total du mois à chaque rapport)."""
    try:
        avant = json.loads(base.lire_meta("rapport_credits") or "null")
    except ValueError:
        avant = None
    if not isinstance(avant, dict) or "mois" not in avant or "total" not in avant:
        return None
    if avant["mois"] == mois:
        return max(0.0, total - float(avant["total"]))
    fin_mois = float(base.valeur("SELECT SUM(cout_usd) FROM credits WHERE mois = ?", (avant["mois"],), 0.0))
    return max(0.0, fin_mois - float(avant["total"])) + total


def _tendance(semaine: float | None, precedente: float | None) -> str | None:
    if semaine is None or precedente is None:
        return None
    if precedente < 0.05 and semaine < 0.05:
        return "stable"
    if semaine > precedente * 1.2:
        return "en hausse"
    if semaine < precedente * 0.8:
        return "en baisse"
    return "stable"


def construire(base: Base, etats: list[EtatModule], fin: float, maintenant: float | None = None) -> Rapport:
    """Les chiffres de la semaine qui se termine à `fin`."""
    maintenant = fin if maintenant is None else maintenant
    debut = fin - SEMAINE
    rapport = Rapport(debut, fin)
    noms = {e.id: e.nom for e in etats}
    rapport.soucis = _soucis(base, debut, fin, noms)
    for e in sorted(etats, key=lambda x: (ORDRE[x.pastille], x.nom)):
        vert, observes = _parts(base, e.id, debut, fin)
        tenues, manquees = _attentes(base, e.id, debut, fin)
        rapport.modules.append(
            LigneModule(e.id, e.nom, e.emoji, e.pastille, vert / observes if observes else None, tenues, manquees,
                        sum(1 for s in rapport.soucis if s["module"] == e.id))
        )  # fmt: skip
    rapport.credits = credits.synthese(base, etats, maintenant)
    rapport.credits_semaine = _credits_semaine(base, rapport.credits["total_usd"], rapport.credits["mois"])
    precedente = base.lire_meta("rapport_credits_semaine")
    rapport.tendance = _tendance(rapport.credits_semaine, float(precedente) if precedente else None)
    for r in base.lignes("SELECT module, ecarts, reference_le FROM integrite_etat ORDER BY module"):
        try:
            ecarts = json.loads(r["ecarts"] or "[]")
        except ValueError:
            ecarts = []
        acceptees = base.valeur(
            "SELECT COUNT(*) FROM evenements WHERE module = ? AND genre = 'reference' AND ts >= ? AND ts < ?",
            (r["module"], debut, fin),
            0,
        )
        if ecarts or acceptees:
            rapport.integrite.append({
                "module": r["module"], "nom": noms.get(r["module"], r["module"]), "fichiers": len(ecarts),
                "acceptees": int(acceptees),
            })  # fmt: skip
    rapport.resume = resumer(rapport)
    return rapport


def resumer(r: Rapport) -> str:
    suivis = [m for m in r.modules if m.part_vert is not None]
    bien = sum(1 for m in suivis if (m.part_vert or 0) >= 0.95)
    morceaux = [f"{bien} module{'s' if bien > 1 else ''} sur {len(suivis)} ont bien tourné"] if suivis else []
    if r.soucis:
        regles = sum(1 for s in r.soucis if s["regle_le"])
        morceaux.append(f"{textes.pluriel(len(r.soucis), 'souci')} ({regles} réglé{'s' if regles > 1 else ''})")
    else:
        morceaux.append("aucun souci")
    morceaux.append(f"{textes.dollars(r.credits.get('total_usd'))} de crédits ce mois-ci")
    changes = [i for i in r.integrite if i["fichiers"]]
    if changes:
        morceaux.append(f"code changé : {', '.join(i['nom'] for i in changes)}")
    return "📊 Ta semaine : " + ", ".join(morceaux) + "."


def _e(x: Any) -> str:
    return html.escape(str(x), quote=True)


STYLE = """
:root{--fond:#f7f7f5;--carte:#ffffff;--texte:#1d1d1f;--doux:#55555a;--trait:#d8d8dc;--vert:#1e7b34;--rouge:#b3261e}
@media (prefers-color-scheme: dark){:root{--fond:#1c1c1e;--carte:#2c2c2e;--texte:#f2f2f7;--doux:#c7c7cc;
--trait:#48484a;--vert:#5fd17a;--rouge:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--fond);color:var(--texte);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}h1{font-size:1.5rem;margin:.5rem 0}
h2{font-size:1.15rem;margin:1.5rem 0 .5rem}section{background:var(--carte);border:1px solid var(--trait);
border-radius:12px;padding:12px 16px;margin:12px 0}p.resume{font-size:1.05rem}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 4px;border-bottom:1px solid var(--trait);
vertical-align:top}th{color:var(--doux);font-weight:600;font-size:.9rem}td.n{text-align:right;white-space:nowrap}
.doux{color:var(--doux)}.ok{color:var(--vert)}.ko{color:var(--rouge)}ul{padding-left:1.2rem;margin:.25rem 0}
"""


def en_html(r: Rapport) -> str:
    du_au = f"du {time.strftime('%d/%m', time.localtime(r.debut))} au {time.strftime('%d/%m', time.localtime(r.fin))}"
    lignes = []
    for m in r.modules:
        part = "pas observé" if m.part_vert is None else textes.pourcent(m.part_vert * 100)
        attentes = f"{m.tenues} tenue{'s' if m.tenues > 1 else ''}" + (
            f", <span class='ko'>{m.manquees} manquée{'s' if m.manquees > 1 else ''}</span>" if m.manquees else ""
        )
        lignes.append(
            f"<tr><td>{_e(m.emoji)} {_e(m.nom)}</td><td>{EMOJI[m.pastille]}</td><td class='n'>{_e(part)}</td>"
            f"<td>{attentes if (m.tenues or m.manquees) else '—'}</td></tr>"
        )
    soucis = "".join(
        f"<li>{_e(s['message'])} <span class='doux'>({_e(textes.quand(s['depuis'], r.fin))}"
        + (f" · réglé {_e(textes.quand(s['regle_le'], r.fin))}" if s["regle_le"] else " · <b>toujours en cours</b>")
        + ")</span></li>"
        for s in r.soucis
    )
    c = r.credits
    semaine = "inconnu (premier rapport)" if r.credits_semaine is None else textes.dollars(r.credits_semaine)
    tendance = f" · tendance : {_e(r.tendance)}" if r.tendance else ""
    projection = textes.dollars(c.get("projection_usd")) if c.get("projection_usd") is not None else "trop tôt"
    plafonds = f" sur {textes.dollars(c['plafonds_usd'])} de plafonds" if c.get("plafonds_usd") else ""
    integrite = "".join(
        f"<li>{_e(i['nom'])} : "
        + (f"<span class='ko'>{textes.pluriel(i['fichiers'], 'fichier changé', 'fichiers changés')}</span>, "
           "à vérifier" if i["fichiers"] else "")
        + (f"{', ' if i['fichiers'] else ''}nouvelle référence acceptée" if i["acceptees"] else "")
        + "</li>"
        for i in r.integrite
    )  # fmt: skip
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport de la semaine</title><style>{STYLE}</style></head>
<body><main>
<h1>Rapport de la semaine</h1><p class="doux">{_e(du_au)}</p>
<p class="resume">{_e(r.resume)}</p>
<section><h2>Ce qui a tourné</h2>
<table><thead><tr><th scope="col">Module</th><th scope="col">Maintenant</th><th scope="col">En bonne santé</th>
<th scope="col">Attentes</th></tr></thead><tbody>{"".join(lignes)}</tbody></table></section>
<section><h2>Ce qui a coincé</h2>{f"<ul>{soucis}</ul>" if soucis else "<p class='ok'>Rien : tout a tourné.</p>"}
</section>
<section><h2>Crédits Claude</h2>
<p>Cette semaine : <b>{_e(semaine)}</b>{tendance}<br>
Ce mois-ci : {_e(textes.dollars(c.get("total_usd")))}{_e(plafonds)} · projection fin de mois : {_e(projection)}</p>
</section>
<section><h2>Intégrité</h2>{f"<ul>{integrite}</ul>" if integrite else "<p class='ok'>Aucun code changé.</p>"}
</section>
</main></body></html>
"""


def ecrire(r: Rapport, dossier: Path) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"semaine-{time.strftime('%Y-%m-%d', time.localtime(r.fin))}.html"
    temporaire = chemin.with_suffix(".tmp")
    descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descripteur, "w", encoding="utf-8") as f:
        f.write(en_html(r))
    temporaire.replace(chemin)
    r.chemin = chemin
    return chemin


def nettoyer(dossier: Path, maintenant: float) -> int:
    n = 0
    for f in dossier.glob("semaine-*.html"):
        try:
            if maintenant - f.stat().st_mtime > GARDE_S:
                f.unlink()
                n += 1
        except OSError:
            continue
    return n


def dernier(dossier: Path) -> Path | None:
    rapports = sorted(dossier.glob("semaine-*.html"))
    return rapports[-1] if rapports else None


def faire_si_du(
    base: Base, reglages: Reglages, etats: list[EtatModule], dossier: Path, maintenant: float
) -> Rapport | None:
    """Le rapport hebdomadaire s'il est dû : la page, et ce qu'il faut retenir pour la semaine suivante."""
    e = du(base, reglages, maintenant)
    if e is None:
        return None
    r = construire(base, etats, e, maintenant)
    ecrire(r, dossier)
    nettoyer(dossier, maintenant)
    base.ecrire_meta("rapport_fait", str(e))
    base.ecrire_meta("rapport_credits", json.dumps({"mois": r.credits["mois"], "total": r.credits["total_usd"]}))
    if r.credits_semaine is not None:
        base.ecrire_meta("rapport_credits_semaine", str(r.credits_semaine))
    base.noter_evenement(maintenant, "tableau", "rapport", "info", r.resume)
    return r
