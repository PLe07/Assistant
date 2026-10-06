"""Générateur du corpus d'arnaques (§11.1), avec sa vérité terrain.

    python -m tests.corpus_arnaques.generer [dossier]

écrit chaque message (`.txt` pour un SMS, `.eml` complet avec en-têtes pour un mail) et `verite.json`.
Les tests appellent directement `corpus_principal()` et `corpus_inedit()`.

Le contexte imité (ce que RDAP, les flux et l'inventaire répondraient) est tiré du nom de domaine, de façon
déterministe et sans regarder le verdict attendu au-delà de ceci : un domaine d'arnaque est récent (4 sur 10),
inconnu de RDAP (3 sur 10) ou ancien, comme un site piraté (3 sur 10) ; 1 lien d'arnaque sur 5 est dans un flux.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from pathlib import Path
from typing import Any

from tests.corpus_arnaques.donnees import ARNAQUES, INJECTIONS, LEGITIMES
from tests.corpus_arnaques.donnees_inedites import ARNAQUES_INEDITES, LEGITIMES_INEDITS

MAINTENANT = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
DESTINATAIRE = "Camille <camille.exemple@googlemail.com>"
_IDN = re.compile(r"\{idn:([^}]+)\}")
_URL = re.compile(r"(?:https?://)?((?:[a-z0-9\-]+\.)+[a-z]{2,})(?:/[^\s]*)?", re.IGNORECASE)

# L'inventaire imité de la personne : elle est cliente de La Banque Postale et de Boursobank.
INVENTAIRE = [
    "laposte", "ameli", "impots", "labanquepostale", "boursobank", "amazon", "vinted", "leboncoin", "netflix",
    "orange", "edf", "doctolib", "sncf", "google", "apple", "paypal", "fnac", "decathlon",
]  # fmt: skip


@dataclass
class Echantillon:
    id: str
    canal: str
    famille: str
    verite: str  # "arnaque" ou "legitime"
    injection: bool
    brut: bytes
    domaines: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)

    @property
    def nom_fichier(self) -> str:
        return f"{self.id}.{'eml' if self.canal == 'mail' else 'txt'}"


def _idn(texte: str) -> str:
    return _IDN.sub(lambda m: m.group(1).encode("idna").decode("ascii"), texte)


def _domaine(adresse: str) -> str:
    return adresse.rsplit("@", 1)[-1].strip(">").strip().lower()


def _auth(spec: str, domaine_expediteur: str) -> str:
    if spec.startswith("pass:"):
        d = spec[5:]
        return (f"mx.google.com; dkim=pass header.i=@{d} header.s=s1 header.b=AbCdEf; "
                f"spf=pass (google.com: domain of bounce@{d} designates 192.0.2.10 as permitted sender) "
                f"smtp.mailfrom=bounce@{d}; dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={d}")  # fmt: skip
    if spec.startswith("fail:"):
        d = spec[5:]
        return (f"mx.google.com; spf=softfail (google.com: domain of transitioning {d} does not designate "
                f"203.0.113.77 as permitted sender) smtp.mailfrom={d}; dkim=none; "
                f"dmarc=fail (p=QUARANTINE sp=QUARANTINE dis=QUARANTINE) header.from={d}")  # fmt: skip
    return (f"mx.google.com; spf=neutral (google.com: 198.51.100.23 is neither permitted nor denied) "
            f"smtp.mailfrom={domaine_expediteur}; dkim=none; dmarc=none header.from={domaine_expediteur}")  # fmt: skip


def _html(corps: str, liens: list[tuple[str, str]]) -> str:
    import html

    morceaux = [html.escape(corps)]
    texte = morceaux[0]
    for i, (affiche, href) in enumerate(liens):
        texte = texte.replace(f"{{{i}}}", f'<a href="{html.escape(href, quote=True)}">{html.escape(affiche)}</a>')
    texte = texte.replace("\n", "<br>\n")
    return f'<html><body><div style="font-family:Arial">{texte}</div></body></html>'


def _mail(ident: str, m: dict[str, Any], numero: int) -> tuple[bytes, list[str], list[str]]:
    de = _idn(m["de"])
    liens = [(_idn(a), _idn(h)) for a, h in m["liens"]]
    corps = _idn(m["corps"])
    domaine = _domaine(de)
    msg = EmailMessage(policy=SMTP)
    msg["From"] = de
    msg["To"] = DESTINATAIRE
    msg["Subject"] = m["sujet"]
    msg["Date"] = format_datetime(MAINTENANT - dt.timedelta(minutes=7 * numero + 3))
    msg["Message-ID"] = f"<{ident}.{numero}@{domaine}>"
    msg["Authentication-Results"] = _auth(m["auth"], domaine)
    if m["reply_to"]:
        msg["Reply-To"] = m["reply_to"]
    if m["desinscription"]:
        msg["List-Unsubscribe"] = f"<https://{domaine}/desabonnement?u=8812>, <mailto:unsubscribe@{domaine}>"
    # Le texte brut montre l'adresse réelle du lien, comme les vrais clients de messagerie.
    brut_texte = corps
    for i, (affiche, href) in enumerate(liens):
        brut_texte = brut_texte.replace(f"{{{i}}}", f"{affiche} ( {href} )")
    brut_texte = brut_texte.replace("{{", "{").replace("}}", "}")
    encodage = m["encodage"]
    cte = "base64" if numero % 3 == 0 else "quoted-printable"
    msg.set_content(brut_texte, subtype="plain", charset=encodage, cte=cte)
    if m["html"] and liens:
        html_corps = _html(corps, liens).replace("{{", "{").replace("}}", "}")
        msg.add_alternative(html_corps, subtype="html", charset=encodage, cte=cte)
    domaines = [domaine] + [_URL.match(h).group(1).lower() for _, h in liens if _URL.match(h)]  # type: ignore[union-attr]
    return bytes(msg), domaines, [h for _, h in liens]


def _echantillon(entree: tuple[str, str, str, Any], verite: str, injection: bool, numero: int) -> Echantillon:
    ident, canal, famille, contenu = entree
    if canal == "sms":
        texte = _idn(contenu)
        urls = re.findall(r"(?:https?://[^\s]+|\b(?:[a-z0-9\-]+\.)+(?:fr|com|info|top|xyz|eu|online|net|me|cc|site|vip|club|shop|app|work|win|live|icu|help|ly|gy|gd|at|id|cx)\b[^\s]*)", texte)  # fmt: skip
        domaines = [_URL.match(u).group(1).lower() for u in urls if _URL.match(u)]  # type: ignore[union-attr]
        return Echantillon(ident, canal, famille, verite, injection, texte.encode("utf-8"), domaines, urls)
    brut, domaines, urls = _mail(ident, contenu, numero)
    return Echantillon(ident, canal, famille, verite, injection, brut, domaines, urls)


def corpus_principal() -> list[Echantillon]:
    sortie: list[Echantillon] = []
    for i, e in enumerate(ARNAQUES):
        sortie.append(_echantillon(e, "arnaque", False, i))
    for i, e in enumerate(INJECTIONS):
        sortie.append(_echantillon(e, "arnaque", True, 200 + i))
    for i, e in enumerate(LEGITIMES):
        sortie.append(_echantillon(e, "legitime", False, 300 + i))
    return sortie


def corpus_inedit() -> list[Echantillon]:
    sortie: list[Echantillon] = []
    for i, e in enumerate(ARNAQUES_INEDITES):
        sortie.append(_echantillon(e, "arnaque", False, 500 + i))
    for i, e in enumerate(LEGITIMES_INEDITS):
        sortie.append(_echantillon(e, "legitime", False, 600 + i))
    return sortie


# --- Le contexte imité ---------------------------------------------------------------------------------------------

_RACCOURCISSEURS = {"bit.ly", "tinyurl.com", "cutt.ly", "rb.gy", "is.gd", "shorturl.at", "s.id", "t.ly", "urlz.fr",
                    "lc.cx", "t.me", "wa.me"}  # fmt: skip


def _graine(texte: str) -> int:
    return int(hashlib.sha256(texte.encode()).hexdigest()[:8], 16)


def contexte(corpus: list[Echantillon]) -> tuple[dict[str, dt.date | None], set[str]]:
    """(date de création de chaque domaine, URL présentes dans les flux de liens piégés)."""
    dates: dict[str, dt.date | None] = {}
    flux: set[str] = set()
    aujourd_hui = MAINTENANT.date()
    for e in corpus:
        for d in e.domaines:
            if d in dates:
                continue
            g = _graine(d)
            if e.verite == "legitime" or d in _RACCOURCISSEURS or d.endswith(("gmail.com", "outlook.com", "outlook.fr", "protonmail.com")):  # fmt: skip
                dates[d] = aujourd_hui - dt.timedelta(days=3650 + g % 5000)
            elif g % 10 < 4:
                dates[d] = aujourd_hui - dt.timedelta(days=2 + g % 24)
            elif g % 10 < 7:
                dates[d] = None
            else:
                dates[d] = aujourd_hui - dt.timedelta(days=700 + g % 2000)
        if e.verite == "arnaque":
            for u in e.urls:
                if _graine(u) % 5 == 0:
                    flux.add(u if "://" in u else "https://" + u)
    return dates, flux


def ecrire(dossier: Path) -> dict[str, Any]:
    dossier.mkdir(parents=True, exist_ok=True)
    verite: dict[str, Any] = {}
    for nom, corpus in (("principal", corpus_principal()), ("inedit", corpus_inedit())):
        (dossier / nom).mkdir(exist_ok=True)
        for e in corpus:
            (dossier / nom / e.nom_fichier).write_bytes(e.brut)
            verite[f"{nom}/{e.nom_fichier}"] = {"verite": e.verite, "famille": e.famille, "canal": e.canal,
                                                "injection": e.injection}  # fmt: skip
    (dossier / "verite.json").write_text(json.dumps(verite, indent=1, ensure_ascii=False), encoding="utf-8")
    return verite


if __name__ == "__main__":
    cible = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "genere"
    v = ecrire(cible)
    print(f"{len(v)} messages écrits dans {cible}")
