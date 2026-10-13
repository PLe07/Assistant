"""La commande `voix` (en français, sans jargon).

voix version
voix raccourci [--export FICHIER]   le raccourci retenu, et les raccourcis du système qu'il évite
voix comprendre "PHRASE"            ce que Voix comprend de cette phrase (sans rien faire)
voix journal                        les dernières commandes (texte compris, action, résultat ; jamais d'audio)
voix oublier                        efface le journal
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from voix import VERSION, config, demarrage
from voix.journal import Journal
from voix.nlu.catalogue import Objet
from voix.nlu.comprendre import Comprehension, comprendre
from voix.nlu.intentions import INTENTIONS
from voix.raccourcis_systeme import Combinaison, CombinaisonInvalide, choisir, conflit, lire_export
from voix.session import contexte


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


def _valeur(v: Any) -> str:
    if isinstance(v, Objet):
        return f"{v.nom} ({v.genre})"
    return str(v)


def decrire(c: Comprehension) -> list[str]:
    """Ce que Voix a compris, en clair."""
    if c.statut == "compris" and c.intention is not None:
        lignes = [f"Compris : {INTENTIONS[c.intention].titre} [{c.intention}]"]
        lignes += [f"  {k} : {_valeur(v)}" for k, v in c.params.items()]
        if c.sensible:
            lignes.append("  ⚠️ action sensible : Voix demandera « Tu confirmes ? »")
        return lignes
    if c.statut == "ambigu":
        return [f"Hésitation : {c.raison}", *(f"  - {x.libelle}" for x in c.choix)]
    if c.statut in ("refus", "negation"):
        return [f"Refus : {c.raison}" if c.statut == "refus" else f"Rien à faire : {c.raison}"]
    if c.statut == "vide":
        return ["Rien entendu."]
    lignes = ["Pas compris."]
    if c.suggestions:
        lignes.append("  Essaie : " + " ; ".join(f"« {s} »" for s in c.suggestions))
    return lignes


def cmd_comprendre(args: argparse.Namespace) -> int:
    chemins = config.chemins_par_defaut()
    reglages = config.charger(chemins)
    c = comprendre(" ".join(args.phrase), contexte(demarrage.outils(chemins, reglages)))
    print("\n".join(decrire(c)))
    return 0 if c.statut == "compris" else 1


def _journal() -> Journal:
    chemins = config.chemins_par_defaut()
    j = config.charger(chemins)["journal"]
    return Journal(chemins.journal, bool(j["actif"]), int(j["taille"]))


def cmd_journal(_args: argparse.Namespace) -> int:
    j = _journal()
    entrees = j.lire()
    if not j.actif:
        print("Journal désactivé (reglages.toml, [journal] actif = false).")
    if not entrees:
        print("Journal vide.")
        return 0
    for e in entrees:
        quand = str(e.get("quand", ""))[:16].replace("T", " ")
        print(f"{quand}  « {e.get('texte', '')} » → {e.get('statut', '')} : {e.get('resultat', '')}")
    return 0


def cmd_oublier(_args: argparse.Namespace) -> int:
    print("Journal effacé." if _journal().oublier() else "Journal déjà vide.")
    return 0


def construire() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voix", description="Commandes vocales en français, 100 % locales.")
    sous = p.add_subparsers(dest="commande")
    sous.add_parser("version", help="la version de Voix")
    r = sous.add_parser("raccourci", help="le raccourci retenu, et ceux du système qu'il évite")
    r.add_argument("--export", help="lire un export de com.apple.symbolichotkeys au lieu du Mac")
    c = sous.add_parser("comprendre", help="ce que Voix comprend d'une phrase (sans rien faire)")
    c.add_argument("phrase", nargs="+")
    sous.add_parser("journal", help="les dernières commandes")
    sous.add_parser("oublier", help="efface le journal")
    return p


def main(argv: list[str] | None = None) -> int:
    p = construire()
    args = p.parse_args(argv)
    if args.commande == "version":
        print(f"Voix {VERSION}")
        return 0
    commandes = {"raccourci": cmd_raccourci, "comprendre": cmd_comprendre, "journal": cmd_journal,
                 "oublier": cmd_oublier}  # fmt: skip
    if args.commande in commandes:
        return commandes[args.commande](args)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
