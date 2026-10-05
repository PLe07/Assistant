"""La commande « demarrage » :  python demarrage.py <commande>  (ou python assistant.py demarrage <commande>).

doctor                     la machine, les commandes disponibles, ce qui marchera en mode dégradé
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from modules.demarrage import config, environnement
from modules.demarrage.systeme import Mac, Systeme


class Contexte:
    """Ce dont chaque commande a besoin : les réglages, le Mac (vrai ou faux), et où écrire."""

    def __init__(
        self,
        reglages: dict[str, Any] | None = None,
        systeme: Systeme | None = None,
        ecrire: Callable[[str], None] = print,
    ):
        self.reglages = reglages or config.charger()[0]
        self.systeme: Systeme = systeme or Mac()
        self.ecrire = ecrire


def _ligne(ok: bool | None, texte: str) -> str:
    return f"   {'✅' if ok else '⚠️' if ok is None else '❌'} {texte}"


def doctor(ctx: Contexte, _: argparse.Namespace) -> int:
    env = environnement.reconnaitre(ctx.systeme)
    ctx.ecrire("🩺 Nettoyeur de démarrage")
    ctx.ecrire(_ligne(env.macos[:1].isdigit(), f"macOS {env.macos} · {env.architecture} · Python {env.python}"))
    for nom, role in environnement.COMMANDES.items():
        ctx.ecrire(_ligne(env.commandes[nom] or None, f"{nom} : {role}" + ("" if env.commandes[nom] else " — absente")))
    if env.manquantes:
        ctx.ecrire(f"   {len(env.manquantes)} commande(s) absente(s) : ce qui en dépend sera marqué « dégradé ».")
    return 0


def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="demarrage", description="Le Nettoyeur de démarrage")
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("doctor", help="ce qui marche, ce qui est dégradé").set_defaults(faire=doctor)
    return p


def main(argv: list[str], ctx: Contexte | None = None) -> int:
    if not argv or argv[0] in ("aide", "help", "-h", "--help"):
        print(__doc__)
        return 0
    args = analyseur().parse_args(argv)
    ctx = ctx or Contexte()
    code: int = args.faire(ctx, args)
    return code
