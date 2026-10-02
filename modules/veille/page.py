"""La page de ta dernière veille (donnees/veille/veille.html) : les points retenus avec leurs liens,
les autres nouveautés, et ce qui a été retenu ces 30 derniers jours. Elle s'ouvre dans ton navigateur."""

import html
import os

from modules.veille import parametres as p
from modules.veille import revue as rv

STYLE = """
:root { --fond:#f7f7f5; --carte:#ffffff; --texte:#1d1d1f; --doux:#6e6e73; --trait:#e3e3e0; --accent:#0a66c2; --or:#b7791f; }
@media (prefers-color-scheme: dark) {
  :root { --fond:#1c1c1e; --carte:#2c2c2e; --texte:#f2f2f7; --doux:#a1a1a6; --trait:#3a3a3c; --accent:#5aa9ff; --or:#e0b252; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--fond); color:var(--texte); font:16px/1.5 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif; }
main { max-width:760px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:1.5rem; margin:0 0 4px; }
h2 { font-size:1.1rem; margin:32px 0 12px; }
.sous { color:var(--doux); margin:0 0 16px; }
.bref { background:var(--carte); border-left:4px solid var(--accent); padding:12px 16px; border-radius:8px; }
.carte { background:var(--carte); border:1px solid var(--trait); border-radius:12px; padding:14px 16px; margin:12px 0; }
.carte a { color:var(--accent); font-weight:600; text-decoration:none; }
.carte a:hover { text-decoration:underline; }
.etoiles { color:var(--or); margin-right:6px; }
.pourquoi { margin:6px 0 4px; }
.meta { color:var(--doux); font-size:.85rem; }
ul { padding-left:20px; } li { margin:6px 0; } li a { color:var(--accent); }
details { margin-top:24px; } summary { cursor:pointer; font-weight:600; }
.alerte { color:#c0392b; }
footer { margin-top:40px; color:var(--doux); font-size:.85rem; }
"""


def _e(texte) -> str:
    return html.escape(str(texte or ""))


def _lien(a: dict) -> str:
    lien = a["lien"] if a["lien"].lower().startswith(("https://", "http://")) else "#"
    return f'<a href="{_e(lien)}" target="_blank" rel="noopener noreferrer">{_e(a["titre"])}</a>'


def _carte(a: dict) -> str:
    return (f'<div class="carte"><span class="etoiles">{rv.ETOILES.get(a["importance"], "★")}</span>{_lien(a)}'
            f'<p class="pourquoi">{_e(a["pourquoi"])}</p><div class="meta">{_e(rv._ligne_source(a))}</div></div>')


def _liste(articles: list[dict]) -> str:
    return "<ul>" + "".join(f'<li>{_lien(a)} <span class="meta">· {_e(rv._ligne_source(a))}</span></li>'
                            for a in articles) + "</ul>"


def contenu(r: dict) -> str:
    morceaux = [f"<h1>📰 Veille du {_e(rv.quand_lisible(r['quand']))}</h1>"]
    if r["retenus"]:
        morceaux.append(f'<p class="sous">{len(r["retenus"])} point(s) qui comptent pour toi, '
                        f'sur {r["nouveaux"]} nouveauté(s) · {r["lus"]} article(s) lu(s)</p>')
        if r["en_bref"]:
            morceaux.append(f'<p class="bref"><strong>En bref :</strong> {_e(r["en_bref"])}</p>')
        morceaux += [_carte(a) for a in r["retenus"]]
    else:
        lignes = rv.texte_revue(r).split("\n")  # « Rien de neuf… », « aucune ne compte… »
        morceaux.append(f'<p class="sous">{_e(lignes[1] if len(lignes) > 1 else "")}</p>')
    if r["autres"]:
        titre = ("Les nouveautés, pas encore triées" if not r["trie"]
                 else f"Les {len(r['autres'])} autres nouveautés (pas retenues)")
        morceaux.append(f"<details{' open' if not r['trie'] else ''}><summary>{_e(titre)}</summary>{_liste(r['autres'])}</details>")
    passe = rv.historique(30, sauf=r["id"])
    if passe:
        morceaux.append("<h2>Retenus ces 30 derniers jours</h2>" + _liste(passe))
    sources = "".join(f'<li class="alerte">⚠️ {_e(s["nom"])} : {_e(s["erreur"])}</li>' if s["erreur"]
                      else f"<li>{_e(s['nom'])} : {s['articles']} article(s) lu(s)</li>" for s in r["sources"])
    morceaux.append(f"<footer><p>Sources lues :</p><ul>{sources}</ul><p>Page écrite par ton Assistant, sur ton Mac. "
                    f"Les liens mènent aux sites officiels.</p></footer>")
    return ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Ma veille</title><style>{STYLE}</style></head><body><main>{''.join(morceaux)}</main></body></html>")


def ecrire_page(r: dict) -> None:
    """Écriture atomique : la page n'est jamais à moitié écrite."""
    p.DOSSIER.mkdir(parents=True, exist_ok=True)
    temporaire = p.PAGE.with_name(f".veille.{os.getpid()}.tmp")
    temporaire.write_text(contenu(r), encoding="utf-8")
    os.chmod(temporaire, 0o600)
    os.replace(temporaire, p.PAGE)
