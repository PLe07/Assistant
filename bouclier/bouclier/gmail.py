"""La connexion à Gmail (lecture seule), partagée par l'inventaire (n°18) et la surveillance (n°20).

L'adresse est dans config.toml ([gmail] adresse), le mot de passe d'application dans **ton** élément de trousseau
`bouclier-gmail` (D-08) : jamais dans un fichier, jamais celui d'un autre projet.
"""

from __future__ import annotations

from typing import Any

from bouclier.comptes.imap_lecture_seule import ErreurImap, Fabrique, LecteurImap, _fabrique_reelle
from bouclier.systeme import Systeme

ELEMENT_TROUSSEAU = "bouclier-gmail"


class GmailNonRelie(ErreurImap):
    pass


def etat(reglages: dict[str, Any], systeme: Systeme) -> tuple[bool, str]:
    g = reglages["gmail"]
    if not g.get("active", True):
        return False, "surveillance Gmail coupée dans config.toml"
    if not g.get("adresse"):
        return False, "Gmail pas encore relié : mets ton adresse dans config.toml (voir ACTIONS_HUMAINES.md)"
    if not systeme.trousseau_lire(ELEMENT_TROUSSEAU, g["adresse"]):
        return False, "mot de passe d'application Gmail absent : bouclier gmail-relier (voir ACTIONS_HUMAINES.md)"
    return True, f"Gmail relié en lecture seule ({g['adresse']})"


def ouvrir(reglages: dict[str, Any], systeme: Systeme, fabrique: Fabrique = _fabrique_reelle) -> LecteurImap:
    ok, message = etat(reglages, systeme)
    if not ok:
        raise GmailNonRelie(message)
    adresse = reglages["gmail"]["adresse"]
    lecteur = LecteurImap(fabrique)
    lecteur.connecter(adresse, systeme.trousseau_lire(ELEMENT_TROUSSEAU, adresse) or "")
    return lecteur
