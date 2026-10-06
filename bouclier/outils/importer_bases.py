"""Construit `bouclier/comptes/services.json` à partir de deux bases ouvertes (licence MIT, voir CREDITS.md) :

- JustDeleteMe (https://github.com/jdm-contrib/jdm, `_data/sites.json`) : lien vers la page de suppression du
  compte, difficulté, explication en français quand elle existe ;
- 2factorauth (https://github.com/2factorauth/twofactorauth, `entries/*/*.json`) : double authentification
  disponible ou non, catégorie, pays.

plus `services_fr.py` (services courants en France, choisis à la main : nom, catégorie, domaines).

    python outils/importer_bases.py <dossier jdm> <dossier 2factorauth>

Ne s'exécute pas sur ton Mac : `services.json` est construit une fois, relu, puis versionné.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from services_fr import SERVICES_FR  # noqa: E402

SORTIE = Path(__file__).resolve().parents[1] / "bouclier" / "comptes" / "services.json"
DIFFICULTE = {"easy": "facile", "medium": "moyenne", "hard": "difficile", "impossible": "impossible",
              "limited": "limitée"}  # fmt: skip
CATEGORIES_2FA = {
    "banking": "banque", "payments": "paiement", "investing": "placements", "cryptocurrencies": "placements",
    "finance": "banque", "insurance": "assurance", "retail": "achats", "food": "repas", "social": "réseaux sociaux",
    "communication": "messagerie", "email": "messagerie", "entertainment": "loisirs", "gaming": "jeux",
    "betting": "jeux", "health": "santé", "government": "administration", "identity": "administration",
    "travel": "voyages et transport", "transport": "voyages et transport", "tickets": "loisirs",
    "utilities": "télécoms et énergie", "education": "éducation", "universities": "éducation",
    "postal": "livraison", "crowdfunding": "paiement", "legal": "administration",
}  # fmt: skip
ADMINISTRATIONS = {"impots", "caf", "francetravail", "ants", "franceconnect", "servicepublic", "cpf", "urssaf",
                   "inforetraite", "msa", "antai", "critair", "ameli", "monespacesante"}  # fmt: skip


def _id(nom: str) -> str:
    t = unicodedata.normalize("NFKD", nom.lower())
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in t if not unicodedata.combining(c))) or "service"


def _commit(dossier: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(dossier), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


def charger_jdm(dossier: Path) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((dossier / "_data" / "sites.json").read_text(encoding="utf-8"))
    return data


def charger_2fa(dossier: Path) -> dict[str, dict[str, Any]]:
    """Domaine (principal et additionnels) → entrée."""
    index: dict[str, dict[str, Any]] = {}
    for f in sorted((dossier / "entries").glob("*/*.json")):
        for nom, v in json.loads(f.read_text(encoding="utf-8")).items():
            v = {**v, "nom": nom}
            for d in [v["domain"], *v.get("additional-domains", [])]:
                index.setdefault(d.lower(), v)
    return index


def _double_auth(e: dict[str, Any] | None) -> dict[str, Any]:
    if e is None:
        return {"double_auth": None}
    return {"double_auth": sorted(e.get("tfa", [])), "doc_double_auth": e.get("documentation") or None}


def _suppression(s: dict[str, Any] | None) -> dict[str, Any]:
    if s is None:
        return {"suppression": None, "difficulte": None, "aide": None}
    url = s.get("url_fr") or s.get("url") or None
    if url and not str(url).startswith("https://"):
        url = None  # seulement des liens sécurisés ; sinon « cherche dans les réglages »
    return {"suppression": url, "difficulte": DIFFICULTE.get(str(s.get("difficulty")), None),
            "aide": s.get("notes_fr") or None}  # fmt: skip


def construire(jdm: list[dict[str, Any]], tfa: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    par_domaine_jdm: dict[str, dict[str, Any]] = {}
    for s in jdm:
        for d in s.get("domains") or []:
            par_domaine_jdm.setdefault(d.lower(), s)
    services: list[dict[str, Any]] = []
    jdm_pris: set[int] = set()
    domaines_pris: set[str] = set()
    for ident, nom, categorie, domaines in SERVICES_FR:
        s_jdm = next((par_domaine_jdm[d] for d in domaines if d in par_domaine_jdm), None)
        if s_jdm is None:  # « connect.garmin.com » dans la base, « garmin.com » ici
            s_jdm = next((s for d, s in par_domaine_jdm.items() if any(d.endswith("." + x) for x in domaines)), None)
        s_tfa = next((tfa[d] for d in domaines if d in tfa), None)
        if s_jdm is not None:
            jdm_pris.add(id(s_jdm))
        entree = {"id": ident, "nom": nom, "categorie": categorie, "domaines": list(domaines), "fr": True,
                  **_suppression(s_jdm), **_double_auth(s_tfa)}  # fmt: skip
        if ident in ADMINISTRATIONS:
            entree.update({"suppression": None, "difficulte": "impossible",
                           "aide": "Compte d'un service public : il ne se supprime pas. Protège-le par un mot de passe"
                                   " unique."})  # fmt: skip
        services.append(entree)
        domaines_pris.update(domaines)
    ids = {s["id"] for s in services}
    for s in jdm:
        if id(s) in jdm_pris:
            continue
        domaines = [d.lower() for d in s.get("domains") or [] if d.lower() not in domaines_pris]
        if not domaines:
            continue
        s_tfa = next((tfa[d] for d in domaines if d in tfa), None)
        categorie = next((CATEGORIES_2FA[c] for c in (s_tfa or {}).get("categories", []) if c in CATEGORIES_2FA),
                         "autre")  # fmt: skip
        ident = _id(s["name"])
        while ident in ids:
            ident += "_"
        ids.add(ident)
        services.append({"id": ident, "nom": s["name"], "categorie": categorie, "domaines": domaines, "fr": False,
                         **_suppression(s), **_double_auth(s_tfa)})  # fmt: skip
        domaines_pris.update(domaines)
    # Services français de 2factorauth absents des deux listes : catégorie et double authentification seulement.
    vus: set[int] = set()
    for d, e in sorted(tfa.items()):
        if id(e) in vus or "fr" not in e.get("regions", []) or d in domaines_pris:
            continue
        vus.add(id(e))
        domaines = [
            x.lower() for x in [e["domain"], *e.get("additional-domains", [])] if x.lower() not in domaines_pris
        ]
        ident = _id(e["nom"])
        while ident in ids:
            ident += "_"
        ids.add(ident)
        categorie = next((CATEGORIES_2FA[c] for c in e.get("categories", []) if c in CATEGORIES_2FA), "autre")
        services.append({"id": ident, "nom": e["nom"], "categorie": categorie, "domaines": domaines, "fr": True,
                         **_suppression(None), **_double_auth(e)})  # fmt: skip
        domaines_pris.update(domaines)
    return services


def main(dossier_jdm: Path, dossier_tfa: Path) -> None:
    services = construire(charger_jdm(dossier_jdm), charger_2fa(dossier_tfa))
    sortie = {
        "_sources": {
            "justdeleteme": {
                "depot": "https://github.com/jdm-contrib/jdm",
                "commit": _commit(dossier_jdm),
                "licence": "MIT",
            },
            "2factorauth": {
                "depot": "https://github.com/2factorauth/twofactorauth",
                "commit": _commit(dossier_tfa),
                "licence": "MIT",
            },
        },  # fmt: skip
        "services": services,
    }
    lignes = ['{"_sources": ' + json.dumps(sortie["_sources"], ensure_ascii=False) + ",", ' "services": [']
    lignes += [("  " + json.dumps(s, ensure_ascii=False) + ",") for s in services]
    lignes[-1] = lignes[-1].rstrip(",")
    lignes.append(" ]}")
    SORTIE.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    fr = sum(1 for s in services if s["fr"])
    avec_lien = sum(1 for s in services if s["suppression"])
    print(f"{len(services)} services ({fr} courants en France, {avec_lien} avec un lien de suppression) → {SORTIE}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
