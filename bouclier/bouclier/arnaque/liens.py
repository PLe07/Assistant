"""Ce qu'on peut lire dans l'adresse d'un lien, sans jamais l'ouvrir.

Le nom de domaine enregistrable (« suivi.laposte.fr » → « laposte.fr »), l'extension, l'adresse numérique,
le raccourcisseur, la messagerie (WhatsApp, Telegram), l'hébergeur gratuit, le faux identifiant avant un « @ ».
"""

from __future__ import annotations

import ipaddress
import re
import urllib.parse
from dataclasses import dataclass

# Suffixes publics à deux niveaux (extrait de la Public Suffix List) et hébergeurs où chaque sous-domaine
# appartient à quelqu'un de différent.
SUFFIXES_DOUBLES = frozenset(
    {
        "gouv.fr", "asso.fr", "com.fr", "nom.fr", "presse.fr", "tm.fr", "co.uk", "org.uk", "ac.uk", "gov.uk",
        "me.uk", "com.au", "net.au", "co.nz", "com.br", "co.jp", "com.cn", "co.za", "com.tr", "com.es", "co.in",
        "com.mx", "com.ar", "co.il", "com.sg", "com.hk", "co.kr",
    }
)  # fmt: skip
HEBERGEURS = frozenset(
    {
        "github.io", "gitlab.io", "netlify.app", "vercel.app", "pages.dev", "workers.dev", "web.app",
        "firebaseapp.com", "herokuapp.com", "blogspot.com", "wixsite.com", "weebly.com", "glitch.me",
        "azurewebsites.net", "appspot.com", "000webhostapp.com", "r2.dev", "ngrok.io", "ngrok-free.app",
        "replit.app", "onrender.com", "webflow.io", "myshopify.com", "square.site", "godaddysites.com",
        "framer.website", "carrd.co", "jimdosite.com", "wordpress.com", "sharepoint.com", "ipfs.io", "dweb.link",
    }
)  # fmt: skip
HEBERGEURS_PAR_CHEMIN = frozenset(
    {"sites.google.com", "docs.google.com", "forms.gle", "storage.googleapis.com", "s3.amazonaws.com",
     "telegra.ph", "linktr.ee", "notion.site"}
)  # fmt: skip
RACCOURCISSEURS = frozenset(
    {
        "bit.ly", "bitly.com", "tinyurl.com", "t.co", "goo.su", "cutt.ly", "rb.gy", "is.gd", "v.gd", "ow.ly",
        "buff.ly", "shorturl.at", "tiny.cc", "s.id", "t.ly", "urlz.fr", "lc.cx", "rebrand.ly", "bl.ink",
        "short.io", "shorte.st", "adf.ly", "tr.im", "x.co", "soo.gd", "clck.ru", "u.to", "me2.do", "qrco.de",
        "shorturl.com", "tiny.one", "lnkd.in", "smarturl.it", "linkr.it", "2u.pw", "cli.re", "snip.ly",
        "shorturl.fr", "raccourci.fr", "kutt.it",
    }
)  # fmt: skip
MESSAGERIES = frozenset({"wa.me", "api.whatsapp.com", "chat.whatsapp.com", "t.me", "telegram.me", "m.me"})
# Les extensions les plus utilisées par les arnaques (listes publiques des extensions les plus abusées).
EXTENSIONS_RISQUEES = frozenset(
    {
        "top", "xyz", "icu", "cyou", "sbs", "cfd", "rest", "lol", "monster", "buzz", "click", "link", "live",
        "online", "site", "shop", "store", "club", "vip", "win", "work", "support", "bond", "help", "cc", "tk",
        "ml", "ga", "cf", "gq", "pw", "su", "ws", "fun", "space", "website", "best", "run", "today", "life",
        "world", "digital", "loan", "bid", "racing", "date", "download", "review", "stream", "gdn", "men", "kim",
        "country", "science", "party", "trade", "webcam", "accountant", "faith", "cricket", "me", "app", "info",
        "services", "money", "finance",
    }
)  # fmt: skip
EXTENSIONS_TRES_RISQUEES = EXTENSIONS_RISQUEES - {"me", "app", "info", "shop", "store", "services", "live", "link"}


@dataclass(frozen=True)
class InfoLien:
    url: str
    hote: str
    domaine: str  # enregistrable
    extension: str
    ip: bool
    https: bool
    arobase: bool  # « https://ameli.fr@evil.example/… » : ce qui précède le @ n'est pas le site
    raccourci: bool
    messagerie: bool
    hebergeur: bool


def hote_de(url: str) -> str:
    try:
        morceaux = urllib.parse.urlsplit(url if "://" in url else "https://" + url)
        return (morceaux.hostname or "").rstrip(".").lower()
    except ValueError:
        return ""


def domaine_enregistrable(hote: str) -> str:
    h = hote.rstrip(".").lower()
    try:
        ipaddress.ip_address(h)
        return h
    except ValueError:
        pass
    labels = h.split(".")
    if len(labels) <= 2:
        return h
    deux = ".".join(labels[-2:])
    if deux in SUFFIXES_DOUBLES or deux in HEBERGEURS:
        return ".".join(labels[-3:])
    return deux


def analyser(url: str) -> InfoLien:
    morceaux = urllib.parse.urlsplit(url if "://" in url else "https://" + url)
    hote = (morceaux.hostname or "").rstrip(".").lower()
    try:
        ipaddress.ip_address(hote)
        ip = True
    except ValueError:
        ip = bool(re.fullmatch(r"\d+", hote)) or bool(re.fullmatch(r"0x[0-9a-f]+", hote))
    domaine = domaine_enregistrable(hote)
    extension = hote.rsplit(".", 1)[-1] if "." in hote and not ip else ""
    hebergeur = any(hote.endswith("." + h) for h in HEBERGEURS) or hote in HEBERGEURS_PAR_CHEMIN
    return InfoLien(
        url=url,
        hote=hote,
        domaine=domaine,
        extension=extension,
        ip=ip,
        https=morceaux.scheme == "https",
        arobase="@" in morceaux.netloc,
        raccourci=domaine in RACCOURCISSEURS or hote in RACCOURCISSEURS,
        messagerie=hote in MESSAGERIES,
        hebergeur=hebergeur,
    )


def domaine_affiche(texte: str) -> str | None:
    """Si le texte d'un lien ressemble à une adresse (« www.ameli.fr », « https://… »), son domaine."""
    t = texte.strip().strip("<>()[]")
    if not t or " " in t:
        return None
    if re.match(r"(?i)^(https?://)?(www\.)?([a-z0-9\-]+\.)+[a-z]{2,}(/.*)?$", t):
        return domaine_enregistrable(hote_de(t))
    return None
