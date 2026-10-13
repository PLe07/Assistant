"""La commande `voix` (en français, sans jargon).

voix version
voix raccourci [--export FICHIER]   le raccourci retenu, et les raccourcis du système qu'il évite
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from voix import VERSION, config
from voix.raccourcis_systeme import Combinaison, CombinaisonInvalide, choisir, conflit, lire_export


def _export_systeme(fichier: str | None) -> bytes | None:
    if fichier:
        return Path(fichier).read_bytes()
    try:
        proc = subprocess.run(
            ["defaults", "export", "com.apple.symbolichotkeys", "-"], capture_output=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def cmd_raccourci(args: argparse.Namespace) -> int:
    reglages = config.charger(config.chemins_par_defaut())
    export = _export_systeme(args.export)
    if export is None:
        print("Export des raccourcis du système indisponible (pas sur un Mac ?) : rien n'est vérifié.")
        print(f"Raccourci de Voix : {Combinaison.lire(reglages.raccourci()).symboles()}")
        return 0
    try:
        systeme = lire_export(export)
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    try:
        voulu = Combinaison.lire(reglages.raccourci())
    except CombinaisonInvalide as e:
        print(f"❌ raccourci de reglages.toml refusé : {e}")
        return 1
    deja = conflit(voulu, systeme)
    if deja is None:
        print(f"✅ Raccourci de Voix : {voulu.symboles()} (libre côté macOS)")
        return 0
    libre, ecartes = choisir(systeme)
    print(f"⚠️ {voulu.symboles()} est pris par macOS ({deja}).")
    for raison in ecartes:
        print(f"  - {raison}")
    print(f"  Premier raccourci libre : {libre.symboles()} (écris-le dans reglages.toml, [raccourci])")
    return 1


def construire() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voix", description="Commandes vocales en français, 100 % locales.")
    sous = p.add_subparsers(dest="commande")
    sous.add_parser("version", help="la version de Voix")
    r = sous.add_parser("raccourci", help="le raccourci retenu, et ceux du système qu'il évite")
    r.add_argument("--export", help="lire un export de com.apple.symbolichotkeys au lieu du Mac")
    return p


def main(argv: list[str] | None = None) -> int:
    p = construire()
    args = p.parse_args(argv)
    if args.commande == "version":
        print(f"Voix {VERSION}")
        return 0
    if args.commande == "raccourci":
        return cmd_raccourci(args)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
