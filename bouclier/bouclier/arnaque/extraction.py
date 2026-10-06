"""Extraction : un SMS, un mail (.eml), un texte ou une capture d'écran deviennent un `Message`.

- Mail : en-têtes (expéditeur, Reply-To, Return-Path, résultats d'authentification), texte brut, texte du HTML
  (ce qui s'affiche) et, pour chaque lien, le texte affiché ET l'adresse réelle (`href`). Les commentaires et le
  texte caché du HTML sont gardés à part : jamais montrés à l'IA, mais cherchés pour des instructions pièges.
- Encodages : quoted-printable, base64, ISO-8859-1 et jeux de caractères inconnus (repli sans plantage).
- Taille : un message de 5 Mo est lu, mais seuls les 200 000 premiers caractères de texte sont analysés.
- Capture d'écran : reconnaissance du texte en local (Apple Vision sur le Mac), voir `ocr.py`.

Aucun lien n'est jamais ouvert ici : on lit le texte de l'adresse, rien d'autre.
"""

from __future__ import annotations

import email
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.message import Message as MessageEmail
from email.policy import default
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from pathlib import Path

LIMITE_TEXTE = 200_000
EXTENSIONS_IMAGES = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".tif", ".tiff", ".gif", ".bmp"}

_TLD_NUS = (
    "fr|com|net|org|info|eu|be|ch|de|uk|es|it|io|co|me|cc|tv|ly|gy|gd|at|id|cx|to|ws|su|ru|cn|tk|ml|ga|cf|gq|pw|"
    "top|xyz|online|site|shop|store|club|vip|live|icu|app|help|work|win|click|link|buzz|cfd|sbs|cyou|rest|lol|"
    "monster|support|services|bond|biz|pro|world|today|life|fun|space|website|tech|digital|page|run|best|"
    "finance|money|bank|gouv|net|mobi|asia|us"
)
_URL = re.compile(
    r"(?i)\b((?:https?|hxxps?)://[^\s<>\"'«»]+"
    r"|www\.[^\s<>\"'«»]+"
    r"|(?<![@\w.\-])(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+(?:" + _TLD_NUS + r")\b(?:/[^\s<>\"'«»]*)?)"
)
_PONCTUATION_FINALE = ".,;:!?)]}>'\"»…"


@dataclass
class Lien:
    url: str  # adresse réelle, avec protocole
    affiche: str = ""  # texte affiché (vide pour une adresse écrite en clair)
    source: str = "texte"  # "texte" ou "html"


@dataclass
class Message:
    canal: str  # "sms", "mail", "texte" ou "image"
    texte: str
    sujet: str = ""
    expediteur_nom: str = ""
    expediteur_adresse: str = ""
    reply_to: str = ""
    return_path: str = ""
    authentification: str = ""
    desinscription: bool = False
    liens: list[Lien] = field(default_factory=list)
    texte_cache: str = ""  # commentaires HTML, texte invisible : jamais envoyé à l'IA
    pieces_jointes: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    @property
    def texte_complet(self) -> str:
        """Ce que voit la personne : sujet, nom de l'expéditeur, texte."""
        return "\n".join(p for p in (self.expediteur_nom, self.sujet, self.texte) if p)


def _nettoyer_url(brute: str) -> str:
    url = brute.strip()
    # La ponctuation qui suit une adresse n'en fait pas partie, sauf une parenthèse fermante qui a son ouvrante.
    while url and url[-1] in _PONCTUATION_FINALE:
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        url = url[:-1]
    if url.lower().startswith("hxxp"):
        url = "http" + url[4:]
    if not re.match(r"(?i)^https?://", url):
        url = "https://" + url if not url.lower().startswith("www.") else "https://" + url
    return url


def urls_du_texte(texte: str) -> list[str]:
    vus: list[str] = []
    for m in _URL.finditer(texte):
        brute = m.group(1)
        # « 1,99€ » ou « 12.10 » ne sont pas des adresses ; une adresse e-mail non plus (exclue par le motif).
        if re.fullmatch(r"[\d.]+", brute.split("/")[0]):
            continue
        url = _nettoyer_url(brute)
        if url not in vus:
            vus.append(url)
    return vus


class _LecteurHtml(HTMLParser):
    _CACHES = {"script", "style", "head", "title", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texte: list[str] = []
        self.cache: list[str] = []
        self.liens: list[tuple[str, str]] = []
        self._pile_cachee = 0
        self._lien: tuple[str, list[str]] | None = None
        self._invisible = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        style = a.get("style", "").replace(" ", "").lower()
        if tag in self._CACHES:
            self._pile_cachee += 1
        elif "display:none" in style or "visibility:hidden" in style or "font-size:0" in style or "hidden" in a:
            self._invisible += 1
        if tag == "a" and a.get("href"):
            self._lien = (a["href"].strip(), [])
        if tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3", "table"):
            self.texte.append("\n")
        if tag == "img" and a.get("alt"):
            self.texte.append(f" {a['alt']} ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._CACHES and self._pile_cachee:
            self._pile_cachee -= 1
        if tag == "a" and self._lien is not None:
            href, morceaux = self._lien
            self.liens.append(("".join(morceaux).strip(), href))
            self._lien = None
        if tag in ("span", "div", "p", "font", "td") and self._invisible:
            self._invisible -= 1

    def handle_data(self, data: str) -> None:
        if self._pile_cachee:
            return
        if self._invisible:
            self.cache.append(data)
            return
        self.texte.append(data)
        if self._lien is not None:
            self._lien[1].append(data)

    def handle_comment(self, data: str) -> None:
        self.cache.append(data)


def html_vers_texte(html: str) -> tuple[str, list[tuple[str, str]], str]:
    """(texte affiché, liens (texte affiché, href), texte caché)."""
    lecteur = _LecteurHtml()
    try:
        lecteur.feed(html)
        lecteur.close()
    except Exception:  # noqa: BLE001 - un HTML abîmé ne doit rien casser : on garde ce qui a été lu
        pass
    texte = re.sub(r"[ \t\r\f\v]+", " ", "".join(lecteur.texte))
    texte = re.sub(r"\n\s*\n+", "\n\n", texte).strip()
    return texte, lecteur.liens, " ".join(lecteur.cache).strip()


def _contenu(partie: MessageEmail) -> str:
    """Le texte d'une partie, quel que soit son encodage annoncé (ou inconnu)."""
    try:
        contenu = partie.get_content() if isinstance(partie, EmailMessage) else None
        if isinstance(contenu, str):
            return contenu
    except (LookupError, UnicodeError, ValueError, AssertionError):
        pass
    brut = partie.get_payload(decode=True)
    if not isinstance(brut, bytes):
        return str(partie.get_payload() or "")
    jeu = partie.get_content_charset() or "utf-8"
    for essai in (jeu, "utf-8", "cp1252", "latin-1"):
        try:
            return brut.decode(essai)
        except (LookupError, UnicodeDecodeError):
            continue
    return brut.decode("utf-8", "replace")


def _entete(m: MessageEmail, nom: str) -> str:
    try:
        valeur = m.get(nom)
    except Exception:  # noqa: BLE001 - un en-tête mal formé est ignoré
        return ""
    return str(valeur) if valeur is not None else ""


def ressemble_a_un_mail(brut: bytes) -> bool:
    debut = brut[:4096].decode("utf-8", "replace")
    entetes = re.findall(r"(?im)^(from|to|subject|date|received|return-path|delivered-to|mime-version|message-id):",
                         debut)  # fmt: skip
    return len({e.lower() for e in entetes}) >= 2


def depuis_eml(brut: bytes) -> Message:
    m = email.message_from_bytes(brut, policy=default)
    nom, adresse = parseaddr(_entete(m, "From"))
    reply = ", ".join(a for _, a in getaddresses([_entete(m, "Reply-To")]) if a)
    # Le premier « Authentication-Results » est celui du serveur qui a reçu le mail (les suivants peuvent être faux).
    auth_tous = m.get_all("Authentication-Results") or []
    auth = str(auth_tous[0]) if auth_tous else ""
    textes: list[str] = []
    liens: list[Lien] = []
    cache: list[str] = []
    pieces: list[str] = []
    html_vu = False
    for partie in m.walk():
        if partie.is_multipart():
            continue
        disposition = partie.get_content_disposition()
        if disposition == "attachment" or (partie.get_filename() and disposition != "inline"):
            pieces.append(partie.get_filename() or "pièce jointe")
            continue
        type_ = partie.get_content_type()
        if type_ == "text/plain":
            textes.append(_contenu(partie))
        elif type_ == "text/html":
            texte_html, liens_html, cache_html = html_vers_texte(_contenu(partie))
            html_vu = True
            if not textes or len(texte_html) > 2 * len(" ".join(textes)):
                textes.append(texte_html)
            for affiche, href in liens_html:
                if re.match(r"(?i)^(https?|hxxps?):", href) or re.match(r"(?i)^www\.", href):
                    liens.append(Lien(_nettoyer_url(href), affiche, "html"))
            if cache_html:
                cache.append(cache_html)
    texte = "\n".join(t.strip() for t in textes if t.strip()).replace("\r\n", "\n").replace("\r", "\n")
    message = Message(
        canal="mail",
        texte=texte[:LIMITE_TEXTE],
        sujet=_entete(m, "Subject"),
        expediteur_nom=nom.strip(),
        expediteur_adresse=adresse.strip().lower(),
        reply_to=reply.lower(),
        return_path=parseaddr(_entete(m, "Return-Path"))[1].lower(),
        authentification=auth,
        desinscription=bool(_entete(m, "List-Unsubscribe")),
        texte_cache=" ".join(cache)[:LIMITE_TEXTE],
        pieces_jointes=pieces,
    )
    if len(texte) > LIMITE_TEXTE:
        message.avertissements.append("message très long : seul le début a été analysé")
    connus = {lien.url for lien in liens}
    for url in urls_du_texte(message.texte):
        if url not in connus:
            liens.append(Lien(url))
            connus.add(url)
    message.liens = liens
    if not html_vu and not texte and not pieces:
        message.avertissements.append("mail sans texte lisible")
    return message


def depuis_texte(texte: str, canal: str = "texte") -> Message:
    texte = texte.replace("\r\n", "\n")[:LIMITE_TEXTE]
    return Message(canal=canal, texte=texte, liens=[Lien(u) for u in urls_du_texte(texte)])


LecteurImage = Callable[[Path], tuple[str, float]]


def depuis_image(chemin: Path, lire_image: LecteurImage) -> Message:
    texte, confiance = lire_image(chemin)
    message = depuis_texte(texte, canal="image")
    if not texte.strip():
        message.avertissements.append("je n'ai trouvé aucun texte dans l'image")
    elif confiance < 0.5:
        message.avertissements.append("image floue : une partie du texte a peut-être été mal lue")
    return message


def depuis_fichier(chemin: Path, lire_image: LecteurImage | None = None) -> Message:
    if chemin.suffix.lower() in EXTENSIONS_IMAGES:
        if lire_image is None:
            raise ValueError("lecture des images indisponible sur cet ordinateur")
        return depuis_image(chemin, lire_image)
    brut = chemin.read_bytes()
    if chemin.suffix.lower() == ".eml" or ressemble_a_un_mail(brut):
        return depuis_eml(brut)
    for essai in ("utf-8", "cp1252", "latin-1"):
        try:
            return depuis_texte(brut.decode(essai))
        except UnicodeDecodeError:
            continue
    return depuis_texte(brut.decode("utf-8", "replace"))  # pragma: no cover - latin-1 décode toujours
