"""Les identifiants enregistrés dans les navigateurs : **seulement** le site et le nom d'utilisateur.

- Chrome, Brave, Edge, Arc : le fichier `Login Data` (SQLite) est copié dans un dossier temporaire (le navigateur
  peut l'avoir verrouillé), puis lu avec une seule requête : `SELECT origin_url, username_value FROM logins`.
  La colonne du mot de passe n'est jamais nommée ni lue (un test espionne chaque requête SQL).
- Firefox : `logins.json`, copié puis lu en écartant au fil de la lecture tout champ dont le nom contient
  « password » (il n'est jamais gardé ni utilisé). Le nom d'utilisateur y est chiffré : seul le site est gardé.
- Safari : ses mots de passe sont dans le trousseau, auquel Bouclier ne touche pas (interdit).

Les copies temporaires sont effacées aussitôt lues ; les originaux ne sont jamais ouverts en écriture.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUETE = "SELECT origin_url, username_value FROM logins"

# Navigateurs de la famille Chrome : (nom, dossier sous ~/Library/Application Support)
CHROMIUM = (
    ("Chrome", "Google/Chrome"),
    ("Brave", "BraveSoftware/Brave-Browser"),
    ("Edge", "Microsoft Edge"),
    ("Arc", "Arc/User Data"),
)


@dataclass(frozen=True)
class Identifiant:
    navigateur: str
    site: str
    utilisateur: str  # vide pour Firefox (chiffré) : jamais affiché en entier


def _profils_chromium(racine: Path) -> list[Path]:
    if not racine.is_dir():
        return []
    return sorted(p / "Login Data" for p in racine.iterdir() if p.is_dir() and (p / "Login Data").is_file())


def lire_chromium(fichier: Path, navigateur: str, trace: list[str] | None = None) -> list[Identifiant]:
    with tempfile.TemporaryDirectory(prefix="bouclier-nav-") as tmp:
        copie = Path(tmp) / "copie.sqlite"
        shutil.copyfile(fichier, copie)
        cx = sqlite3.connect(f"file:{copie}?mode=ro", uri=True)
        if trace is not None:
            cx.set_trace_callback(trace.append)
        try:
            lignes = cx.execute(REQUETE).fetchall()
        except sqlite3.DatabaseError:
            lignes = []
        finally:
            cx.close()
    return [Identifiant(navigateur, str(site or ""), str(nom or "")) for site, nom in lignes if site]


def _sans_mot_de_passe(paires: list[tuple[str, Any]]) -> dict[str, Any]:
    return {k: v for k, v in paires if "password" not in k.lower()}


def lire_firefox(fichier: Path) -> list[Identifiant]:
    with tempfile.TemporaryDirectory(prefix="bouclier-nav-") as tmp:
        copie = Path(tmp) / "logins.json"
        shutil.copyfile(fichier, copie)
        try:
            data = json.loads(copie.read_text(encoding="utf-8"), object_pairs_hook=_sans_mot_de_passe)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
    sortie = []
    for entree in data.get("logins", []) if isinstance(data, dict) else []:
        site = entree.get("hostname") or entree.get("formSubmitURL") or ""
        if site:
            sortie.append(Identifiant("Firefox", str(site), ""))
    return sortie


@dataclass
class Releve:
    identifiants: list[Identifiant]
    navigateurs: list[str]  # ceux qui ont été lus
    erreurs: list[str]


def relever(maison: Path, trace: list[str] | None = None) -> Releve:
    support = maison / "Library" / "Application Support"
    releve = Releve([], [], [])
    for nom, dossier in CHROMIUM:
        for fichier in _profils_chromium(support / dossier):
            try:
                releve.identifiants += lire_chromium(fichier, nom, trace)
                if nom not in releve.navigateurs:
                    releve.navigateurs.append(nom)
            except OSError as e:
                releve.erreurs.append(f"{nom} : {e.__class__.__name__}")
    profils = support / "Firefox" / "Profiles"
    if profils.is_dir():
        for fichier in sorted(profils.glob("*/logins.json")):
            try:
                releve.identifiants += lire_firefox(fichier)
                if "Firefox" not in releve.navigateurs:
                    releve.navigateurs.append("Firefox")
            except OSError as e:
                releve.erreurs.append(f"Firefox : {e.__class__.__name__}")
    return releve
