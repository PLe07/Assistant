"""Tes alias, playlists et routines (`commandes.toml`, dans le dossier de Voix).

- **alias** : « la compta » → un fichier ou un dossier de ta maison, une adresse `https://`, ou une app (`app:Notion`).
  Rien d'autre n'est accepté (pas de `file://`, pas de commande) ;
- **playlist** : un nom (et son adresse Spotify si besoin) pour « lance la playlist Révisions » ;
- **routine** : des phrases (« lance ma révision ») et des étapes, chacune une intention de la liste blanche avec
  ses paramètres (vérifiés avant de lancer quoi que ce soit). `sensible = true` : confirmation avant.

`voix apprendre "la compta" ~/Documents/Compta.numbers` ajoute un alias **à la fin** du fichier, sans toucher au
reste.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voix.nlu.approx import forme_normale
from voix.nlu.catalogue import Objet

NOM_MAX = 60
_URI_SPOTIFY = re.compile(r"^spotify:(?:playlist|album|artist|track):[A-Za-z0-9]{10,40}$")


class CibleRefusee(ValueError):
    """Une cible d'alias refusée (hors de ta maison, schéma inconnu, introuvable…)."""


@dataclass(frozen=True)
class Routine:
    nom: str
    phrases: tuple[str, ...]
    etapes: tuple[dict[str, Any], ...]
    sensible: bool = False


@dataclass
class Commandes:
    alias: list[Objet] = field(default_factory=list)
    playlists: list[Objet] = field(default_factory=list)
    routines: list[Routine] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)

    def objets(self) -> list[Objet]:
        routines = [Objet("routine", r.nom, r.nom, r.nom, (forme_normale(r.nom), *r.phrases)) for r in self.routines]
        return [*self.alias, *self.playlists, *routines]

    def routine(self, nom: str) -> Routine | None:
        return next((r for r in self.routines if r.nom == nom), None)


def verifier_cible(cible: str, maison: Path, existe: bool = True) -> str:
    """La cible normalisée d'un alias, ou CibleRefusee."""
    brut = cible.strip()
    if brut.startswith("https://"):
        if any(c in brut for c in " \n\t\"'<>`\\") or len(brut) > 500:
            raise CibleRefusee("adresse invalide")
        return brut
    if brut.startswith("app:"):
        nom = brut[4:].strip()
        if not nom or len(nom) > NOM_MAX or "/" in nom:
            raise CibleRefusee("nom d'app invalide")
        return f"app:{nom}"
    if "://" in brut or brut.startswith(("http:", "file:", "javascript:", "data:")):
        raise CibleRefusee("seules les adresses https:// sont acceptées")
    chemin = Path(os.path.expanduser(brut.replace("~", str(maison), 1) if brut.startswith("~") else brut))
    try:
        reel = chemin.resolve()
        maison_reelle = maison.resolve()
    except OSError as e:
        raise CibleRefusee(f"chemin illisible ({e.__class__.__name__})") from e
    if reel != maison_reelle and maison_reelle not in reel.parents:
        raise CibleRefusee("seuls les fichiers et dossiers de ta maison sont acceptés")
    if existe and not reel.exists():
        raise CibleRefusee("fichier ou dossier introuvable")
    return str(reel)


def _texte(v: Any) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() and len(v.strip()) <= NOM_MAX else None


def _formes(nom: str, brutes: Any) -> tuple[str, ...]:
    formes = [forme_normale(nom)]
    if isinstance(brutes, list):
        formes += [forme_normale(f) for f in brutes if isinstance(f, str) and f.strip()]
    return tuple(dict.fromkeys(f for f in formes if f))


def lire(texte: str, maison: Path) -> Commandes:
    c = Commandes()
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        c.erreurs.append(f"commandes.toml illisible ({e}) : alias et routines ignorés")
        return c
    for i, a in enumerate(donnees.get("alias", []) if isinstance(donnees.get("alias"), list) else []):
        nom = _texte(a.get("nom")) if isinstance(a, dict) else None
        if nom is None or not isinstance(a.get("cible"), str):
            c.erreurs.append(f"alias n°{i + 1} : il faut un « nom » et une « cible »")
            continue
        try:
            cible = verifier_cible(a["cible"], maison, existe=False)
        except CibleRefusee as e:
            c.erreurs.append(f"alias « {nom} » refusé : {e}")
            continue
        c.alias.append(Objet("alias", nom, cible, f"alias:{nom}", _formes(nom, a.get("formes"))))
    for i, p in enumerate(donnees.get("playlist", []) if isinstance(donnees.get("playlist"), list) else []):
        nom = _texte(p.get("nom")) if isinstance(p, dict) else None
        if nom is None:
            c.erreurs.append(f"playlist n°{i + 1} : il faut un « nom »")
            continue
        lecteur = p.get("lecteur", "musique")
        uri = p.get("uri", "") or ""
        if lecteur not in ("musique", "spotify"):
            c.erreurs.append(f"playlist « {nom} » : lecteur « musique » ou « spotify »")
            continue
        if lecteur == "spotify" and not _URI_SPOTIFY.match(uri):
            c.erreurs.append(f"playlist « {nom} » : pour Spotify, une adresse spotify:playlist:… est nécessaire")
            continue
        cible = uri if lecteur == "spotify" else nom
        c.playlists.append(Objet("playlist", nom, cible, f"{lecteur}:{nom}", _formes(nom, p.get("formes"))))
    for i, r in enumerate(donnees.get("routine", []) if isinstance(donnees.get("routine"), list) else []):
        nom = _texte(r.get("nom")) if isinstance(r, dict) else None
        if nom is None:
            c.erreurs.append(f"routine n°{i + 1} : il faut un « nom »")
            continue
        phrases = r.get("phrases", [])
        etapes = r.get("etapes", [])
        if not isinstance(phrases, list) or not phrases or not all(isinstance(x, str) for x in phrases):
            c.erreurs.append(f"routine « {nom} » : il faut au moins une phrase")
            continue
        if not isinstance(etapes, list) or not etapes or not all(isinstance(e, dict) for e in etapes):
            c.erreurs.append(f"routine « {nom} » : il faut au moins une étape")
            continue
        if not all(isinstance(e.get("intention"), str) for e in etapes):
            c.erreurs.append(f"routine « {nom} » : chaque étape a une « intention »")
            continue
        sensible = r.get("sensible", False)
        if not isinstance(sensible, bool):
            c.erreurs.append(f"routine « {nom} » : sensible = true ou false")
            continue
        formes = tuple(dict.fromkeys(forme_normale(x) for x in phrases if forme_normale(x)))
        c.routines.append(Routine(nom, formes, tuple(dict(e) for e in etapes), sensible))
    return c


def charger(fichier: Path, maison: Path) -> Commandes:
    if not fichier.exists():
        return Commandes()
    try:
        return lire(fichier.read_text(encoding="utf-8"), maison)
    except (OSError, UnicodeDecodeError) as e:
        return Commandes(erreurs=[f"commandes.toml illisible ({e.__class__.__name__})"])


def _echapper_toml(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace('"', '\\"')


def apprendre(fichier: Path, maison: Path, nom: str, cible: str) -> str:
    """Ajoute un alias à la fin de commandes.toml (créé s'il n'existe pas). Rend la cible retenue."""
    propre = " ".join(nom.split())
    if not propre or len(propre) > NOM_MAX or not forme_normale(propre):
        raise CibleRefusee("nom d'alias vide ou trop long")
    retenue = verifier_cible(cible, maison, existe=True)
    existants = charger(fichier, maison)
    if any(forme_normale(a.nom) == forme_normale(propre) for a in existants.alias):
        raise CibleRefusee(f"l'alias « {propre} » existe déjà (modifie-le dans commandes.toml)")
    bloc = f'\n[[alias]]\nnom = "{_echapper_toml(propre)}"\ncible = "{_echapper_toml(retenue)}"\n'
    fichier.parent.mkdir(parents=True, exist_ok=True)
    with open(fichier, "a", encoding="utf-8") as f:
        f.write(bloc)
    os.chmod(fichier, 0o600)
    return retenue
