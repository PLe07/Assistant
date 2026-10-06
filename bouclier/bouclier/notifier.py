"""Les notifications : au plus 3 par jour, jamais entre 23 h et 8 h.

Exceptions : une réponse à une demande de ta part (« Arnaque ? », « Est-ce une arnaque ? ») part toujours, même la
nuit, et ne compte pas dans les 3. Une alerte tombée la nuit attend 8 h (dans la limite du jour).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from bouclier.db import Base
from bouclier.journal import log
from bouclier.systeme import Systeme


class Notifieur:
    def __init__(
        self,
        base: Base,
        systeme: Systeme,
        reglages: dict[str, Any],
        horloge: Callable[[], float] = time.time,
    ) -> None:
        self.base = base
        self.systeme = systeme
        self.reglages = reglages["notifications"]
        self.horloge = horloge

    def _debut_du_jour(self, t: float) -> float:
        lt = time.localtime(t)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))

    def en_silence(self, t: float | None = None) -> bool:
        heure = time.localtime(self.horloge() if t is None else t).tm_hour
        debut, fin = int(self.reglages["silence_debut"]), int(self.reglages["silence_fin"])
        return heure >= debut or heure < fin if debut > fin else debut <= heure < fin

    def envoyees_aujourdhui(self) -> int:
        debut = self._debut_du_jour(self.horloge())
        ligne = self.base.cx.execute(
            "SELECT COUNT(*) FROM notifications WHERE date >= ? AND envoyee = 1 AND genre NOT LIKE 'reponse%'",
            (debut,),
        ).fetchone()
        return int(ligne[0])

    def _noter(self, genre: str, titre: str, envoyee: bool, motif: str = "") -> None:
        with self.base.transaction() as cx:
            cx.execute(
                "INSERT INTO notifications(date, genre, titre, envoyee, motif) VALUES (?, ?, ?, ?, ?)",
                (self.horloge(), genre, titre, int(envoyee), motif),
            )

    def envoyer(self, genre: str, titre: str, texte: str, *, reponse_a_demande: bool = False) -> bool:
        """True si la notification est partie maintenant ; sinon elle est notée (en attente ou au-delà du plafond)."""
        if reponse_a_demande:
            ok = self.systeme.notifier(titre, texte)
            self._noter(f"reponse:{genre}", titre, ok, "" if ok else "notification impossible")
            return ok
        if self.en_silence():
            self._noter(genre, titre, False, "nuit")
            self.base.ecrire_meta(f"attente:{genre}:{titre}", texte)
            log().info("notification « %s » gardée pour 8 h", titre)
            return False
        if self.envoyees_aujourdhui() >= int(self.reglages["max_par_jour"]):
            self._noter(genre, titre, False, "plafond")
            log().info("plafond de notifications atteint : « %s » visible dans le tableau de bord", titre)
            return False
        ok = self.systeme.notifier(titre, texte)
        self._noter(genre, titre, ok, "" if ok else "notification impossible")
        return ok

    def envoyer_en_attente(self) -> int:
        """Au réveil (8 h passées) : les alertes de la nuit partent, dans la limite du jour."""
        if self.en_silence():
            return 0
        envoyees = 0
        for ligne in self.base.lignes("SELECT cle, valeur FROM meta WHERE cle LIKE 'attente:%' ORDER BY cle"):
            _, genre, titre = str(ligne["cle"]).split(":", 2)
            with self.base.transaction() as cx:
                cx.execute("DELETE FROM meta WHERE cle = ?", (ligne["cle"],))
            if self.envoyer(genre, titre, str(ligne["valeur"])):
                envoyees += 1
        return envoyees
