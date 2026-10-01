"""Mémoire du tri (donnees/mails/memoire.db) : les mails déjà traités, pour ne jamais les retraiter."""

import os
import sqlite3
from datetime import datetime

from modules.mails import parametres as p

FICHIER = p.MEMOIRE


class Memoire:
    def __init__(self, fichier=FICHIER):
        p.preparer_dossier()
        self.db = sqlite3.connect(fichier)
        os.chmod(fichier, 0o600)  # lisible par toi seul (contient expéditeurs et objets)
        with self.db:
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS parametres (cle TEXT PRIMARY KEY, valeur TEXT);
                CREATE TABLE IF NOT EXISTS mails (
                    id TEXT PRIMARY KEY, statut TEXT, traite_le TEXT, recu_le TEXT,
                    bac TEXT, source TEXT, vaut_mon_temps INTEGER, raison TEXT,
                    expediteur TEXT, objet TEXT
                );
                CREATE TABLE IF NOT EXISTS echecs (id TEXT PRIMARY KEY, tentatives INTEGER);
                """
            )

    # --- Paramètres (date de mise en service, pause après panne) ---------------

    def lire(self, cle: str) -> str | None:
        ligne = self.db.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
        return ligne[0] if ligne else None

    def ecrire(self, cle: str, valeur) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO parametres VALUES (?, ?)", (cle, str(valeur)))

    # --- Mails ----------------------------------------------------------------

    def connus(self, ids: list[str]) -> set[str]:
        """Parmi ces identifiants, ceux déjà traités (ou volontairement ignorés)."""
        if not ids:
            return set()
        marques = ",".join("?" * len(ids))
        lignes = self.db.execute(f"SELECT id FROM mails WHERE id IN ({marques})", ids)
        return {l[0] for l in lignes}

    def noter(self, mail_id: str, statut: str, mail=None, classement=None) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO mails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mail_id,
                    statut,
                    datetime.now().isoformat(timespec="seconds"),
                    mail.date.isoformat(timespec="seconds") if mail else None,
                    classement.bac if classement else None,
                    classement.source if classement else None,
                    int(classement.vaut_mon_temps) if classement else None,
                    classement.raison if classement else None,
                    mail.expediteur_adresse if mail else None,
                    mail.objet if mail else None,
                ),
            )
            self.db.execute("DELETE FROM echecs WHERE id = ?", (mail_id,))

    def noter_echec(self, mail_id: str) -> int:
        """Compte une réponse ratée de Claude pour ce mail. Renvoie le nombre d'échecs."""
        with self.db:
            self.db.execute(
                "INSERT INTO echecs VALUES (?, 1) ON CONFLICT(id) DO UPDATE SET tentatives = tentatives + 1",
                (mail_id,),
            )
        return self.db.execute("SELECT tentatives FROM echecs WHERE id = ?", (mail_id,)).fetchone()[0]

    def fermer(self) -> None:
        self.db.close()
