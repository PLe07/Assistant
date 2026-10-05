"""Le rapport : une page HTML autonome (sans rien à télécharger), en français, claire et sombre selon ton Mac.

Pour chaque corvée : ce qui a été vu, en une phrase ; la fréquence, la dernière fois, le temps perdu ; la solution
proposée (script contrôlé, pas à pas, risques) ; son identifiant pour accepter, refuser ou reporter.
La page est écrite dans donnees/corvees/rapport.html (lisible par toi seul) et s'ouvre avec « open ».
"""

from __future__ import annotations

import html
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from modules.corvees import config, propositions
from modules.corvees.descriptions import locale, observe
from modules.corvees.detection.memoire import filtrer
from modules.corvees.normalize import local, mois_de

JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
TYPES = {
    "raccourci_macos": "Raccourci ou réglage de macOS",
    "app_raccourcis": "App Raccourcis",
    "script_shell": "Script",
    "alias_zsh": "Raccourci de terminal (alias)",
    "tache_launchd": "Tâche automatique",
    "regle_dossier": "Règle de dossier",
    "autre": "Idée",
}

STYLE = """
:root{--fond:#f6f6f3;--carte:#fff;--texte:#1d1d1f;--doux:#6e6e73;--trait:#e2e2de;--accent:#0a66c2;
--vert:#1e7e34;--orange:#b35c00;--code:#f0f0ec}
@media (prefers-color-scheme:dark){:root{--fond:#1b1b1d;--carte:#2a2a2d;--texte:#f2f2f7;--doux:#a1a1a6;
--trait:#3a3a3d;--accent:#5aa9ff;--vert:#5cc879;--orange:#f0a04b;--code:#1f1f22}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--texte);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif}
main{max-width:820px;margin:0 auto;padding:28px 16px 56px}
h1{font-size:1.6rem;margin:0 0 6px}
.resume{color:var(--doux);margin:0 0 22px}
.resume strong{color:var(--texte)}
article{background:var(--carte);border:1px solid var(--trait);border-radius:14px;padding:18px 20px;margin:16px 0}
article h2{font-size:1.15rem;margin:0 0 8px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.id{font:600 .8rem ui-monospace,Menlo,monospace;color:var(--doux);border:1px solid var(--trait);border-radius:6px;
padding:1px 6px}
.vu{margin:0 0 10px}
.chiffres{display:flex;flex-wrap:wrap;gap:8px 18px;margin:0 0 12px;padding:0;list-style:none;color:var(--doux);
font-size:.92rem}
.chiffres strong{color:var(--texte)}
.solution{border-top:1px solid var(--trait);padding-top:12px}
.solution h3{font-size:1rem;margin:0 0 6px}
.etiquette{display:inline-block;font-size:.8rem;border-radius:6px;padding:1px 8px;margin-left:6px;
background:var(--code);color:var(--doux)}
.ok{color:var(--vert)}.attention{color:var(--orange)}
pre{background:var(--code);border:1px solid var(--trait);border-radius:10px;padding:12px;overflow-x:auto;
font:13px/1.45 ui-monospace,Menlo,monospace;margin:6px 0}
ol{padding-left:22px}li{margin:4px 0}
.commandes{margin:12px 0 0;font-size:.92rem;color:var(--doux)}
code{font:13px ui-monospace,Menlo,monospace;background:var(--code);padding:1px 5px;border-radius:5px;
color:var(--texte)}
.revenue{color:var(--orange);font-weight:600}
.vide{background:var(--carte);border:1px dashed var(--trait);border-radius:14px;padding:22px;text-align:center;
color:var(--doux)}
footer{margin-top:36px;color:var(--doux);font-size:.88rem}
button.copier{float:right;font:inherit;font-size:.8rem;border:1px solid var(--trait);background:var(--carte);
color:var(--texte);border-radius:6px;padding:2px 8px;cursor:pointer}
"""

SCRIPT_COPIER = """
document.querySelectorAll('button.copier').forEach(function(b){b.addEventListener('click',function(){
var t=document.getElementById(b.dataset.cible).innerText;
if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){b.textContent='Copié ✓';});}
});});
"""


def _e(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def date_lisible(ts: float | None) -> str:
    """« ven. 2 oct. à 20:30 » (heure de Paris)."""
    if not ts:
        return "jamais"
    d = local(float(ts))
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} à {d:%H:%M}"


def _nombre(x: float) -> str:
    return f"{x:.1f}".replace(".", ",").replace(",0", "") if x < 10 else str(round(x))


def _verification(reglages: dict[str, Any], c: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    prop = propositions.lire(reglages, c["id"])
    if prop is not None and prop["description"]["solution"]["script"] == d["solution"]["script"]:
        resultat: dict[str, Any] = prop["verification"]
        return resultat
    return propositions.verifier(d["solution"]["script"], d["solution"]["type"])


def carte(reglages: dict[str, Any], c: dict[str, Any], d: dict[str, Any]) -> str:
    s = d["solution"]
    v = _verification(reglages, c, d)
    morceaux = [
        f'<article id="{_e(c["id"])}"><h2>{_e(d["titre_court"])}<span class="id">{_e(c["id"])}</span></h2>',
        f'<p class="vu">{_e(observe(c))}</p>',
    ]
    if c.get("revenue"):
        morceaux.append(f'<p class="revenue">{_e(c["revenue"])}</p>')
    if d.get("source") == "claude":
        morceaux.append(f"<p>{_e(d['description_fr'])}</p>")
    gain = min(float(d["gain_minutes_mois"]), float(c["minutes_mois"]))
    morceaux.append(
        '<ul class="chiffres">'
        f"<li>Fréquence : <strong>{_nombre(float(c['frequence_mois']))} fois par mois</strong></li>"
        f"<li>Dernière fois : <strong>{_e(date_lisible(c.get('derniere')))}</strong></li>"
        f"<li>Temps perdu : <strong>≈ {_nombre(float(c['minutes_mois']))} min/mois</strong></li>"
        f"<li>À récupérer : <strong>≈ {_nombre(gain)} min/mois</strong></li></ul>"
    )
    morceaux.append(
        f'<div class="solution"><h3>💡 {_e(TYPES.get(s["type"], s["type"]))}'
        f'<span class="etiquette">difficulté : {_e(d["difficulte"])}</span>'
        f'<span class="etiquette">confiance : {round(float(d["confiance"]) * 100)} %</span>'
        f'<span class="etiquette">{"par Claude" if d.get("source") == "claude" else "sans Claude"}</span></h3>'
        f"<p>{_e(s['explication'])}</p>"
    )
    if s["installation_pas_a_pas"]:
        morceaux.append("<ol>" + "".join(f"<li>{_e(p)}</li>" for p in s["installation_pas_a_pas"]) + "</ol>")
    if s["script"].strip():
        classe = "ok" if v["ok"] else "attention"
        morceaux.append(
            f'<p><button class="copier" data-cible="script-{_e(c["id"])}">Copier</button>'
            f'<span class="{classe}">{_e(v["statut"])}</span> · il n\'est jamais lancé tout seul</p>'
        )
        if v["problemes"]:
            morceaux.append("<ul>" + "".join(f'<li class="attention">{_e(p)}</li>' for p in v["problemes"]) + "</ul>")
        morceaux.append(f'<pre><code id="script-{_e(c["id"])}">{_e(s["script"].rstrip())}</code></pre>')
    morceaux.append(f"<p><strong>Risques :</strong> {_e(s['risques'])}</p>")
    morceaux.append(f"<p><strong>Pourquoi c'est une corvée :</strong> {_e(d['pourquoi_corvee'])}</p></div>")
    installer = (
        f" · <code>corvees accept {_e(c['id'])} --installer</code>"
        if s["type"] in propositions.INSTALLABLES and s["script"].strip() and v["ok"]
        else ""
    )
    morceaux.append(
        f'<p class="commandes"><code>corvees accept {_e(c["id"])}</code>{installer}'
        f" · <code>corvees reject {_e(c['id'])}</code> · <code>corvees snooze {_e(c['id'])} 7</code></p></article>"
    )
    return "".join(morceaux)


def construire(base: Any, reglages: dict[str, Any], maintenant: float) -> str:
    candidats = filtrer(base.candidats(), base.decisions(), maintenant)  # sans ce que tu as décidé depuis
    descriptions = base.descriptions()
    paires = [(c, descriptions.get(c["signature"]) or {**locale(c), "source": "locale"}) for c in candidats]
    gain = sum(min(float(d["gain_minutes_mois"]), float(c["minutes_mois"])) for c, d in paires)
    derniere = base.lire("derniere_analyse")
    if paires:
        n = len(paires)
        resume = (
            f"<strong>{n} corvée{'s' if n > 1 else ''}</strong> · environ <strong>{round(gain)} min/mois</strong> "
            f"à récupérer · analyse du {_e(date_lisible(derniere))}"
        )
        corps = "".join(carte(reglages, c, d) for c, d in paires)
    else:
        resume = f"Analyse du {_e(date_lisible(derniere))}"
        corps = (
            "<p class=\"vide\">Rien de solide pour l'instant : je continue d'observer, discrètement.<br>"
            "Reviens dans quelques jours.</p>"
        )
    cout = base.cout_du_mois(mois_de(maintenant))
    plafond = float(reglages["ia"]["budget_mensuel_usd"])
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark"><title>Tes corvées repérées</title>'
        f"<style>{STYLE}</style></head><body><main>"
        f'<h1>🔁 Tes corvées repérées</h1><p class="resume">{resume}</p>{corps}'
        "<footer><p>Je propose, tu décides : rien n'est jamais automatisé sans ton accord.</p>"
        "<p>Tout reste sur ton Mac. Seuls des résumés caviardés partent chez Claude "
        f"(≈ {cout:.2f} $ ce mois-ci, plafond {plafond:.2f} $).</p>"
        "<p><code>corvees pause</code> coupe tout · <code>corvees purge</code> efface tout · "
        "<code>corvees doctor</code> fait le point.</p></footer>"
        f"</main><script>{SCRIPT_COPIER}</script></body></html>"
    )


def chemin(reglages: dict[str, Any]) -> Path:
    return config.dossier_donnees(reglages) / "rapport.html"


def ecrire(base: Any, reglages: dict[str, Any], maintenant: float) -> Path:
    fichier = chemin(reglages)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(construire(base, reglages, maintenant), encoding="utf-8")
    os.chmod(fichier, 0o600)
    return fichier


def ouvrir(fichier: Path, lancer: Callable[..., Any] = subprocess.run, plateforme: str = sys.platform) -> bool:
    """Ouvre la page dans ton navigateur (sur le Mac) ; ailleurs, ne fait rien."""
    if plateforme != "darwin":
        return False
    return lancer(["open", str(fichier)], check=False).returncode == 0
