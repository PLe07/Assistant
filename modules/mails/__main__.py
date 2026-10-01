"""Module « mails » : tri automatique des mails dans Gmail (5 étiquettes).

Sous le superviseur (sans option) : un passage toutes les 3 minutes
(reglages.json → modules.mails.toutes_les_secondes).

À la main, dans ~/Assistant avec .venv activé :
    python -m modules.mails --test 20             classe les 20 derniers mails, SANS rien modifier
    python -m modules.mails --reel                un passage réel tout de suite
    python -m modules.mails --etat                dernier passage, erreurs, mails triés aujourd'hui
    python -m modules.mails --creer-etiquettes    crée les 5 étiquettes dans Gmail (aucun mail touché)
    python -m modules.mails --verifier-connexion  teste la connexion à Gmail (lecture seule)
    python -m modules.mails --migrer              copie les données de tri-mails/ (rien n'est supprimé)
"""

import argparse
import sys

from core.journal import journal
from core.module import executer
from modules.mails import tri


def boucle(ctx) -> None:
    while True:
        if not tri.claude_en_pause():
            tri.un_passage(ctx.log, interactif=False)
        if ctx.attendre(max(30, int(ctx.reglage("toutes_les_secondes", 180)))):
            return


def main(argv: list[str]) -> int:
    if not argv:  # lancé par le superviseur
        executer("mails", boucle)
        return 0
    parser = argparse.ArgumentParser(prog="python -m modules.mails", description="Tri automatique des mails")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--test", type=int, metavar="N", help="classe les N derniers mails, sans rien modifier")
    modes.add_argument("--reel", action="store_true", help="un passage réel tout de suite")
    modes.add_argument("--etat", action="store_true", help="dernier passage, erreurs, mails triés")
    modes.add_argument("--creer-etiquettes", action="store_true", help="crée les 5 étiquettes dans Gmail")
    modes.add_argument("--verifier-connexion", action="store_true", help="teste la connexion à Gmail")
    modes.add_argument("--migrer", action="store_true", help="copie les données de tri-mails/")
    parser.add_argument("--rattrapage-heures", type=float, default=None,
                        help="tout 1er passage uniquement : trier aussi les mails des N dernières heures")
    args = parser.parse_args(argv)

    if args.test is not None:
        return tri.mode_test(max(1, min(args.test, 50)))
    if args.reel:
        return tri.un_passage(journal("mails", ecran=True), interactif=True, rattrapage_heures=args.rattrapage_heures)
    if args.etat:
        return tri.afficher_etat()
    if args.creer_etiquettes:
        return tri.mode_creer_etiquettes()
    if args.verifier_connexion:
        return tri.verifier_connexion()
    from modules.mails.migration import migrer

    return migrer()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
