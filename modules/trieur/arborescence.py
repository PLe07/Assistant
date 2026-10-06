"""D-10 · « trieur arborescence » : s'aligner sur tes dossiers de ~/Documents (lus par leur nom seulement).

Si tu as déjà « Documents/Factures » ou « Documents/Impôts », le Trieur propose d'y ranger plutôt que dans
« Classés/Factures ». Rien n'est déplacé : seuls les nouveaux documents iront là, après `--appliquer`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.trieur.classement.texte import normaliser

SYNONYMES = {
    "Factures": ["factures", "facture", "achats"],
    "Banque": ["banque", "banques", "comptes", "releves", "releves bancaires"],
    "Impôts": ["impots", "impot", "fiscal", "fiscalite"],
    "Logement": ["logement", "maison", "appartement", "location"],
    "Santé": ["sante", "medical", "mutuelle"],
    "Assurances": ["assurances", "assurance"],
    "Administratif": ["administratif", "papiers", "admin", "administration"],
    "Identité": ["identite", "papiers d'identite"],
    "Transport & voyages": ["voyages", "voyage", "transport", "vacances"],
    "Devis": ["devis", "travaux"],
    "Micro-entreprise": ["micro-entreprise", "microentreprise", "entreprise", "auto-entrepreneur", "pro"],
    "Garanties": ["garanties", "garantie", "notices"],
}


def proposer(documents: Path, reglages: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """{clé: (modèle actuel, modèle proposé)} pour chaque type dont le 1er dossier existe déjà chez toi."""
    try:
        noms = [d.name for d in documents.iterdir() if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return {}
    par_nom = {normaliser(n): n for n in noms}
    sortie = {}
    for cle, modele in reglages["arborescence"].items():
        if modele.startswith(("~", "/")):
            continue
        premier, _, reste = modele.partition("/")
        for synonyme in SYNONYMES.get(premier, []):
            if synonyme in par_nom:
                nouveau = f"~/Documents/{par_nom[synonyme]}" + (f"/{reste}" if reste else "")
                sortie[cle] = (modele, nouveau)
                break
    return sortie


def appliquer(propositions: dict[str, tuple[str, str]], reglages: dict[str, Any]) -> dict[str, str]:
    from core import config as config_assistant

    arbo = dict(reglages["arborescence"])
    arbo.update({cle: nouveau for cle, (_, nouveau) in propositions.items()})
    config_assistant.regler_module("trieur", "arborescence", arbo)
    return arbo
