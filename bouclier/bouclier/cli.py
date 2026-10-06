"""La commande `bouclier` : tout ce que Bouclier sait faire, en français.

bouclier verifier "texte du SMS"        bouclier verifier message.eml       bouclier verifier --presse-papiers
bouclier historique
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bouclier import config, db, journal, reseau
from bouclier.systeme import Systeme


@dataclass
class Environnement:
    chemins: config.Chemins
    reglages: dict[str, Any]
    base: db.Base
    systeme: Systeme
    alerte_config: str | None = None


def preparer(systeme: Systeme | None = None) -> Environnement:
    reseau.installer_garde()
    chemins = config.chemins()
    reglages, alerte = config.charger_ou_defauts(chemins)
    chemins.support.mkdir(parents=True, exist_ok=True)
    journal.configurer(chemins.logs, reglages.get("moi", {}))
    return Environnement(chemins, reglages, db.ouvrir(chemins.base), systeme or Systeme(), alerte)


def _ecrire(texte: str) -> None:
    print(texte)


# --- verifier ------------------------------------------------------------------------------------------------------


def cmd_verifier(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier.arnaque import analyse, extraction

    outils = analyse.outils_reels(env.chemins, env.reglages, env.base, env.systeme)
    if args.presse_papiers:
        texte = env.systeme.presse_papiers()
        if not texte.strip():
            _ecrire("Le presse-papiers est vide : copie d'abord le message (⌘C), puis relance.")
            return 1
        message, source = extraction.depuis_texte(texte, "texte"), "presse-papiers"
    elif args.quoi and Path(args.quoi).expanduser().is_file():
        chemin = Path(args.quoi).expanduser()
        try:
            message = extraction.depuis_fichier(chemin, outils.lire_image)
        except (OSError, ValueError) as e:
            _ecrire(f"Je ne peux pas lire {chemin.name} : {e}.")
            return 1
        source = "fichier"
    elif args.quoi:
        message, source = extraction.depuis_texte(args.quoi, "texte"), "mac"
    elif not sys.stdin.isatty():
        message, source = extraction.depuis_texte(sys.stdin.read(), "texte"), "mac"
    else:
        _ecrire('Donne-moi le message : bouclier verifier "le texte"  (ou un fichier, ou --presse-papiers)')
        return 1
    if not message.texte.strip() and not message.avertissements:
        _ecrire("Le message est vide.")
        return 1
    resultat = analyse.verifier(message, outils, source, demande_ia=args.ia)
    _ecrire(resultat.reponse.texte())
    return 0


def cmd_historique(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier.arnaque import historique

    _ecrire(historique.formater(historique.lister(env.base, args.nombre)))
    return 0


# --- Analyse des arguments -----------------------------------------------------------------------------------------

Commande = Callable[[argparse.Namespace, Environnement], int]


def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bouclier", description="Bouclier : arnaques, comptes, fuites, métadonnées, urgence."
    )
    sous = p.add_subparsers(dest="commande", metavar="commande")

    v = sous.add_parser("verifier", help="est-ce une arnaque ? (texte, fichier .eml / .txt / capture, presse-papiers)")
    v.add_argument("quoi", nargs="?", help="le texte du message, ou le chemin d'un fichier")
    v.add_argument("--presse-papiers", action="store_true", help="vérifier le texte copié")
    v.add_argument("--ia", action="store_true", help="demander aussi l'avis de Claude, même si les règles sont sûres")
    v.set_defaults(fonction=cmd_verifier)

    h = sous.add_parser("historique", help="les dernières vérifications (texte caviardé, 90 jours)")
    h.add_argument("-n", "--nombre", type=int, default=20)
    h.set_defaults(fonction=cmd_historique)
    return p


def main(argv: Sequence[str] | None = None, systeme: Systeme | None = None) -> int:
    p = analyseur()
    args = p.parse_args(argv)
    fonction: Commande | None = getattr(args, "fonction", None)
    if fonction is None:
        p.print_help()
        return 0
    env = preparer(systeme)
    try:
        if env.alerte_config:
            _ecrire(f"⚠️ {env.alerte_config} (réglages par défaut utilisés)")
        return fonction(args, env)
    finally:
        env.base.fermer()
