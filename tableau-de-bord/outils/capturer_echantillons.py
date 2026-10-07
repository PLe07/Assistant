"""Capturer des échantillons réels, anonymisés, des journaux et des bases des modules installés (§9.2).

Les bases ne sont jamais ouvertes : elles sont **copiées** (voir `tableau/sondes/sqlite_copie.py`) puis lues dans la
copie. On garde le schéma exact et quelques lignes par table, avec chaque texte libre remplacé ou caviardé ; les
journaux : les dernières lignes, caviardées, noms de fichiers remplacés.

    python outils/capturer_echantillons.py --assistant ~/Assistant --sortie tests/fixtures/reelles/mac

Sur ton Mac, `install.sh` le lance vers `tests/fixtures/reelles/mac/` (jamais sur GitHub) puis rejoue les tests des
adaptateurs dessus.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import tempfile
from collections import deque
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tableau.caviardage import caviarder  # noqa: E402
from tableau.sondes.sqlite_copie import copie  # noqa: E402

# Colonnes dont la valeur est un état, un genre ou une clé technique : gardées telles quelles si elles sont courtes.
COLONNES_TECHNIQUES = {
    "etat", "type", "source", "statut", "genre", "kind", "mois", "cle", "niveau", "module", "modele", "mode", "par",
    "nom_tache", "role", "usage", "resultat", "categorie", "nature", "fiche_id", "jour", "echeance", "semaine",
}  # fmt: skip
# Clés de méta dont la valeur est un instant ou un nombre : gardées (elles disent le battement, les dernières tâches).
TECHNIQUE = re.compile(r"^[\w\-.:/ ]{0,40}$")
NUMERIQUE = re.compile(r"^-?\d+(\.\d+)?$")
# Un nom de fichier, même avec des espaces (« Relevé octobre 2026.pdf ») ou précédé de son dossier : remplacé en
# entier (mieux vaut effacer quelques mots de trop que laisser un nom de document personnel).
FICHIER = re.compile(
    r"(?:[~/][^\n:«»\"'→]*?|[^\s/«»\"':\]→]+(?: [^\s/«»\"':\]→]+){0,6})"
    r"\.(pdf|jpe?g|png|heic|docx?|xlsx?|txt|zip|eml|mp4|mov)\b",
    re.IGNORECASE,
)


def anonymiser_texte(texte: str) -> str:
    t = FICHIER.sub(lambda m: f"document.{m.group(1).lower()}", texte)
    return caviarder(t, longueur_max=300, compacter=False)


def anonymiser_valeur(colonne: str, valeur: object) -> object:
    if valeur is None or isinstance(valeur, (int, float)):
        return valeur
    if isinstance(valeur, bytes):
        return None
    texte = str(valeur)
    if NUMERIQUE.match(texte):
        return texte
    if colonne.lower() in COLONNES_TECHNIQUES and TECHNIQUE.match(texte):
        return texte
    if colonne.lower() == "valeur" and (NUMERIQUE.match(texte) or len(texte) <= 12):
        return texte
    return f"[{colonne}]"


def litteral(valeur: object) -> str:
    if valeur is None:
        return "NULL"
    if isinstance(valeur, (int, float)):
        return repr(valeur)
    return "'" + str(valeur).replace("'", "''") + "'"


def lignes_utiles(db: sqlite3.Connection, table: str, n: int) -> list[sqlite3.Row]:
    """Les dernières lignes (les plus récentes portent le battement, les coûts du mois…)."""
    try:
        return list(db.execute(f'SELECT * FROM "{table}" ORDER BY rowid DESC LIMIT ?', (n,)).fetchall())[::-1]
    except sqlite3.DatabaseError:
        return list(db.execute(f'SELECT * FROM "{table}" LIMIT ?', (n,)).fetchall())


def exporter_base(source: Path, sortie: Path, n: int = 12) -> str:
    """Le schéma exact et quelques lignes anonymisées, en SQL rejouable."""
    morceaux = [f"-- Échantillon anonymisé de {source.name} (schéma exact, {n} lignes au plus par table)."]
    with tempfile.TemporaryDirectory() as dossier, copie(source, Path(dossier)) as db:
        objets = db.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type = 'index', rowid"
        ).fetchall()
        for _type, _nom, sql in objets:
            morceaux.append(sql.strip() + ";")
        for _type, nom, _sql in objets:
            if _type != "table":
                continue
            for ligne in lignes_utiles(db, nom, n):
                cols = ligne.keys()
                valeurs = [anonymiser_valeur(c, ligne[c]) for c in cols]
                morceaux.append(
                    f'INSERT INTO "{nom}" ({", ".join(cols)}) VALUES ({", ".join(map(litteral, valeurs))});'
                )
    texte = "\n".join(morceaux) + "\n"
    sortie.write_text(texte, encoding="utf-8")
    return texte


NOTABLE = re.compile(r"ERROR|WARNING|CRITICAL|Plantage|Traceback|\[superviseur\]|tombé")


def exporter_journal(source: Path, sortie: Path, n: int = 400, notables: int = 120) -> int:
    """Les `n` dernières lignes, plus des lignes notables plus anciennes (erreurs, avertissements, superviseur),
    pour que l'échantillon montre chaque forme de ligne, dans l'ordre d'origine."""
    dernieres: deque[tuple[int, str]] = deque(maxlen=n)
    vues: deque[tuple[int, str]] = deque(maxlen=notables)
    with open(source, encoding="utf-8", errors="replace") as f:
        for i, ligne in enumerate(f):
            dernieres.append((i, ligne))
            if NOTABLE.search(ligne):
                vues.append((i, ligne))
    choisies = sorted(dict(list(vues) + list(dernieres)).items())
    lignes = [anonymiser_texte(ligne.rstrip("\n")) for _i, ligne in choisies]
    sortie.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return len(lignes)


def sources(assistant: Path | None, maison: Path) -> dict[str, list[tuple[str, Path]]]:
    support = maison / "Library" / "Application Support"
    journaux = maison / "Library" / "Logs"
    resultat: dict[str, list[tuple[str, Path]]] = {
        "bouclier": [
            ("base", support / "Bouclier" / "bouclier.db"),
            ("journal", journaux / "Bouclier" / "bouclier.log"),
        ],
        "quotidien": [
            ("base", support / "Quotidien" / "quotidien.db"),
            ("journal", journaux / "Quotidien" / "quotidien.log"),
        ],  # fmt: skip
    }
    for d in (support / "Ambiance", journaux / "Ambiance"):
        if d.is_dir():
            for f in sorted(d.glob("*.db")) + sorted(d.glob("*.log")):
                resultat.setdefault("ambiance", []).append(("base" if f.suffix == ".db" else "journal", f))
    if assistant is not None:
        resultat["assistant"] = [("base", assistant / "donnees" / "etat.db"),
                                 ("journal", assistant / "logs" / "assistant.log")]  # fmt: skip
        resultat["trieur"] = [("base", assistant / "donnees" / "trieur" / "trieur.db")]
        resultat["corvees"] = [("base", assistant / "donnees" / "corvees" / "corvees.db")]
        resultat["nettoyeur"] = [("base", assistant / "donnees" / "demarrage" / "demarrage.db")]
    return resultat


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--assistant", type=Path, default=None, help="le dossier de l'assistant (~/Assistant)")
    p.add_argument("--maison", type=Path, default=Path.home())
    p.add_argument("--sortie", type=Path, required=True)
    args = p.parse_args(argv)
    args.sortie.mkdir(parents=True, exist_ok=True)
    trouves = 0
    for module, liste in sources(args.assistant, args.maison).items():
        for genre, chemin in liste:
            if not chemin.is_file():
                continue
            cible = args.sortie / f"{module}-{chemin.stem}.{'sql' if genre == 'base' else 'log'}"
            try:
                if genre == "base":
                    exporter_base(chemin, cible)
                else:
                    exporter_journal(chemin, cible)
            except Exception as e:  # noqa: BLE001 - une source illisible n'empêche pas les autres
                print(f"  ⚠️ {module} : {chemin.name} illisible ({e.__class__.__name__})")
                continue
            trouves += 1
            print(f"  ✅ {module} : {chemin.name} → {cible.name}")
    print(f"{trouves} échantillon(s) capturé(s) dans {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
