"""Option (désactivée par défaut) : la catégorie d'un service inconnu, demandée à Claude à partir de son **seul nom
de domaine**. Rien d'autre ne part : ni sujet, ni date, ni adresse."""

from __future__ import annotations

import json
import re

from bouclier.arnaque.ia import Budget, Client, ErreurDefinitive, ErreurPassagere

CATEGORIES = ("réseaux sociaux", "messagerie", "achats", "annonces", "repas", "livraison", "banque", "paiement",
              "placements", "assurance", "santé", "administration", "télécoms et énergie", "loisirs", "jeux",
              "voyages et transport", "emploi", "rencontres", "presse", "éducation", "outils", "autre")  # fmt: skip
SYSTEME = (
    "Tu ranges des noms de domaine de services en ligne dans des catégories. Réponds uniquement par un objet JSON "
    '{"domaine": "catégorie"} ; catégories permises : ' + ", ".join(CATEGORIES) + ". Si tu ne sais pas : autre."
)
_DOMAINE = re.compile(r"^[a-z0-9.\-]{3,253}$")


def categoriser(domaines: list[str], client: Client | None, budget: Budget) -> dict[str, str]:
    propres = sorted({d for d in domaines if _DOMAINE.match(d)})[:100]
    if not propres or client is None:
        return {}
    demande = "\n".join(propres)
    if not budget.permet(budget.estimation(SYSTEME, demande, 800)):
        return {}
    try:
        brute = client.envoyer(SYSTEME, demande, 800, 30)
    except (ErreurPassagere, ErreurDefinitive):
        return {}
    budget.noter(brute, usage="comptes")
    debut, fin = brute.texte.find("{"), brute.texte.rfind("}")
    try:
        data = json.loads(brute.texte[debut : fin + 1]) if debut != -1 else {}
    except json.JSONDecodeError:
        return {}
    return {d: c for d, c in data.items() if d in propres and c in CATEGORIES} if isinstance(data, dict) else {}
