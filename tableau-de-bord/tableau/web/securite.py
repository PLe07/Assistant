"""La porte de la page locale (§5.1, §9.3).

- Écoute sur **127.0.0.1 seulement**.
- **Jeton secret** dans l'adresse (`?t=…`) pour toute requête ; comparé en temps constant.
- **Host** : exactement `127.0.0.1:<port>` ou `localhost:<port>`. Un autre nom (rebond DNS : un site qui fait pointer
  son nom vers 127.0.0.1) est refusé, même avec le bon port.
- **POST** (les rares actions) : le jeton aussi dans l'en-tête `X-Jeton`, un corps JSON, et une **Origin** absente ou
  exactement la nôtre ; une requête marquée `Sec-Fetch-Site: cross-site` est refusée.
- En-têtes de réponse : aucune ressource extérieure (CSP stricte, ni script ni style en ligne), pas d'adresse
  transmise ailleurs (`Referrer-Policy: no-referrer`, le jeton ne fuit pas), pas d'affichage dans un cadre, pas de
  cache.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
ENTETES = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
HOTES = ("127.0.0.1", "localhost")
ENTETES_LUES = ("Host", "Origin", "X-Jeton", "Content-Type", "Sec-Fetch-Site")


@dataclass
class Verdict:
    ok: bool
    code: int = 200
    motif: str = ""


def jeton_de(url: str) -> str:
    valeurs = parse_qs(urlsplit(url).query).get("t", [])
    return valeurs[0] if len(valeurs) == 1 else ""


def meme_jeton(fourni: str, attendu: str) -> bool:
    return bool(fourni) and hmac.compare_digest(fourni.encode(), attendu.encode())


def hote_permis(hote: str | None, port: int) -> bool:
    return hote is not None and hote.strip().lower() in {f"{h}:{port}" for h in HOTES}


def origine_permise(origine: str | None, port: int) -> bool:
    if origine is None:
        return True  # outils en ligne de commande : le jeton suffit
    return origine.strip().lower() in {f"http://{h}:{port}" for h in HOTES}


def verifier(methode: str, url: str, entetes: Mapping[str, str], jeton: str, port: int) -> Verdict:
    """Le verdict de la porte pour une requête (avant toute lecture de données)."""
    if not hote_permis(entetes.get("Host"), port):
        return Verdict(False, 421, "hôte refusé")
    if not meme_jeton(jeton_de(url), jeton):
        return Verdict(False, 403, "jeton absent ou faux")
    if methode == "POST":
        if (entetes.get("Sec-Fetch-Site") or "").lower() == "cross-site":
            return Verdict(False, 403, "requête venue d'un autre site")
        if not origine_permise(entetes.get("Origin"), port):
            return Verdict(False, 403, "origine refusée")
        if not meme_jeton(entetes.get("X-Jeton") or "", jeton):
            return Verdict(False, 403, "jeton absent de l'en-tête")
        if not (entetes.get("Content-Type") or "").lower().startswith("application/json"):
            return Verdict(False, 415, "corps JSON attendu")
    elif methode not in ("GET", "HEAD"):
        return Verdict(False, 405, "méthode refusée")
    return Verdict(True)
