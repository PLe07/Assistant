"""Un faux module du faux écosystème (§9.1) : un vrai petit démon, sans dépendance.

    python faux_module.py <dossier du module>

Il relit à chaque seconde `<dossier>/comportement` : sain, boucle, file, erreurs, budget, attente, cpu. Il écrit son
journal (`logs/module.log`) et sa base SQLite en mode WAL (`donnees/module.db` : battement, preuves des attentes,
dépenses). La base est ouverte avec un délai d'attente nul : si quelqu'un la verrouillait, même un instant, l'erreur
« database is locked » serait notée dans `logs/verrous.txt` (le test exige que ce fichier n'existe pas).
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

CPU_MAX_S = 12 * 60  # la boucle de calcul s'arrête d'elle-même au plus tard après 12 min


def journal(dossier: Path, niveau: str, message: str) -> None:
    maintenant = time.time()
    date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(maintenant))
    with open(dossier / "logs" / "module.log", "a", encoding="utf-8") as f:
        f.write(f"{date},{int(maintenant % 1 * 1000):03d} {niveau} [module] {message}\n")


def ecrire(dossier: Path, db: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> None:
    try:
        db.execute(sql, params)
    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            with open(dossier / "logs" / "verrous.txt", "a", encoding="utf-8") as f:
                f.write(f"{time.time()} {e}\n")
        else:
            raise


def comportement(dossier: Path) -> str:
    try:
        return (dossier / "comportement").read_text(encoding="utf-8").strip()
    except OSError:
        return "sain"


def main() -> int:
    dossier = Path(sys.argv[1])
    (dossier / "logs").mkdir(exist_ok=True)
    (dossier / "donnees").mkdir(exist_ok=True)
    (dossier / "entree").mkdir(exist_ok=True)
    if comportement(dossier) == "boucle":
        journal(dossier, "ERROR", "plantage au démarrage : configuration introuvable")
        time.sleep(0.3)
        return 1
    db = sqlite3.connect(dossier / "donnees" / "module.db", timeout=0, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS depenses_ia (date REAL, mois TEXT, cout_usd REAL)")
    journal(dossier, "INFO", "démarré")
    debut = time.monotonic()
    dernier_journal = 0.0
    while True:
        c = comportement(dossier)
        maintenant = time.time()
        if c == "boucle":
            journal(dossier, "ERROR", "plantage : configuration introuvable")
            return 1
        ecrire(dossier, db, "INSERT OR REPLACE INTO meta VALUES ('battement', ?)", (str(maintenant),))
        ecrire(dossier, db, "INSERT OR REPLACE INTO meta VALUES ('preuve:travail', ?)", (str(maintenant),))
        if c != "attente":
            ecrire(dossier, db, "INSERT OR REPLACE INTO meta VALUES ('preuve:brief', ?)", (str(maintenant),))
        if maintenant - dernier_journal >= 10:
            journal(dossier, "INFO", "travail fait")
            dernier_journal = maintenant
        entree = dossier / "entree"
        if c == "file":
            for i in range(3):
                document = entree / f"document-{i}.pdf"
                if not document.exists():
                    document.write_bytes(b"%PDF-1.4 faux document\n")
        else:
            for document in entree.glob("document-*.pdf"):
                document.unlink()
        if c == "erreurs" and not (dossier / "logs" / ".erreurs_faites").exists():
            for i in range(30):
                journal(dossier, "ERROR", f"échec de traitement n°{i} : délai dépassé")
            (dossier / "logs" / ".erreurs_faites").write_text("1")
        cible = dossier / "budget_cible"
        if cible.exists():
            voulu = float(cible.read_text(encoding="utf-8"))
            mois = time.strftime("%Y-%m", time.localtime(maintenant))
            r = db.execute("SELECT COALESCE(SUM(cout_usd), 0) FROM depenses_ia WHERE mois = ?", (mois,)).fetchone()
            if float(r[0]) < voulu - 1e-9:
                ecrire(dossier, db, "INSERT INTO depenses_ia VALUES (?, ?, ?)", (maintenant, mois, voulu - float(r[0])))
        if c == "cpu" and time.monotonic() - debut < CPU_MAX_S:
            fin = time.monotonic() + 0.9  # 90 % d'un cœur, en priorité basse
            while time.monotonic() < fin:
                sum(i * i for i in range(2000))
            time.sleep(0.1)
        else:
            time.sleep(1)


if __name__ == "__main__":
    try:
        os.nice(10)
    except OSError:
        pass
    sys.exit(main())
