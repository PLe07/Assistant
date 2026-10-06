"""Une vérification complète : analyse locale → avis de l'IA si besoin → veto → réponse → historique."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bouclier.arnaque import historique
from bouclier.arnaque.detecteur import Contexte, analyser
from bouclier.arnaque.extraction import LecteurImage, Message
from bouclier.arnaque.flux import Flux
from bouclier.arnaque.ia import Budget, Client, ResultatIA, choisir_client, demander_avis, faut_il_demander
from bouclier.arnaque.rdap import ClientRdap
from bouclier.arnaque.reponse import Reponse, construire
from bouclier.arnaque.veto import Verdict, combiner
from bouclier.config import Chemins
from bouclier.db import Base
from bouclier.journal import log
from bouclier.systeme import Systeme


def comptes_connus(base: Base) -> set[str]:
    """Les services où l'inventaire (n°18) a trouvé un compte (et que tu n'as pas marqués « supprimé »)."""
    lignes = base.lignes("SELECT service FROM comptes WHERE nature = 'compte' AND statut != 'supprime'")
    return {str(ligne["service"]) for ligne in lignes}


@dataclass
class Outils:
    reglages: dict[str, Any]
    base: Base
    contexte: Contexte = field(default_factory=Contexte)
    client: Client | None = None
    lire_image: LecteurImage | None = None
    dormir: Callable[[float], None] = time.sleep


def outils_reels(chemins: Chemins, reglages: dict[str, Any], base: Base, systeme: Systeme) -> Outils:
    from bouclier.arnaque import ocr

    contexte = Contexte(rdap=ClientRdap(base), flux=Flux(chemins.caches), comptes=lambda: comptes_connus(base))
    client = choisir_client(reglages, lambda service: systeme.trousseau_lire(service))
    return Outils(reglages, base, contexte, client, ocr.lecteur(systeme.mac))


@dataclass
class Resultat:
    verdict: Verdict
    reponse: Reponse
    id_historique: int


def verifier(message: Message, o: Outils, source: str, demande_ia: bool = False) -> Resultat:
    locale = analyser(message, o.contexte)
    avis: ResultatIA | None = None
    if faut_il_demander(locale, o.reglages, demande_ia):
        avis = demander_avis(locale, o.reglages, o.client, Budget(o.base, o.reglages), o.dormir)
    verdict = combiner(locale, avis)
    reponse = construire(verdict)
    ident = historique.noter(o.base, verdict, reponse, source, o.reglages)
    etat_ia = avis.etat if avis is not None else "non demandée"
    log().info("vérification n°%d (%s) : %s, score %d, IA %s. %s", ident, source, verdict.niveau.code, verdict.score,
               etat_ia, " / ".join(reponse.raisons))  # fmt: skip
    return Resultat(verdict, reponse, ident)
