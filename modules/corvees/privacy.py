"""La vie privée, AVANT toute écriture : exclusions (applis, sites, dossiers) et caviardage des secrets.

Tout événement passe par Gardien.nettoyer() avant d'atteindre la base : c'est le seul chemin d'écriture.
Les secrets sont remplacés par des étiquettes ([e-mail], [IBAN]…) ; rien de ce qu'ils contenaient ne reste.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from modules.corvees import config

if TYPE_CHECKING:
    from modules.corvees.db import Evenement

# --- Caviardage --------------------------------------------------------------------------------------------

_URL = re.compile(r"(?i)\b((?:https?|ftp)://)(?:[^\s/@]+@)?([^\s?#]*)[?#][^\s]*")
_URL_IDENTIFIANTS = re.compile(r"(?i)\b((?:https?|ftp)://)[^\s/@]+@")
_CLE_PRIVEE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)
_JETONS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{8,}=*"),
]
# Mots de passe passés en ligne de commande
_OPTIONS_SECRETES = re.compile(
    r"(?i)(--(?:password|passwd|pass|pwd|token|secret|api[-_]?key|apikey|access[-_]?key|auth[-_]?token))(=|\s+)"
    r"(?:'[^']*'|\"[^\"]*\"|\S+)"
)
_AFFECTATIONS_SECRETES = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|PWD|PASS|TOKEN|SECRET|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|AUTH))"
    r"(\s*[=:]\s*)(?:'[^']*'|\"[^\"]*\"|\S+)"
)
_COMMANDES_AVEC_P = re.compile(
    r"(?i)\b(mysql|mysqldump|mysqladmin|mariadb|mariadb-dump|sshpass|smbclient)\b([^|;&]*?)\s-p\s*(?:'[^']*'|\"[^\"]*\"|\S+)"
)
_P_COLLE = re.compile(r"(?<!\S)-p(?:'[^']*'|\"[^\"]*\")")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
_TELEPHONE = re.compile(r"(?<![\d+])(?:\+33\s?|0033\s?|0)[1-9](?:[\s.\-]?\d{2}){4}(?!\d)")
_IBAN = re.compile(r"(?<![A-Z0-9])([A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30})(?![A-Z0-9])")
_CARTE = re.compile(r"(?<![\d])(?:\d[ \-]?){12,18}\d(?![\d])")
_HEXA = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32,}(?![0-9A-Fa-f])")
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/=_\-])(?:[A-Za-z0-9+_\-]{40,}|[A-Za-z0-9+/]{40,}={1,2})(?![A-Za-z0-9+/=_\-])")


def _iban_valide(brut: str) -> bool:
    iban = brut.replace(" ", "").upper()
    if not 15 <= len(iban) <= 34:
        return False
    deplace = iban[4:] + iban[:4]  # le motif garantit des lettres et des chiffres seulement
    return int("".join(str(int(c, 36)) for c in deplace)) % 97 == 1


def _luhn(nombre: str) -> bool:
    chiffres = [int(c) for c in nombre if c.isdigit()]  # 13 à 19 chiffres, garanti par le motif
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        if i % 2 == 1:
            c *= 2
            if c > 9:
                c -= 9
        total += c
    return total % 10 == 0


def _base64_probable(mot: str) -> bool:
    return any(c.isdigit() for c in mot) and any(c.isupper() for c in mot) and any(c.islower() for c in mot)


def caviarder(texte: str) -> str:
    """Le texte sans aucun secret : chaque secret devient une étiquette entre crochets."""
    if not texte:
        return texte
    t = _CLE_PRIVEE.sub("[clé privée]", texte)
    t = _URL.sub(lambda m: m.group(1) + m.group(2), t)  # paramètres d'URL et identifiants retirés
    t = _URL_IDENTIFIANTS.sub(lambda m: m.group(1), t)
    for motif in _JETONS:
        t = motif.sub("[secret]", t)
    t = _OPTIONS_SECRETES.sub(lambda m: f"{m.group(1)}{m.group(2)}[secret]", t)
    t = _AFFECTATIONS_SECRETES.sub(lambda m: f"{m.group(1)}{m.group(2)}[secret]", t)
    t = _COMMANDES_AVEC_P.sub(lambda m: f"{m.group(1)}{m.group(2)} -p [secret]", t)
    t = _P_COLLE.sub("-p[secret]", t)
    t = _EMAIL.sub("[e-mail]", t)
    t = _IBAN.sub(lambda m: "[IBAN]" if _iban_valide(m.group(1)) else m.group(0), t)
    t = _CARTE.sub(lambda m: "[carte]" if _luhn(m.group(0)) else m.group(0), t)
    t = _TELEPHONE.sub("[téléphone]", t)
    t = _HEXA.sub("[secret]", t)
    t = _BASE64.sub(
        lambda m: "[secret]" if (m.group(0).endswith("=") or _base64_probable(m.group(0))) else m.group(0), t
    )
    return t


def caviarder_valeur(valeur: Any) -> Any:
    """Caviarde récursivement les textes d'une structure (attributs d'un événement)."""
    if isinstance(valeur, str):
        return caviarder(valeur)
    if isinstance(valeur, list):
        return [caviarder_valeur(v) for v in valeur]
    if isinstance(valeur, dict):
        return {k: caviarder_valeur(v) for k, v in valeur.items()}
    return valeur


# --- Exclusions --------------------------------------------------------------------------------------------


def simple(texte: str) -> str:
    """Minuscules, sans accents, apostrophes droites : « Crédit Agricole » = « credit agricole »."""
    texte = unicodedata.normalize("NFKD", str(texte).replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texte.lower()).strip()


def domaine_de(adresse: str) -> str:
    """« https://www.boursorama.com/compte » → « boursorama.com »."""
    sans_schema = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", adresse.strip().lower())
    hote = re.split(r"[/?#]", sans_schema, maxsplit=1)[0].rsplit("@", 1)[-1].split(":")[0]
    return hote[4:] if hote.startswith("www.") else hote


class Gardien:
    """Décide de ce qui peut être écrit, et sous quelle forme."""

    def __init__(self, reglages: dict[str, Any], sel: bytes):
        self.applis = [x for x in (simple(a) for a in config.applis_exclues(reglages)) if x]
        self.domaines = [d.strip().lower() for d in config.domaines_exclus(reglages) if str(d).strip()]
        self.dossiers = [str(Path(d).expanduser()) for d in reglages["exclusions"]["dossiers"] if str(d).strip()]
        self.sel = sel

    # -- questions simples --
    def appli_exclue(self, nom: str, bundle: str = "") -> bool:
        n, b = simple(nom), simple(bundle)
        for a in self.applis:
            if a == n or a == b or (len(a) >= 4 and (n.startswith(a) or b.startswith(a))):
                return True
        return False

    def domaine_exclu(self, adresse_ou_domaine: str) -> bool:
        d = domaine_de(adresse_ou_domaine)
        for exclu in self.domaines:
            if "." in exclu:
                if d == exclu or d.endswith("." + exclu):
                    return True
            elif exclu in d:
                return True
        return False

    def chemin_exclu(self, chemin: str) -> bool:
        absolu = str(Path(chemin).expanduser())
        return any(absolu == d or absolu.startswith(d.rstrip("/") + "/") for d in self.dossiers)

    def empreinte(self, donnees: bytes | str) -> str:
        """Empreinte HMAC salée : permet de reconnaître « la même chose » sans jamais la garder."""
        brut = donnees.encode() if isinstance(donnees, str) else donnees
        return hmac.new(self.sel, brut, hashlib.sha256).hexdigest()[:16]

    # -- le filtre unique avant écriture --
    def _mentionne_exclu(self, evt: Evenement) -> bool:
        a = evt.attrs
        for cle in ("appli", "source", "destination"):
            if isinstance(a.get(cle), str) and self.appli_exclue(a[cle], a.get("bundle", "") if cle == "appli" else ""):
                return True
        if isinstance(a.get("bundle"), str) and a["bundle"] and self.appli_exclue("", a["bundle"]):
            return True
        if isinstance(a.get("domaine"), str) and self.domaine_exclu(a["domaine"]):
            return True
        for cle in ("chemin", "de", "vers"):
            if isinstance(a.get(cle), str) and self.dossiers and self.chemin_exclu(a[cle]):
                return True
        corps = evt.token.split(":", 1)[1] if ":" in evt.token else evt.token
        if evt.kind in ("app", "fen"):
            appli = corps.split(":", 1)[0] if evt.kind == "fen" else corps
            if self.appli_exclue(appli):
                return True
        if evt.kind == "clip":
            if any(self.appli_exclue(x) for x in re.split(r"→", corps)):
                return True
        if evt.kind == "url" and self.domaine_exclu(corps):
            return True
        return False

    def nettoyer(self, evt: Evenement) -> Evenement | None:
        """None si l'événement touche à une exclusion ; sinon l'événement caviardé, prêt à être écrit."""
        if self._mentionne_exclu(evt):
            return None
        attrs = caviarder_valeur(evt.attrs)
        token = caviarder(evt.token)
        if evt.kind == "fen":
            titre = token.partition(":")[2].partition(":")[2]
            if any(motif in simple(titre) for motif in _TITRES_SENSIBLES):
                return None
        return replace(evt, token=token, attrs=attrs)


# Une fenêtre dont le titre contient ces mots (banque, santé, mot de passe…) n'est jamais notée.
_TITRES_SENSIBLES = [
    "banque",
    "bank",
    "boursorama",
    "credit agricole",
    "societe generale",
    "caisse d'epargne",
    "credit mutuel",
    "impots",
    "ameli",
    "doctolib",
    "mot de passe",
    "password",
    "navigation privee",
    "private browsing",
]


def sel(dossier: Path) -> bytes:
    """Le sel des empreintes (32 octets aléatoires), créé une fois, lisible par toi seul."""
    fichier = dossier / "sel"
    if fichier.exists() and len(fichier.read_bytes()) == 32:
        return fichier.read_bytes()
    dossier.mkdir(parents=True, exist_ok=True)
    brut = secrets.token_bytes(32)
    descripteur = os.open(fichier, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descripteur, "wb") as f:
        f.write(brut)
    return brut
