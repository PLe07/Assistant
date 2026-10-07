"""La ligne de commande `quotidien` (complétée phase après phase)."""

from __future__ import annotations

import argparse

from quotidien import __version__


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(prog="quotidien", description="Ton brief du quotidien.")
    parseur.add_argument("--version", action="version", version=f"quotidien {__version__}")
    parseur.parse_args(argv)
    parseur.print_help()
    return 0
