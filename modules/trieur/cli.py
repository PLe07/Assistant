"""La commande « trieur » (python trieur.py <commande>, ou python assistant.py trieur <commande>)."""

from __future__ import annotations

import argparse

AIDE = """🗂 Le Trieur : tes documents reconnus, renommés, rangés ; tes garanties suivies.

  trieur ajouter FICHIER…          donner un ou plusieurs documents
  trieur statut                    l'état du système
  trieur journal                   les derniers traitements
  trieur coffre                    tes garanties
  trieur garantie ajouter|modifier|supprimer
  trieur annuler ID                remettre l'original à sa place
  trieur corriger ID --type X      corriger un classement (une règle est apprise)
  trieur ranger-existant DOSSIER   un plan pour un dossier existant (--confirmer pour l'exécuter)
  trieur doctor                    santé, autorisations, données
"""


def construire() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trieur", description="Le Trieur de documents.", add_help=True)
    p.add_subparsers(dest="commande")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construire().parse_args(argv or [])
    if args.commande is None:
        print(AIDE)
        return 0
    return 0
