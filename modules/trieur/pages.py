"""Les deux pages HTML de la boîte iCloud (§7, §9), lisibles sur l'iPhone dans l'app Fichiers :
- « Mon coffre.html » : tes garanties, la plus proche de sa fin en premier ;
- « Derniers classements.html » : ce que le Trieur a rangé, et ce qui t'attend dans « À vérifier ».

Une seule page autonome chacune : pas de script, pas de police ni de feuille de style externe (aucun réseau),
mode sombre automatique. Une page n'est remplacée que si elle porte la marque du Trieur : un fichier à toi qui
aurait le même nom n'est jamais touché (la page s'appelle alors « … (Trieur).html »).
"""

from __future__ import annotations

import html
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from modules.trieur import config
from modules.trieur.base import Base, Element
from modules.trieur.garanties.coffre import Coffre, Fiche

MARQUE = "<!-- trieur:page -->"
COFFRE = "Mon coffre.html"
DERNIERS = "Derniers classements.html"
LIBELLES = {"classe": "rangé", "a_verifier": "à vérifier", "photos": "photo", "doublon": "doublon", "erreur": "erreur",
            "annule": "annulé", "ignore": "laissé", "en_attente": "en attente", "en_cours": "en cours"}  # fmt: skip

STYLE = """
:root { --fond:#f6f5f2; --carte:#ffffff; --texte:#1d1d1f; --doux:#6e6e73; --ligne:#e3e1dc; --bien:#1f7a4d;
        --alerte:#b45309; --fini:#8e8e93; --accent:#2557a7; }
@media (prefers-color-scheme: dark) {
  :root { --fond:#151517; --carte:#1f1f22; --texte:#f2f2f4; --doux:#a1a1a8; --ligne:#333338; --bien:#4cc38a;
          --alerte:#f2a93b; --fini:#7c7c84; --accent:#7aa7ff; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--fond); color:var(--texte); font:16px/1.45 -apple-system, BlinkMacSystemFont,
       "Helvetica Neue", Arial, sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 20px 16px 48px; }
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.05rem; margin: 28px 0 10px; color: var(--doux); font-weight: 600; }
.sous { color: var(--doux); margin: 0 0 18px; font-size: .92rem; }
.chiffres { display:flex; gap:10px; flex-wrap:wrap; margin-bottom: 8px; }
.chiffre { background:var(--carte); border:1px solid var(--ligne); border-radius:12px; padding:10px 14px;
           min-width:110px; }
.chiffre b { display:block; font-size:1.4rem; }
.chiffre span { color:var(--doux); font-size:.85rem; }
.carte { background:var(--carte); border:1px solid var(--ligne); border-radius:12px; padding:12px 14px;
         margin-bottom:10px; display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.carte .titre { font-weight:600; overflow-wrap:anywhere; }
.carte .meta { color:var(--doux); font-size:.88rem; margin-top:2px; overflow-wrap:anywhere; }
.reste { text-align:right; white-space:nowrap; font-weight:600; }
.reste small { display:block; font-weight:400; color:var(--doux); font-size:.8rem; }
.active .reste { color:var(--bien); } .bientot .reste { color:var(--alerte); } .expiree { opacity:.65; }
.expiree .reste { color:var(--fini); }
.etiquette { display:inline-block; font-size:.75rem; padding:1px 8px; border-radius:999px;
             border:1px solid var(--ligne); color:var(--doux); margin-left:6px; vertical-align:1px; }
.a_verifier .etiquette, .erreur .etiquette { color:var(--alerte); border-color:var(--alerte); }
code { font: .85rem ui-monospace, Menlo, monospace; color: var(--accent); }
details summary { cursor:pointer; color:var(--doux); margin: 18px 0 10px; }
.vide { color:var(--doux); background:var(--carte); border:1px dashed var(--ligne); border-radius:12px; padding:16px; }
"""


def _page(titre: str, sous_titre: str, corps: str) -> str:
    return (f"<!doctype html>\n{MARQUE}\n<html lang=\"fr\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<meta name=\"color-scheme\" content=\"light dark\"><title>{html.escape(titre)}</title>"
            f"<style>{STYLE}</style></head><body><main><h1>{html.escape(titre)}</h1>"
            f"<p class=\"sous\">{html.escape(sous_titre)}</p>{corps}</main></body></html>\n")  # fmt: skip


def _e(texte: Any) -> str:
    return html.escape(str(texte)) if texte not in (None, "") else ""


def _jj(d: date | str | None) -> str:
    if not d:
        return ""
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d/%m/%Y")


def _carte_fiche(f: Fiche, aujourd_hui: date) -> str:
    etat = {"active": "active", "bientôt": "bientot", "expirée": "expiree"}[f.etat(aujourd_hui)]
    j = f.jours_restants(aujourd_hui)
    reste = f"{j} j" if j >= 0 else "expirée"
    origine = {"note": "ta note", "facture": "la facture", "légale": "garantie légale", "manuelle": "saisie"}.get(
        f.source, f.source
    )
    meta = " · ".join(x for x in (_e(f.emetteur), f"acheté le {_jj(f.achat)}", f"{f.mois} mois ({origine})",
                                  f"{_e(f.prix)} €" if f.prix else "", f"fiche n°{f.id}") if x)  # fmt: skip
    return (f"<div class=\"carte {etat}\"><div><div class=\"titre\">{_e(f.produit)}</div><div class=\"meta\">{meta}"
            f"</div></div><div class=\"reste\">{reste}<small>fin le {_jj(f.fin)}</small></div></div>")  # fmt: skip


def page_coffre(fiches: list[Fiche], aujourd_hui: date | None = None) -> str:
    jour = aujourd_hui or date.today()
    actives = [f for f in fiches if f.jours_restants(jour) >= 0]
    expirees = [f for f in fiches if f.jours_restants(jour) < 0]
    bientot = [f for f in actives if f.jours_restants(jour) <= 30]
    chiffres = (f"<div class=\"chiffres\"><div class=\"chiffre\"><b>{len(actives)}</b><span>en cours</span></div>"
                f"<div class=\"chiffre\"><b>{len(bientot)}</b><span>finissent dans 30 j</span></div>"
                f"<div class=\"chiffre\"><b>{len(expirees)}</b><span>expirées</span></div></div>")  # fmt: skip
    if not fiches:
        corps = chiffres + "<p class=\"vide\">Aucune garantie pour l'instant. Envoie une facture d'achat au Mac.</p>"
    else:
        corps = chiffres + "<h2>En cours</h2>" + ("".join(_carte_fiche(f, jour) for f in actives) or
                                                 "<p class=\"vide\">Aucune garantie en cours.</p>")  # fmt: skip
        if expirees:
            corps += (f"<details><summary>{len(expirees)} garantie(s) expirée(s)</summary>"
                      + "".join(_carte_fiche(f, jour) for f in reversed(expirees)) + "</details>")  # fmt: skip
    corps += ("<h2>Changer une fiche</h2><p class=\"sous\">Sur le Mac : <code>trieur garantie modifier N --fin "
              "AAAA-MM-JJ</code> ou <code>trieur garantie supprimer N</code>.</p>")  # fmt: skip
    return _page("Mon coffre", f"Tes garanties — mis à jour le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", corps)


def _carte_element(el: Element) -> str:
    destination = Path(el.destination) if el.destination else None
    titre = destination.name if destination else el.nom
    meta = [f"reçu : {_e(el.nom)}"] if destination and destination.name != el.nom else []
    if destination:
        meta.append(f"dans {_e(destination.parent.name)}")
    if el.confiance is not None and el.etat in ("classe", "a_verifier"):
        meta.append(f"confiance {el.confiance:.0%}" + (f" ({_e(el.par)})" if el.par else ""))
    if el.erreur and el.etat in ("erreur", "a_verifier"):
        meta.append(_e(el.erreur))
    meta.append(f"n°{el.id}")
    quand = datetime.fromtimestamp(el.traite or el.ajoute).strftime("%d/%m %H:%M")
    return (f"<div class=\"carte {el.etat}\"><div><div class=\"titre\">{_e(titre)}<span class=\"etiquette\">"
            f"{LIBELLES.get(el.etat, el.etat)}</span></div><div class=\"meta\">{' · '.join(meta)}</div></div>"
            f"<div class=\"reste\"><small>{quand}</small></div></div>")  # fmt: skip


def page_derniers(elements: list[Element]) -> str:
    a_voir = [e for e in elements if e.etat in ("a_verifier", "erreur")]
    corps = ""
    if a_voir:
        corps += "<h2>À regarder</h2>" + "".join(_carte_element(e) for e in a_voir)
    reste = [e for e in elements if e not in a_voir]
    corps += "<h2>Derniers classements</h2>" + ("".join(_carte_element(e) for e in reste) or
                                                "<p class=\"vide\">Rien encore.</p>")  # fmt: skip
    corps += ("<h2>Une erreur ?</h2><p class=\"sous\">Sur le Mac : <code>trieur corriger N --type devis</code> ou "
              "<code>trieur annuler N</code> (N : le numéro de la ligne).</p>")  # fmt: skip
    return _page("Derniers classements", f"Mis à jour le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", corps)


def ecrire(dossier: Path, nom: str, contenu: str) -> Path:
    """Écrit la page de façon atomique ; ne remplace qu'une page du Trieur (avec sa marque)."""
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / nom
    if cible.exists():
        try:
            a_nous = MARQUE in cible.read_text(encoding="utf-8", errors="replace")[:400]
        except OSError:
            a_nous = False
        if not a_nous:
            cible = dossier / f"{Path(nom).stem} (Trieur).html"
            if cible.exists() and MARQUE not in cible.read_text(encoding="utf-8", errors="replace")[:400]:
                raise FileExistsError(f"{cible} existe et n'est pas une page du Trieur")
    fd, temporaire = tempfile.mkstemp(dir=dossier, prefix=".trieur-", suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(contenu)
    os.replace(temporaire, cible)
    return cible


def mettre_a_jour(reglages: dict[str, Any], base: Base, coffre: Coffre) -> list[Path]:
    dossier = config.chemin(reglages, "boite")
    return [ecrire(dossier, COFFRE, page_coffre(coffre.fiches(toutes=False))),
            ecrire(dossier, DERNIERS, page_derniers(base.derniers(40)))]  # fmt: skip
