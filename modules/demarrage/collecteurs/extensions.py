"""S7 — les extensions système (réseau, sécurité, pilotes) : `systemextensionsctl list`.

On ne peut les retirer que depuis leur app ou les Réglages : le Nettoyeur n'y donne que des instructions.
"""

from __future__ import annotations

import re

from modules.demarrage.modele import Fiche, identifiant
from modules.demarrage.systeme import Systeme

_LIGNE = re.compile(r"^(\*?)\t(\*?)\t(\S+)\t(\S+) \(([^)]*)\)\t(.*?)\t\[(.*)\]\s*$")
_ESPACES = re.compile(r"^(\*?)\s+(\*?)\s+([A-Z0-9]{10}|-)\s+(\S+) \(([^)]*)\)\s+(.*?)\s+\[(.*)\]\s*$")


def analyser(texte: str) -> list[Fiche]:
    fiches: list[Fiche] = []
    categorie = ""
    for ligne in texte.splitlines():
        if ligne.startswith("--- "):
            categorie = ligne[4:].strip().rsplit(".", 1)[-1]
            continue
        m = _LIGNE.match(ligne) or _ESPACES.match(ligne)
        if not m:
            continue
        activee, active, equipe, bundle, version, nom, etat = m.groups()
        fiches.append(
            Fiche(
                id=identifiant("extension", bundle),
                label=bundle,
                source="extension",
                nom=nom.strip() or bundle,
                equipe=None if equipe == "-" else equipe,
                actif=bool(activee) and "enabled" in etat and "terminated" not in etat,
                desactive=not activee,
                charge=bool(active),
                details={"categorie": categorie, "etat": etat, "version": version},
            )
        )
    return fiches


def collecter(systeme: Systeme) -> tuple[list[Fiche], list[str]]:
    if not systeme.a_la_commande("systemextensionsctl"):
        return [], ["systemextensionsctl absent"]
    r = systeme.executer(["systemextensionsctl", "list"], delai=10.0)
    if not r.ok:
        return [], [f"systemextensionsctl : {r.erreur.strip()[:100] or r.code}"]
    return analyser(r.sortie), []
