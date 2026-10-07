"""Les notifications de Quotidien : jamais entre 23 h et 7 h (réglable), toutes notées en base pour `doctor`.

Une notification qui tomberait dans le silence n'est pas envoyée (elle est notée « silence ») : ce qui compte
revient dans le brief du matin. Rien ici n'envoie de message à quelqu'un : ce sont des notifications du Mac, pour toi.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quotidien.db import Base as BaseDonnees
from quotidien.systeme import Systeme


def en_silence(maintenant: float, reglages: dict[str, Any]) -> bool:
    h = reglages["horaires"]
    heure = datetime.fromtimestamp(maintenant, ZoneInfo(reglages["lieu"]["fuseau"])).strftime("%H:%M")
    debut, fin = h["silence_debut"], h["silence_fin"]
    return heure >= debut or heure < fin if debut > fin else debut <= heure < fin


class Notifieur:
    def __init__(self, db: BaseDonnees, systeme: Systeme, reglages: dict[str, Any],
                 horloge: Callable[[], float] = time.time) -> None:  # fmt: skip
        self.db, self.systeme, self.reglages, self.horloge = db, systeme, reglages, horloge

    def notifier(self, genre: str, titre: str, texte: str) -> bool:
        t = self.horloge()
        if en_silence(t, self.reglages):
            envoyee, motif = False, "silence"
        else:
            envoyee = self.systeme.notifier(titre, texte, "Quotidien")
            motif = "" if envoyee else ("pas un Mac" if not self.systeme.mac else "refusée par macOS")
        with self.db.transaction() as cx:
            cx.execute("INSERT INTO notifications(date, genre, titre, texte, envoyee, motif) VALUES (?, ?, ?, ?, ?, ?)",
                       (t, genre, titre, texte[:1000], int(envoyee), motif))  # fmt: skip
            cx.execute("DELETE FROM notifications WHERE date < ?", (t - 60 * 86400,))
        return envoyee

    def dernieres(self, n: int = 5) -> list[tuple[float, str, str, bool, str]]:
        lignes = self.db.lignes("SELECT date, genre, titre, envoyee, motif FROM notifications ORDER BY date DESC "
                                "LIMIT ?", (n,))  # fmt: skip
        return [(float(r[0]), str(r[1]), str(r[2]), bool(r[3]), str(r[4])) for r in lignes]
