"""C5 — L'historique des navigateurs (Chrome, Brave, Arc, Edge, Safari) : seulement le domaine et le début du chemin,
jamais les paramètres d'adresse.

La base de chaque navigateur est verrouillée pendant qu'il tourne : on la copie dans un fichier temporaire, on lit
les visites depuis le dernier curseur, puis on efface la copie. Safari exige l'« Accès complet au disque » : sans
elle, ce navigateur passe en mode dégradé. Au premier passage, on part d'aujourd'hui (le passé n'est pas lu).
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from modules.corvees.capteurs.base import Capteur
from modules.corvees.normalize import tok_url
from modules.corvees.privacy import domaine_de

SUPPORT = "~/Library/Application Support"
CHROMIUMS = {
    "chrome": f"{SUPPORT}/Google/Chrome",
    "brave": f"{SUPPORT}/BraveSoftware/Brave-Browser",
    "arc": f"{SUPPORT}/Arc/User Data",
    "edge": f"{SUPPORT}/Microsoft Edge",
}
SAFARI = "~/Library/Safari/History.db"
EPOQUE_CHROME = 11644473600  # 1601 → 1970, en secondes
EPOQUE_SAFARI = 978307200  # 2001 → 1970
SOUS_CADRES_ET_RECHARGEMENTS = (3, 4, 8)  # transitions Chrome qui ne sont pas une visite voulue
PAR_PASSAGE = 10000

REQUETES = {
    "chromium": "SELECT v.id, v.visit_time, u.url, v.transition FROM visits v JOIN urls u ON u.id = v.url "
    "WHERE v.id > ? ORDER BY v.id LIMIT ?",
    "safari": "SELECT v.id, v.visit_time, i.url, 0 FROM history_visits v JOIN history_items i ON i.id = v.history_item "
    "WHERE v.id > ? ORDER BY v.id LIMIT ?",
}
MAXIMUM = {
    "chromium": "SELECT COALESCE(MAX(id), 0) FROM visits",
    "safari": "SELECT COALESCE(MAX(id), 0) FROM history_visits",
}


def bases(navigateurs: list[str]) -> list[tuple[str, str, Path]]:
    """[(navigateur, sorte de base, chemin)] pour chaque profil trouvé sur ce Mac."""
    trouvees = []
    for nom in navigateurs:
        if nom == "safari":
            chemin = Path(SAFARI).expanduser()
            if chemin.exists():
                trouvees.append(("safari", "safari", chemin))
        elif nom in CHROMIUMS:
            racine = Path(CHROMIUMS[nom]).expanduser()
            for profil in sorted([racine / "Default", *racine.glob("Profile *")]):
                if (profil / "History").exists():
                    trouvees.append((nom, "chromium", profil / "History"))
    return trouvees


def instant(sorte: str, brut: float) -> float:
    return brut / 1e6 - EPOQUE_CHROME if sorte == "chromium" else brut + EPOQUE_SAFARI


class Navigateur(Capteur):
    nom = "navigateur"
    intervalle = 300.0

    def __init__(self, *args, chemins: list[tuple[str, str, Path]] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.chemins = chemins
        self.derniers: dict[str, tuple[str, float]] = {}

    def demarrer(self) -> None:
        if self.chemins is None:
            self.chemins = bases(self.reglages["navigateurs"])
        if not self.chemins:
            self.desactiver("aucun historique de navigateur trouvé")

    def relever(self, maintenant: float) -> None:
        problemes = []
        for navigateur, sorte, chemin in self.chemins or []:
            try:
                self._lire(navigateur, sorte, chemin, maintenant)
            except PermissionError:
                problemes.append(f"{navigateur} : « Accès complet au disque » requis")
            except (OSError, sqlite3.Error) as e:
                problemes.append(f"{navigateur} : base illisible pour l'instant ({e.__class__.__name__})")
        if problemes:
            self.degrader(" ; ".join(problemes))
        elif self.chemins:
            self.statut, self.detail = "ok", ""

    def _lire(self, navigateur: str, sorte: str, chemin: Path, maintenant: float) -> None:
        cle = "curseur.navigateur." + hashlib.sha1(str(chemin).encode()).hexdigest()[:12]
        with tempfile.TemporaryDirectory(prefix="corvees-") as tmp:
            copie = Path(tmp) / chemin.name
            shutil.copy2(chemin, copie)  # la base est verrouillée par le navigateur : on lit une copie
            for suffixe in ("-wal", "-shm"):
                if Path(str(chemin) + suffixe).exists():
                    shutil.copy2(Path(str(chemin) + suffixe), Path(str(copie) + suffixe))
            db = sqlite3.connect(copie)
            try:
                curseur = self.memoire.lire(cle)
                if curseur is None:  # premier passage : à partir de maintenant
                    self.memoire.ecrire(cle, int(db.execute(MAXIMUM[sorte]).fetchone()[0]))
                    return
                lignes = db.execute(REQUETES[sorte], (int(curseur), PAR_PASSAGE)).fetchall()
            finally:
                db.close()
        for id_, brut, adresse, transition in lignes:
            curseur = max(int(curseur), int(id_))
            if not str(adresse).startswith(("http://", "https://")):
                continue
            if sorte == "chromium" and (int(transition) & 0xFF) in SOUS_CADRES_ET_RECHARGEMENTS:
                continue
            ts, token = instant(sorte, float(brut)), tok_url(str(adresse))
            precedent = self.derniers.get(navigateur)
            if precedent and precedent[0] == token and ts - precedent[1] < 60:
                continue  # la même page, aussitôt : une seule visite
            self.derniers[navigateur] = (token, ts)
            self.emettre(ts, "url", token, domaine=domaine_de(str(adresse)), navigateur=navigateur)
        self.memoire.ecrire(cle, int(curseur))

    def sante(self) -> dict[str, Any]:
        s = super().sante()
        s["navigateurs"] = sorted({n for n, _, _ in self.chemins or []})
        return s
