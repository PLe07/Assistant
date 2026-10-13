"""Le pont vers l'app « Commandes Vocales » : les actions qui demandent une autorisation de macOS.

Quitter, cacher ou montrer une app (NSRunningApplication, sans autorisation), piloter Musique et Spotify et changer
l'apparence (Apple Events : l'autorisation « Automatisation » est demandée **au nom de l'app**, pas d'un Python
anonyme), verrouiller l'écran, afficher une notification. Le moteur envoie un **ordre fermé** (un nom de la liste
ci-dessous et des paramètres validés) ; l'app ne connaît que ces ordres et ne reçoit jamais de script.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

BUNDLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]{0,200}")
LECTEURS = ("musique", "spotify")
# Ordre → paramètres permis (nom → validateur).
ORDRES: dict[str, dict[str, str]] = {
    "app.quitter": {"bundle": "bundle"},
    "app.cacher": {"bundle": "bundle"},
    "app.cacher_autres": {"sauf": "bundle?"},
    "app.quitter_tout": {"sauf": "bundle?"},
    "app.ouvertes": {},
    "musique.lecture": {"lecteur": "lecteur?"},
    "musique.pause": {"lecteur": "lecteur?"},
    "musique.suivant": {"lecteur": "lecteur?"},
    "musique.precedent": {"lecteur": "lecteur?"},
    "musique.titre": {"lecteur": "lecteur?"},
    "musique.playlist": {"lecteur": "lecteur", "playlist": "texte"},
    "apparence.lire": {},
    "apparence.regler": {"sombre": "bool"},
    "ecran.verrouiller": {},
    "notification": {"titre": "texte", "message": "texte"},
    "ecoute.pause": {},
}


class OrdreRefuse(Exception):
    """Un ordre hors liste ou un paramètre invalide : rien n'est envoyé."""


def valider(ordre: str, params: dict[str, Any]) -> dict[str, Any]:
    if ordre not in ORDRES:
        raise OrdreRefuse(f"ordre hors liste : {ordre!r}")
    permis = ORDRES[ordre]
    for cle in params:
        if cle not in permis:
            raise OrdreRefuse(f"paramètre inconnu pour {ordre} : {cle!r}")
    propres: dict[str, Any] = {}
    for cle, sorte in permis.items():
        facultatif = sorte.endswith("?")
        sorte = sorte.rstrip("?")
        if cle not in params or params[cle] is None:
            if not facultatif:
                raise OrdreRefuse(f"paramètre manquant pour {ordre} : {cle}")
            continue
        v = params[cle]
        if sorte == "bundle" and not (isinstance(v, str) and BUNDLE.fullmatch(v)):
            raise OrdreRefuse(f"identifiant d'app invalide : {v!r}")
        if sorte == "lecteur" and v not in LECTEURS:
            raise OrdreRefuse(f"lecteur inconnu : {v!r}")
        if sorte == "bool" and not isinstance(v, bool):
            raise OrdreRefuse(f"{cle} doit être vrai ou faux")
        if sorte == "texte" and not (isinstance(v, str) and 0 < len(v) <= 300 and "\x00" not in v):
            raise OrdreRefuse(f"{cle} : texte invalide")
        propres[cle] = v
    return propres


@dataclass(frozen=True)
class ReponsePont:
    ok: bool
    donnees: dict[str, Any]
    erreur: str = ""


class Pont(Protocol):
    def demander(self, ordre: str, params: dict[str, Any]) -> ReponsePont: ...


class PontAbsent:
    """Quand l'app n'est pas connectée : rien ne part, et on le dit."""

    def demander(self, ordre: str, params: dict[str, Any]) -> ReponsePont:
        valider(ordre, params)
        return ReponsePont(False, {}, "l'app Commandes Vocales n'est pas lancée")
