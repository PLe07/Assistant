"""Les files d'attente : combien de fichiers attendent dans une boîte d'entrée, et depuis quand (§4.1).

On **liste** les dossiers (nom et date seulement) : jamais le contenu, jamais de téléchargement iCloud forcé. Un
fichier « fantôme » d'iCloud (`.facture.pdf.icloud`) est compté à part (« pas encore téléchargé »).

L'âge d'un fichier, c'est depuis quand il est **arrivé** : la première fois que le tableau de bord l'a vu (gardé dans
notre base, donc juste à une minute près et après un redémarrage). Sa date de modification ne compte pas : un PDF
vieux d'un an posé à l'instant n'attend que depuis un instant. Seuls les fichiers déjà là la toute première fois
qu'on regarde un dossier prennent leur date de changement d'état (`ctime`) : c'est la meilleure estimation possible.
"""

from __future__ import annotations

import os
from pathlib import Path

from tableau.db import Base
from tableau.module import FileAttente

# Ce que les modules écrivent eux-mêmes dans leur boîte (pages, dossiers de raccourcis) : ce n'est pas en attente.
IGNORES = {"Mon coffre.html", "Derniers classements.html", ".DS_Store", "Icon\r", ".localized"}


def _ignore(nom: str) -> bool:
    return nom in IGNORES or nom.startswith("~$") or nom.endswith(" (Trieur).html") or nom.endswith(".tmp")


def mesurer(dossier: Path, base: Base, maintenant: float, nom: str | None = None) -> FileAttente | None:
    """None si le dossier n'existe pas (module pas installé ou iCloud absent)."""
    try:
        entrees = list(os.scandir(dossier))
    except OSError:
        return None
    presents: list[tuple[str, float]] = []
    fantomes = 0
    for e in entrees:
        if _ignore(e.name):
            continue
        try:
            if not e.is_file(follow_symlinks=False):
                continue
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if e.name.startswith("."):
            if e.name.endswith(".icloud"):
                fantomes += 1
                presents.append((e.path, st.st_ctime))
            continue
        presents.append((e.path, st.st_ctime))
    plus_vieux = 0.0
    cle_dossier = f"file_vue:{dossier}"
    deja_regarde = base.lire_meta(cle_dossier) is not None
    if not deja_regarde:
        base.ecrire_meta(cle_dossier, str(maintenant))
    if presents:
        connus = {
            r["chemin"]: float(r["premier_vu"])
            for r in base.lignes(
                f"SELECT chemin, premier_vu FROM fichiers_vus WHERE chemin IN ({','.join('?' * len(presents))})",
                tuple(p for p, _ in presents),
            )
        }
        base.plusieurs(
            "INSERT INTO fichiers_vus (chemin, premier_vu, dernier_vu) VALUES (?, ?, ?) "
            "ON CONFLICT(chemin) DO UPDATE SET dernier_vu = excluded.dernier_vu",
            [(p, maintenant, maintenant) for p, _ in presents],
        )
        for chemin, ctime in presents:
            if chemin in connus:
                arrivee = connus[chemin]
            else:
                arrivee = min(ctime, maintenant) if not deja_regarde else maintenant
                if not deja_regarde:
                    base.executer("UPDATE fichiers_vus SET premier_vu = ? WHERE chemin = ?", (arrivee, chemin))
            plus_vieux = max(plus_vieux, maintenant - arrivee)
    # Un fichier parti puis revenu repart de zéro : on oublie ceux qui ne sont plus là.
    prefixe = f"{dossier}/"
    encore = {p for p, _ in presents}
    partis = [
        (r["chemin"],)
        for r in base.lignes(
            "SELECT chemin FROM fichiers_vus WHERE substr(chemin, 1, length(?)) = ?", (prefixe, prefixe)
        )
        if r["chemin"] not in encore
    ]
    if partis:
        base.plusieurs("DELETE FROM fichiers_vus WHERE chemin = ?", partis)
    return FileAttente(
        nom=nom or dossier.name, n=len(presents), plus_vieux_s=plus_vieux, pas_encore_telecharges=fantomes
    )
