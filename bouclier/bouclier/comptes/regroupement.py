"""Du nom de domaine au service : « accounts.google.com » → Google, « mail.instagram.com » → Instagram.

La base embarquée (`services.json`, construite par `outils/importer_bases.py`) donne pour chaque service ses
domaines, sa catégorie, le lien direct vers sa page de suppression (JustDeleteMe), la difficulté et la double
authentification disponible (2factorauth). Un domaine inconnu devient un service à son nom (catégorie « autre »).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from bouclier.arnaque.liens import domaine_enregistrable

CHEMIN = Path(__file__).with_name("services.json")


@dataclass(frozen=True)
class Service:
    id: str
    nom: str
    categorie: str
    domaines: tuple[str, ...]
    fr: bool = False
    suppression: str | None = None
    difficulte: str | None = None
    aide: str | None = None
    double_auth: tuple[str, ...] | None = None  # None : inconnu ; () : pas de double authentification
    doc_double_auth: str | None = None
    connu: bool = True


@dataclass(frozen=True)
class Base:
    services: dict[str, Service]
    par_domaine: dict[str, str]
    sources: dict[str, dict[str, str]]


@lru_cache(maxsize=1)
def charger(chemin: Path = CHEMIN) -> Base:
    brut = json.loads(chemin.read_text(encoding="utf-8"))
    services: dict[str, Service] = {}
    par_domaine: dict[str, str] = {}
    for s in brut["services"]:
        da = s.get("double_auth")
        service = Service(
            s["id"], s["nom"], s["categorie"], tuple(s["domaines"]), bool(s.get("fr")), s.get("suppression"),
            s.get("difficulte"), s.get("aide"), tuple(da) if da is not None else None, s.get("doc_double_auth"),
        )  # fmt: skip
        services[service.id] = service
        for d in service.domaines:
            par_domaine.setdefault(d.lower(), service.id)
    return Base(services, par_domaine, brut.get("_sources", {}))


def trouver(hote: str, base: Base | None = None) -> Service | None:
    """Le service connu pour un hôte : le plus précis d'abord (« mail.google.com », puis « google.com »)."""
    base = base or charger()
    labels = hote.lower().strip(".").split(".")
    for i in range(len(labels) - 1):
        ident = base.par_domaine.get(".".join(labels[i:]))
        if ident:
            return base.services[ident]
    return None


def identifier(hote: str, base: Base | None = None) -> Service:
    """Le service connu, ou un service « inconnu » nommé d'après son domaine."""
    connu = trouver(hote, base)
    if connu is not None:
        return connu
    domaine = domaine_enregistrable(hote.lower().strip("."))
    return Service(domaine, domaine, "autre", (domaine,), connu=False)


def service(ident: str, base: Base | None = None) -> Service | None:
    return (base or charger()).services.get(ident)
