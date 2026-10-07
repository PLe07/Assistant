"""Le gabarit commun des pages de Quotidien (menu de la semaine, « Ma journée ») : un seul fichier HTML autonome,
sans rien à télécharger, lisible sur iPhone, imprimable, en clair ou en sombre selon le téléphone.

Tout texte venant d'ailleurs (noms, notes, messages) passe par `e()` (échappement HTML).
"""

from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path

STYLE = """
:root { --fond:#faf8f5; --carte:#ffffff; --texte:#1f1d1a; --doux:#6b665e; --trait:#e6e1d8; --accent:#2f6f4e;
        --alerte:#9a3b1f; --puce:#f1ede6; }
@media (prefers-color-scheme: dark) {
  :root { --fond:#151412; --carte:#1e1c19; --texte:#ece8e1; --doux:#a39d93; --trait:#34302a; --accent:#7cc39b;
          --alerte:#f0a080; --puce:#2a2723; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--fond); color:var(--texte); font:16px/1.5 -apple-system, BlinkMacSystemFont,
       "Segoe UI", Roboto, sans-serif; -webkit-text-size-adjust:100%; }
main { max-width: 760px; margin: 0 auto; padding: 20px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 1.15rem; margin: 28px 0 10px; }
h3 { font-size: 1.02rem; margin: 0 0 6px; }
.sous { color: var(--doux); margin: 0 0 18px; }
.carte { background: var(--carte); border: 1px solid var(--trait); border-radius: 14px; padding: 14px 16px;
         margin: 0 0 12px; break-inside: avoid; }
.ligne { display:flex; gap:10px; align-items:baseline; }
.jour { font-weight: 650; min-width: 92px; }
.meta { color: var(--doux); font-size: .9rem; }
.puce { display:inline-block; background: var(--puce); border-radius: 999px; padding: 1px 9px; font-size: .82rem;
        margin: 2px 4px 2px 0; color: var(--doux); }
.alerte { border-color: var(--alerte); color: var(--alerte); }
ul { margin: 6px 0 0; padding-left: 20px; }
ol { margin: 6px 0 0; padding-left: 22px; }
li { margin: 2px 0; }
a { color: var(--accent); }
a.bouton { display:inline-block; background: var(--accent); color: var(--carte); text-decoration:none;
           padding: 8px 14px; border-radius: 10px; font-weight: 600; margin: 6px 6px 0 0; }
details summary { cursor: pointer; font-weight: 600; }
.total { font-size: 1.1rem; font-weight: 650; }
.vide { color: var(--doux); font-style: italic; }
@media print {
  body { background: #fff; color: #000; font-size: 12pt; }
  .carte { border-color: #bbb; }
  details { display: block; }
  details > summary { list-style: none; }
  a.bouton { display: none; }
}
"""


def e(texte: object) -> str:
    return html.escape(str(texte), quote=True)


def page(titre: str, corps: str) -> str:
    return (
        '<!doctype html>\n<html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="color-scheme" content="light dark"><title>{e(titre)}</title><style>{STYLE}</style></head>'
        f"<body><main>{corps}</main></body></html>\n"
    )


def ecrire_atomique(chemin: Path, contenu: str) -> None:
    """Écrit d'un coup (fichier temporaire puis renommage) : iCloud ne voit jamais une page à moitié écrite."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, temporaire = tempfile.mkstemp(prefix=".quotidien-", suffix=".tmp", dir=chemin.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenu)
        os.replace(temporaire, chemin)
    finally:
        if os.path.exists(temporaire):
            os.unlink(temporaire)
