"""Les personnes et leurs fiches (§6) : Contacts du Mac (lecture seule) + `proches.toml`.

`proches.toml` (dans Application Support/Quotidien) sert à deux choses :
- ajouter quelqu'un qui n'est pas dans tes Contacts (avec sa date) ;
- donner une fiche à quelqu'un qui y est (relation, ton, notes), reliée par le prénom et le nom.

    [[personne]]
    prenom = "Léa"
    nom = "Exemple"                 # facultatif : relie la fiche au contact (jamais envoyé à l'IA)
    anniversaire = "14/03/2001"     # ou "14/03" sans l'année
    relation = "ami_proche"         # famille, couple, ami_proche, ami, collegue, professeur
    ton = "drole"                   # tendre, drole, sobre, formel
    notes = ["souvenir : voyage à Lisbonne", "adore le foot"]
    telephone = "06 00 00 00 00"    # facultatif : prérempli dans Messages (jamais envoyé à l'IA)

Une personne sans fiche : relation inconnue, ton « sobre et chaleureux ».
Un fichier mal rempli ne bloque rien : la fiche fautive est ignorée avec un message clair.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from quotidien import config
from quotidien.anniversaires import dates
from quotidien.repas.envies import normaliser

PROCHES = ("famille", "couple", "ami_proche")  # rappel J-7 pour penser au cadeau
TON_DEFAUT = "sobre"
NOTES_MAX = 5
NOTE_LONGUEUR_MAX = 120


@dataclass(frozen=True)
class Personne:
    cle: str  # stable et anonyme (empreinte), sert aux rappels déjà émis
    prenom: str
    nom: str  # nom de famille : jamais envoyé à l'IA, jamais écrit dans un journal
    naissance: dates.DateNaissance
    relation: str | None = None
    ton: str = TON_DEFAUT
    notes: tuple[str, ...] = ()
    telephone: str = ""  # jamais envoyé, jamais enregistré
    source: str = "proches"  # « contacts » ou « proches »
    fiche: bool = False

    @property
    def proche(self) -> bool:
        return self.relation in PROCHES


@dataclass
class Lecture:
    personnes: list[Personne] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


def chemin() -> Path:
    return config.dossier_support() / "proches.toml"


def cle_de(*morceaux: str) -> str:
    brut = "|".join(normaliser(m) for m in morceaux)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


def _texte(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def lire_fiches(fichier: Path | None = None, aujourdhui: date | None = None) -> Lecture:
    """Les fiches de `proches.toml` (Personne avec ou sans date : sans date, c'est une fiche pour un contact)."""
    fichier = fichier or chemin()
    lecture = Lecture()
    if not fichier.is_file():
        return lecture
    try:
        brut = tomllib.loads(fichier.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as err:
        lecture.avertissements.append(f"proches.toml est illisible ({err.__class__.__name__}) : il est ignoré.")
        return lecture
    entrees = brut.get("personne", [])
    if not isinstance(entrees, list):
        lecture.avertissements.append("proches.toml : utilise des blocs [[personne]] (voir proches.example.toml).")
        return lecture
    for n, fiche in enumerate(entrees, 1):
        if not isinstance(fiche, dict):
            continue
        e: dict[str, Any] = fiche
        prenom = _texte(e.get("prenom"))
        if not prenom:
            lecture.avertissements.append(f"proches.toml, personne n°{n} : il manque le prénom, fiche ignorée.")
            continue
        nom = _texte(e.get("nom"))
        naissance = dates.DateNaissance(0, 0)
        if e.get("anniversaire") not in (None, ""):
            try:
                naissance = dates.lire(str(e["anniversaire"]), aujourdhui)
            except dates.DateInvalide as err:
                lecture.avertissements.append(f"proches.toml, {prenom} : {err} ; fiche gardée sans date.")
        relation: str | None = normaliser(_texte(e.get("relation")).replace("-", " ")).replace(" ", "_") or None
        if relation is not None and relation not in config.RELATIONS:
            lecture.avertissements.append(f"proches.toml, {prenom} : relation « {e.get('relation')} » inconnue "
                                          f"(permis : {', '.join(config.RELATIONS)}) ; ignorée.")  # fmt: skip
            relation = None
        ton = normaliser(_texte(e.get("ton"))) or TON_DEFAUT
        if ton not in config.TONS:
            lecture.avertissements.append(f"proches.toml, {prenom} : ton « {ton} » inconnu (permis : "
                                          f"{', '.join(config.TONS)}) ; « sobre » utilisé.")  # fmt: skip
            ton = TON_DEFAUT
        notes_brutes = e.get("notes", [])
        if isinstance(notes_brutes, str):
            notes_brutes = [notes_brutes]
        notes = tuple(_texte(x)[:NOTE_LONGUEUR_MAX] for x in notes_brutes if _texte(x))[:NOTES_MAX]
        lecture.personnes.append(Personne(cle_de("proche", prenom, nom), prenom, nom, naissance, relation, ton, notes,
                                          _texte(e.get("telephone")), "proches", True))  # fmt: skip
    return lecture


def _meme_personne(fiche: Personne, contact: Personne) -> bool:
    if normaliser(fiche.prenom) != normaliser(contact.prenom):
        return False
    return not fiche.nom or normaliser(fiche.nom) == normaliser(contact.nom)


def fusionner(contacts: list[Personne], fiches: list[Personne]) -> list[Personne]:
    """Les contacts, enrichis de leur fiche ; puis les fiches avec une date qui ne sont pas des contacts.

    Une fiche reliée à plusieurs contacts (même prénom, pas de nom) n'en enrichit aucun : on ne devine pas."""
    resultat: list[Personne] = []
    utilisees: set[str] = set()
    for c in contacts:
        candidates = [f for f in fiches if _meme_personne(f, c)]
        if len(candidates) == 1 and sum(_meme_personne(candidates[0], x) for x in contacts) == 1:
            f = candidates[0]
            utilisees.add(f.cle)
            naissance = f.naissance if f.naissance.jour else c.naissance
            c = replace(c, naissance=naissance, relation=f.relation, ton=f.ton, notes=f.notes,
                        telephone=f.telephone or c.telephone, fiche=True)  # fmt: skip
        resultat.append(c)
    resultat += [f for f in fiches if f.cle not in utilisees and f.naissance.jour]
    return resultat
