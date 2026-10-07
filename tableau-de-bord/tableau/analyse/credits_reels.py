"""Le coût **réel** de l'organisation Anthropic (option, éteinte par défaut) — la seule connexion sortante permise.

Il faut une clé Admin (`sk-ant-admin…`), rangée par toi dans le trousseau du Mac (ACTIONS_HUMAINES.md) sous le
service `tableau-de-bord-admin-anthropic`, et `[credits] api_admin = true` dans `reglages.toml`.

Endpoint vérifié dans la documentation officielle le 2026-10-07 (Usage and Cost Admin API) :
`GET https://api.anthropic.com/v1/organizations/cost_report?starting_at=…&ending_at=…&limit=31[&page=…]`, en-têtes
`x-api-key` et `anthropic-version: 2023-06-01`. Réponse : `data[]` (une case par jour) → `results[]` → `amount`, en
**cents**, chaîne décimale ; pagination par `has_more` / `next_page`. Au plus une requête par heure.
"""

from __future__ import annotations

import calendar
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from tableau import systeme

HOTE = "api.anthropic.com"
URL = f"https://{HOTE}/v1/organizations/cost_report"
VERSION = "2023-06-01"
PAGES_MAX = 5

Ouvrir = Callable[[urllib.request.Request, float], Any]


class CoutReelIndisponible(Exception):
    pass


def lire_cle(executer: Callable[[list[str]], systeme.Resultat] | None = None) -> str | None:
    """La clé Admin dans le trousseau (lecture de notre propre élément seulement) ; None si absente."""
    executer = executer or (lambda args: systeme.executer(args, delai=10))
    r = executer(["security", "find-generic-password", "-s", systeme.SERVICE_TROUSSEAU, "-w"])
    cle = r.sortie.strip() if r.ok else ""
    return cle if cle.startswith("sk-ant-") else None


def _ouvrir_par_defaut(requete: urllib.request.Request, delai: float) -> Any:
    return urllib.request.urlopen(requete, timeout=delai)  # noqa: S310 - URL fixe en https vers api.anthropic.com


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def cout_du_mois(cle: str, maintenant: float, ouvrir: Ouvrir = _ouvrir_par_defaut) -> float:
    """Le coût réel du mois en dollars, toutes cases jour additionnées (pagination suivie, au plus 5 pages)."""
    t = time.gmtime(maintenant)
    debut = calendar.timegm((t.tm_year, t.tm_mon, 1, 0, 0, 0))
    fin = maintenant + 86400
    page: str | None = None
    total_cents = 0.0
    for _ in range(PAGES_MAX):
        params = {"starting_at": _iso(debut), "ending_at": _iso(fin), "limit": "31"}
        if page:
            params["page"] = page
        url = f"{URL}?{urllib.parse.urlencode(params)}"
        if urllib.parse.urlparse(url).hostname != HOTE or not url.startswith("https://"):
            raise CoutReelIndisponible("adresse refusée")  # garde-fou : jamais ailleurs
        requete = urllib.request.Request(url, method="GET", headers={
            "x-api-key": cle, "anthropic-version": VERSION, "User-Agent": "tableau-de-bord/1.0"})  # fmt: skip
        try:
            with ouvrir(requete, 20.0) as reponse:
                donnees = json.loads(reponse.read(2_000_000).decode("utf-8"))
        except (OSError, ValueError) as e:
            raise CoutReelIndisponible(f"rapport de coûts indisponible ({e.__class__.__name__})") from e
        for case in donnees.get("data", []) if isinstance(donnees, dict) else []:
            for r in case.get("results", []) if isinstance(case, dict) else []:
                try:
                    total_cents += float(r.get("amount", 0))
                except (TypeError, ValueError):
                    continue
        if not (isinstance(donnees, dict) and donnees.get("has_more") and donnees.get("next_page")):
            break
        page = str(donnees["next_page"])
    return total_cents / 100
