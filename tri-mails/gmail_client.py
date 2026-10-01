"""Connexion à Gmail (OAuth) et lecture des mails.

Ce module se connecte, vérifie la boîte et LIT les mails.
Il n'envoie aucun mail et n'en met aucun à la corbeille.
"""

import base64
import os
import re
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DOSSIER = Path(__file__).resolve().parent
CREDENTIALS = DOSSIER / "credentials.json"  # carte d'identité de l'appli (Google Cloud)
TOKEN = DOSSIER / "token.json"  # jeton d'accès, créé à la 1re connexion

# Plus petite autorisation qui permet de poser des étiquettes.
# Elle interdit la suppression définitive.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class ConnexionImpossible(Exception):
    """Gmail inaccessible : jeton absent, expiré ou révoqué."""


class MauvaiseBoite(Exception):
    """Connecté à une autre boîte que celle attendue dans le .env."""


def _sauver_jeton(creds: Credentials) -> None:
    # Fichier lisible par toi seul (droits 600).
    fd = os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())


def _connexion_navigateur() -> Credentials:
    if not CREDENTIALS.exists():
        raise ConnexionImpossible(
            f"Fichier introuvable : {CREDENTIALS}\n"
            "   Refais l'étape A6 (ranger le fichier téléchargé depuis Google Cloud)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
    return flow.run_local_server(
        port=0,
        prompt="select_account consent",  # force le choix du compte Google
        timeout_seconds=300,
        authorization_prompt_message=(
            "Ton navigateur va s'ouvrir. S'il ne s'ouvre pas, copie ce lien :\n{url}\n"
        ),
        success_message="Connexion réussie. Tu peux fermer cet onglet et revenir au Terminal.",
    )


def obtenir_identifiants(interactif: bool) -> Credentials:
    """Renvoie des identifiants valides.

    interactif=True  : peut ouvrir le navigateur (utilisation à la main).
    interactif=False : n'ouvre jamais rien (arrière-plan) ; lève ConnexionImpossible.
    """
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _sauver_jeton(creds)
            return creds
        except RefreshError as e:
            if not interactif:
                raise ConnexionImpossible(
                    "Jeton Gmail expiré ou révoqué. Lance : python verifier_connexion.py"
                ) from e

    if not interactif:
        raise ConnexionImpossible(
            "Aucun jeton Gmail valide. Lance : python verifier_connexion.py"
        )

    creds = _connexion_navigateur()
    _sauver_jeton(creds)
    return creds


def service_gmail(interactif: bool = False):
    """Objet qui permet de parler à l'API Gmail."""
    creds = obtenir_identifiants(interactif)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def adresse_connectee(service) -> str:
    return service.users().getProfile(userId="me").execute()["emailAddress"]


def verifier_boite(service, attendue: str) -> str:
    """Garde-fou : refuse de continuer si ce n'est pas la boîte attendue."""
    attendue = (attendue or "").strip().lower()
    if not attendue:
        raise MauvaiseBoite("GMAIL_ATTENDU est vide dans le fichier .env.")
    reelle = adresse_connectee(service)
    if reelle.lower() != attendue:
        raise MauvaiseBoite(f"Connecté à {reelle}, alors que la boîte attendue est {attendue}.")
    return reelle


# --- Lecture des mails (lecture seule) ----------------------------------------

CATEGORIES = {
    "CATEGORY_PERSONAL": "Principale",
    "CATEGORY_SOCIAL": "Réseaux sociaux",
    "CATEGORY_PROMOTIONS": "Promotions",
    "CATEGORY_UPDATES": "Notifications",
    "CATEGORY_FORUMS": "Forums",
}


@dataclass
class Mail:
    id: str
    date: datetime
    expediteur_nom: str
    expediteur_adresse: str
    destinataires: str  # toi seul / toi et d'autres / en copie / non nommé
    objet: str
    categorie: str  # catégorie Gmail (Promotions, Réseaux sociaux…) ou ""
    desinscription: bool  # présence d'un lien de désinscription (List-Unsubscribe)
    reponse: bool  # réponse dans une conversation existante
    extrait: str  # corps nettoyé et raccourci
    libelles: list


def lister_boite(service, maximum: int, requete: str | None = None) -> list[str]:
    """Identifiants des mails de la boîte de réception, du plus récent au plus ancien."""
    ids, page = [], None
    while len(ids) < maximum:
        rep = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=["INBOX"],
                q=requete,
                maxResults=min(100, maximum - len(ids)),
                pageToken=page,
            )
            .execute()
        )
        ids += [m["id"] for m in rep.get("messages", [])]
        page = rep.get("nextPageToken")
        if not page:
            break
    return ids[:maximum]


def lire_mail(service, msg_id: str, mon_adresse: str, longueur: int = 1500) -> Mail:
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    payload = msg.get("payload", {})
    entetes = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    libelles = msg.get("labelIds", [])

    nom, adresse = parseaddr(_decoder_entete(entetes.get("from", "")))
    objet = _decoder_entete(entetes.get("subject", "")).strip() or "(sans objet)"
    corps = _texte_du_mail(payload) or msg.get("snippet", "")

    return Mail(
        id=msg_id,
        date=datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000),
        expediteur_nom=nom or adresse,
        expediteur_adresse=adresse.lower(),
        destinataires=_destinataires(entetes, mon_adresse),
        objet=objet,
        categorie=next((CATEGORIES[l] for l in libelles if l in CATEGORIES), ""),
        desinscription="list-unsubscribe" in entetes,
        reponse="in-reply-to" in entetes or objet.lower().startswith(("re:", "re :")),
        extrait=nettoyer(corps, longueur),
        libelles=libelles,
    )


def _decoder_entete(valeur: str) -> str:
    if "=?" not in valeur:
        return valeur
    try:
        return str(make_header(decode_header(valeur)))
    except (ValueError, LookupError):
        return valeur


def _normaliser(adresse: str) -> str:
    """Gmail ignore les points et le +suffixe : jean.dupont+x@gmail.com = jeandupont@gmail.com."""
    adresse = adresse.strip().lower()
    local, _, domaine = adresse.partition("@")
    if domaine in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0].replace(".", "")
        domaine = "gmail.com"
    return f"{local}@{domaine}"


def _destinataires(entetes: dict, mon_adresse: str) -> str:
    moi = _normaliser(mon_adresse)
    a = {_normaliser(x) for _, x in getaddresses([entetes.get("to", "")]) if x}
    cc = {_normaliser(x) for _, x in getaddresses([entetes.get("cc", "")]) if x}
    if moi in a:
        return "toi seul" if a == {moi} and not cc else "toi et d'autres personnes"
    if moi in cc:
        return "toi en copie"
    return "adresse non nommée (liste de diffusion ou copie cachée)"


def _parties(partie: dict):
    yield partie
    for p in partie.get("parts") or []:
        yield from _parties(p)


def _decoder_corps(partie: dict) -> str:
    data = (partie.get("body") or {}).get("data")
    if not data:
        return ""
    brut = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    charset = "utf-8"
    for h in partie.get("headers", []):
        if h["name"].lower() == "content-type":
            m = re.search(r'charset="?([\w.-]+)', h["value"], re.I)
            if m:
                charset = m.group(1)
    try:
        return brut.decode(charset, errors="replace")
    except LookupError:
        return brut.decode("utf-8", errors="replace")


def _texte_du_mail(payload: dict) -> str:
    texte = html = ""
    for p in _parties(payload):
        if p.get("filename"):
            continue  # pièce jointe : jamais lue
        mime = p.get("mimeType", "")
        if mime == "text/plain" and not texte:
            texte = _decoder_corps(p)
        elif mime == "text/html" and not html:
            html = _decoder_corps(p)
    # Beaucoup de mails commerciaux ont une version texte vide (« voir en ligne »).
    if len(texte.strip()) >= 200 or not html:
        return texte
    return _html_vers_texte(html)


class _ExtracteurHTML(HTMLParser):
    BLOCS = {"p", "div", "br", "tr", "li", "table", "section", "article",
             "h1", "h2", "h3", "h4", "h5", "h6"}
    IGNORES = {"style", "script", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.morceaux, self._ignore = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORES:
            self._ignore += 1
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORES:
            self._ignore = max(0, self._ignore - 1)
        elif tag in self.BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, data):
        if not self._ignore:
            self.morceaux.append(data)


def _html_vers_texte(html: str) -> str:
    extracteur = _ExtracteurHTML()
    extracteur.feed(html)
    return "".join(extracteur.morceaux)


_INVISIBLES = re.compile("[​‌‍⁠﻿͏­]")
_URL = re.compile(r"https?://\S+")
_DEBUT_HISTORIQUE = re.compile(
    r"^(le .{0,150}a écrit\s?:|on .{0,150}wrote:"
    r"|-{3,}\s*(original message|message d'origine)\s*-{3,})$",
    re.I,
)


def nettoyer(texte: str, longueur: int = 1500) -> str:
    """Garde l'essentiel : sans historique cité, signature, liens ni blancs inutiles."""
    texte = _INVISIBLES.sub("", texte).replace("\r", "")
    lignes = []
    for ligne in texte.split("\n"):
        ligne = ligne.strip()
        if ligne == "--" or _DEBUT_HISTORIQUE.match(ligne):
            break  # signature ou début de l'historique de la conversation
        if ligne.startswith(">"):
            continue  # ligne citée d'un ancien message
        lignes.append(ligne)
    texte = _URL.sub("[lien]", "\n".join(lignes))
    texte = re.sub(r"[ \t\xa0]+", " ", texte)
    texte = re.sub(r"\n\s*\n+", "\n", texte).strip()
    if len(texte) > longueur:
        texte = texte[:longueur].rstrip() + " […]"
    return texte


# --- Étiquettes (création uniquement : aucun mail n'est touché ici) -------------


def etiquettes_existantes(service) -> dict:
    """Nom de l'étiquette → identifiant Gmail."""
    rep = service.users().labels().list(userId="me").execute()
    return {l["name"]: l["id"] for l in rep.get("labels", [])}


def creer_etiquette(service, nom: str, fond: str, texte: str) -> str:
    corps = {
        "name": nom,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
        "color": {"backgroundColor": fond, "textColor": texte},
    }
    try:
        return service.users().labels().create(userId="me", body=corps).execute()["id"]
    except HttpError as e:
        if e.status_code != 400:
            raise
        corps.pop("color")  # couleur refusée par Gmail : on crée quand même, sans couleur
        return service.users().labels().create(userId="me", body=corps).execute()["id"]
