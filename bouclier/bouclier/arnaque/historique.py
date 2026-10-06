"""L'historique des vérifications (`bouclier historique`) : texte **caviardé**, 90 jours au plus."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from bouclier.arnaque.reponse import Reponse
from bouclier.arnaque.veto import Verdict
from bouclier.caviardage import caviarder
from bouclier.db import Base

LIMITE_TEXTE = 5000


def purger(base: Base, jours: int, horloge: Callable[[], float] = time.time) -> int:
    with base.transaction() as cx:
        return cx.execute("DELETE FROM analyses WHERE date < ?", (horloge() - jours * 86400,)).rowcount


def noter(
    base: Base,
    verdict: Verdict,
    reponse: Reponse,
    source: str,
    reglages: dict[str, Any],
    horloge: Callable[[], float] = time.time,
) -> int:
    perso = reglages.get("moi", {})
    message = verdict.locale.message
    ia = verdict.ia.etat if verdict.ia is not None else "non"
    cout = verdict.ia.cout_usd if verdict.ia is not None else 0.0
    with base.transaction() as cx:
        curseur = cx.execute(
            "INSERT INTO analyses(date, source, niveau, score, titre, texte_caviarde, raisons, ia, cout_usd)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                horloge(),
                source,
                verdict.niveau.code,
                verdict.score,
                caviarder(reponse.titre, perso),
                caviarder(message.texte_complet[:LIMITE_TEXTE], perso),
                json.dumps([caviarder(r, perso) for r in reponse.raisons], ensure_ascii=False),
                ia,
                cout,
            ),
        )
        ident = int(curseur.lastrowid or 0)
    purger(base, int(reglages.get("historique", {}).get("jours", 90)), horloge)
    return ident


def lister(base: Base, n: int = 20) -> list[sqlite3.Row]:
    return base.lignes("SELECT * FROM analyses ORDER BY date DESC, id DESC LIMIT ?", (n,))


def formater(lignes: list[sqlite3.Row]) -> str:
    if not lignes:
        return 'Aucune vérification pour l\'instant. Essaie : bouclier verifier "le texte du SMS"'
    sortie = []
    for ligne in lignes:
        quand = time.strftime("%d/%m %H:%M", time.localtime(ligne["date"]))
        extrait = " ".join(str(ligne["texte_caviarde"]).split())[:70]
        ia = " · avis de l'IA" if ligne["ia"] == "ok" else ""
        sortie.append(f"{quand}  {ligne['titre']}  ({ligne['source']}{ia})\n          « {extrait} »")
    return "\n".join(sortie)
