"""Test de connexion à Gmail. LECTURE SEULE : aucun mail n'est modifié.

Usage (dans ~/Assistant/tri-mails, avec (.venv) activé) :
    python verifier_connexion.py

La 1re fois, le navigateur s'ouvre pour autoriser l'appli, puis le jeton
est enregistré dans token.json (qui reste sur ton Mac).
"""

import os
import sys

from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from gmail_client import (
    DOSSIER,
    TOKEN,
    ConnexionImpossible,
    MauvaiseBoite,
    service_gmail,
    verifier_boite,
)


def main() -> int:
    load_dotenv(DOSSIER / ".env")
    attendue = os.getenv("GMAIL_ATTENDU", "")
    if not attendue.strip():
        print("⛔ GMAIL_ATTENDU est vide : écris l'adresse de la boîte à trier dans le fichier .env.")
        return 1

    try:
        service = service_gmail(interactif=True)
        adresse = verifier_boite(service, attendue)
        boite = service.users().labels().get(userId="me", id="INBOX").execute()
    except MauvaiseBoite as e:
        print(f"⛔ Mauvaise boîte : {e}")
        if TOKEN.exists():
            TOKEN.unlink()  # jeton du mauvais compte : on l'oublie
            print("   J'ai effacé token.json. Relance la commande et choisis le bon compte.")
        return 1
    except ConnexionImpossible as e:
        print(f"⛔ {e}")
        return 1
    except HttpError as e:
        print(f"⛔ Gmail a répondu une erreur ({e.status_code}) : {e.reason}")
        return 1
    except OSError as e:
        print(f"⛔ Problème réseau : {e}")
        return 1

    print(f"✅ Connecté à {adresse} : c'est bien la boîte attendue.")
    print(
        f"   Boîte de réception : {boite['messagesTotal']} mails, "
        f"dont {boite['messagesUnread']} non lus."
    )
    print("   Aucun mail n'a été modifié.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
