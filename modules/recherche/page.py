"""La page de tes 20 dernières recherches (donnees/recherche/recherche.html) : chaque réponse avec ses
sources cliquables. Elle s'ouvre dans ton navigateur (« Ouvrir les sources »)."""

import html
import os
from datetime import datetime

from modules.recherche import parametres as p
from modules.recherche.recherche import FIABILITE
from modules.veille.page import STYLE  # le même style que la page de la veille


def _e(texte) -> str:
    return html.escape(str(texte or ""))


def _source(s: dict) -> str:
    url = s["url"] if s["url"].lower().startswith(("https://", "http://")) else "#"
    alerte = ' <span class="alerte">⚠️ lien introuvable</span>' if s.get("lien") == "mort" else ""
    return (f'<li><a href="{_e(url)}" target="_blank" rel="noopener noreferrer">{_e(s["titre"])}</a>'
            f' <span class="meta">· {_e(s["site"])}{" · " + _e(s["date"]) if s["date"] else ""}</span>{alerte}</li>')


def _carte(r: dict) -> str:
    sources = "".join(_source(s) for s in r["sources"]) or '<li class="alerte">Aucune source donnée</li>'
    return (f'<div class="carte"><strong>🌐 {_e(r["question"])}</strong>'
            f'<div class="meta">{datetime.fromtimestamp(r["quand"]):%d/%m/%Y à %H:%M} · '
            f'fiabilité : {_e(FIABILITE.get(r["fiabilite"], ""))}</div>'
            f'<p class="pourquoi">{_e(r["reponse"])}</p><ul>{sources}</ul></div>')


def contenu(recherches: list[dict]) -> str:
    corps = "".join(_carte(r) for r in recherches) or '<p class="sous">Pas encore de recherche.</p>'
    return ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Mes recherches</title><style>{STYLE}</style></head><body><main>"
            f"<h1>🌐 Mes recherches</h1><p class=\"sous\">Les {p.GARDER} dernières, la plus récente en premier.</p>"
            f"{corps}<footer><p>Page écrite par ton Assistant, sur ton Mac. Les liens ⚠️ n'ont pas été trouvés "
            f"quand ton Mac les a vérifiés.</p></footer></main></body></html>")


def ecrire_page(recherches: list[dict]) -> None:
    p.DOSSIER.mkdir(parents=True, exist_ok=True)
    temporaire = p.PAGE.with_name(f".recherche.{os.getpid()}.tmp")
    temporaire.write_text(contenu(recherches), encoding="utf-8")
    os.chmod(temporaire, 0o600)
    os.replace(temporaire, p.PAGE)
