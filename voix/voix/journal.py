"""Le journal des commandes : les 100 dernières (texte compris, intention, résultat), en local, désactivable, effacé
par `voix oublier`. Jamais d'audio ; les adresses e-mail et les longues suites de chiffres sont masquées.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CHIFFRES = re.compile(r"(?:\d[ .\-]?){6,}\d")


def caviarder(texte: str) -> str:
    """Masque ce qui pourrait être personnel (e-mails, numéros de téléphone ou de carte)."""
    return CHIFFRES.sub("[nombre]", EMAIL.sub("[e-mail]", texte))


class Journal:
    def __init__(self, fichier: Path, actif: bool = True, taille: int = 100) -> None:
        self.fichier = fichier
        self.actif = actif and taille > 0
        self.taille = taille

    def lire(self) -> list[dict[str, Any]]:
        try:
            lignes = self.fichier.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        entrees = []
        for ligne in lignes:
            try:
                e = json.loads(ligne)
            except ValueError:
                continue
            if isinstance(e, dict):
                entrees.append(e)
        return entrees[-self.taille :]

    def ajouter(self, texte: str, intention: str | None, statut: str, resultat: str, quand: datetime) -> None:
        if not self.actif:
            return
        entrees = self.lire()
        entrees.append({
            "quand": quand.isoformat(timespec="seconds"),
            "texte": caviarder(texte)[:300],
            "intention": intention,
            "statut": statut,
            "resultat": caviarder(resultat)[:300],
        })  # fmt: skip
        self._ecrire(entrees[-self.taille :])

    def _ecrire(self, entrees: list[dict[str, Any]]) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.fichier.parent, prefix=".journal.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for e in entrees:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.fichier)

    def oublier(self) -> bool:
        try:
            self.fichier.unlink()
        except FileNotFoundError:
            return False
        return True
