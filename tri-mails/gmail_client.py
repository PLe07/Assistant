"""Connexion à Gmail (OAuth).

Ce module ne fait que se connecter et vérifier la boîte.
Il n'envoie aucun mail et n'en met aucun à la corbeille.
"""

import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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
