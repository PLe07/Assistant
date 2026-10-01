"""Migration des données de tri-mails/ vers donnees/mails/.

Uniquement des COPIES : tri-mails/ n'est jamais modifié, et un fichier déjà présent
dans donnees/mails/ n'est jamais écrasé. Relançable sans risque.
"""

import os
import re
import shutil
import sqlite3
from datetime import datetime

from core import config as coeur
from modules.mails import parametres as p
from modules.mails.memoire import Memoire

SOURCE = coeur.RACINE / "tri-mails"
FICHIERS = [
    ("memoire.db", "mémoire (mails déjà triés + date de mise en service)"),
    ("token.json", "jeton Gmail"),
    ("credentials.json", "identité de l'appli Google"),
    ("regles_perso.txt", "tes règles perso"),
    ("jamais_archiver.txt", "expéditeurs jamais archivés"),
]


def _copier_base(source, destination) -> None:
    """Copie cohérente d'une base SQLite, même si l'ancien service est en train d'y écrire."""
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def _copier_adresse() -> str:
    """Recopie GMAIL_ATTENDU de tri-mails/.env vers le .env de l'assistant, sans l'afficher."""
    env = coeur.RACINE / ".env"
    contenu = env.read_text(encoding="utf-8") if env.exists() else ""
    if re.search(r"^GMAIL_ATTENDU=\S+", contenu, re.M):
        return "= déjà présente dans .env"
    source = SOURCE / ".env"
    ligne = None
    if source.exists():
        ligne = next((l for l in source.read_text(encoding="utf-8").splitlines()
                      if re.match(r"^GMAIL_ATTENDU=\S+", l)), None)
    if not ligne:
        return "⚠️ absente de tri-mails/.env : ajoute GMAIL_ATTENDU=… dans .env à la main"
    with open(env, "a", encoding="utf-8") as f:
        if contenu and not contenu.endswith("\n"):
            f.write("\n")
        f.write(ligne + "\n")
    os.chmod(env, 0o600)
    return "+ copiée dans .env"


def migrer() -> int:
    if not SOURCE.exists():
        print(f"⛔ Dossier introuvable : {SOURCE}")
        return 1
    p.preparer_dossier()
    print(f"Copie de tri-mails/ vers {p.DOSSIER.relative_to(coeur.RACINE)}/ :")
    for nom, description in FICHIERS:
        source, destination = SOURCE / nom, p.DOSSIER / nom
        if not source.exists():
            print(f"  · {description} : absent de tri-mails/, rien à copier")
            continue
        if destination.exists():
            print(f"  = {description} : déjà présent, je ne l'écrase pas")
            continue
        if nom.endswith(".db"):
            _copier_base(source, destination)
        else:
            shutil.copy2(source, destination)
        os.chmod(destination, 0o600)
        print(f"  + {description} : copié")
    print(f"  {_copier_adresse()} (adresse de la boîte, GMAIL_ATTENDU)")

    memoire = Memoire()
    try:
        depart = memoire.lire("date_depart")
        n = memoire.db.execute("SELECT COUNT(*) FROM mails WHERE statut = 'etiquete'").fetchone()[0]
    finally:
        memoire.fermer()
    print("\nRésumé")
    if depart:
        print(f"  Mise en service conservée : {datetime.fromtimestamp(float(depart)):%d/%m/%Y %H:%M}")
        print(f"  Mails déjà triés connus : {n} (ils ne seront jamais retraités)")
    else:
        print("  ⚠️  Pas de date de mise en service : la mémoire n'a pas été trouvée.")
    print("  tri-mails/ n'a pas été modifié (sauvegarde intacte).")
    return 0
