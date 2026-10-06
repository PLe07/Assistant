"""Lancer l'inventaire : Gmail (en-têtes, lecture seule) puis navigateurs, fusion en base, tableau de bord."""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any

from bouclier.arnaque.entetes import WEBMAILS
from bouclier.arnaque.ia import Budget, Client
from bouclier.comptes import ia_categories, inventaire, navigateurs
from bouclier.comptes.imap_lecture_seule import ErreurImap, Fabrique, _fabrique_reelle
from bouclier.config import Chemins
from bouclier.db import Base
from bouclier.journal import log
from bouclier.systeme import Systeme


@dataclass
class ResultatInventaire:
    gmail: str
    navigateurs: list[str] = field(default_factory=list)
    comptes: int = 0
    abonnements: int = 0
    nouveaux: list[str] = field(default_factory=list)


def lancer(
    chemins: Chemins,
    reglages: dict[str, Any],
    base: Base,
    systeme: Systeme,
    fabrique: Fabrique = _fabrique_reelle,
    client: Client | None = None,
    avec_gmail: bool = True,
    avec_navigateurs: bool = True,
) -> ResultatInventaire:
    from bouclier import gmail

    adresse = str(reglages["gmail"].get("adresse") or "")
    domaine_perso = adresse.rsplit("@", 1)[-1].lower() if "@" in adresse else ""
    inv = inventaire.Inventaire(exclus=[domaine_perso] if domaine_perso and domaine_perso not in WEBMAILS else [])
    deja = {str(r["service"]) for r in base.lignes("SELECT service FROM comptes WHERE nature = 'compte'")}
    etat_gmail = "Gmail non consulté"
    if avec_gmail:
        try:
            with gmail.ouvrir(reglages, systeme, fabrique) as lecteur:
                r = inventaire.releve_gmail(lecteur, base, inv)
            etat_gmail = f"Gmail : {r.lus} nouveaux en-têtes lus (lecture seule)"
        except ErreurImap as e:
            etat_gmail = f"Gmail : {e}"
    releve = navigateurs.relever(chemins.maison) if avec_navigateurs else navigateurs.Releve([], [], [])
    for ident in releve.identifiants:
        inv.ajouter_identifiant(ident)
    if reglages["comptes"].get("ia_domaines_inconnus") and client is not None:
        inconnus = [c.service.id for c in inv.comptes.values() if not c.service.connu]
        for domaine, categorie in ia_categories.categoriser(inconnus, client, Budget(base, reglages)).items():
            inv.comptes[domaine].service = dataclasses.replace(inv.comptes[domaine].service, categorie=categorie)
    inventaire.enregistrer(base, inv)
    base.ecrire_meta("inventaire_le", str(time.time()))
    totaux = inventaire.compter(base)
    nouveaux = sorted(i for i, c in inv.comptes.items() if c.nature == "compte" and i not in deja)
    resultat = ResultatInventaire(etat_gmail, releve.navigateurs, totaux.get("compte", 0), totaux.get("abonnement", 0),
                                  nouveaux)  # fmt: skip
    log().info("inventaire : %d comptes, %d abonnements (%s ; navigateurs : %s)", resultat.comptes,
               resultat.abonnements, etat_gmail, ", ".join(releve.navigateurs) or "aucun")  # fmt: skip
    return resultat
