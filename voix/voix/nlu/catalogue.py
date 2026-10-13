"""Le catalogue des objets que Voix connaît : apps, dossiers, sites, alias, raccourcis Apple, routines, playlists.

Chaque objet a des **formes parlées** (« VS Code » : `vs code`, `vi esse code`, `visual studio code`…) ; on cherche
l'objet dont une forme ressemble le plus à ce qui a été dit (écriture et prononciation, voir `approx`).
Construit automatiquement (apps installées, dossiers courants, sites, `shortcuts list`) et complété par tes alias,
routines et playlists de `commandes.toml`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from voix.nlu.approx import Forme, forme_normale, sans_articles, similarite

ICI = Path(__file__).resolve().parent
GENRES = ("alias", "app", "dossier", "site", "raccourci", "routine", "playlist")

LETTRES = {
    "a": "a", "b": "be", "c": "ce", "d": "de", "e": "e", "f": "effe", "g": "ge", "h": "ache", "i": "i", "j": "ji",
    "k": "ka", "l": "elle", "m": "emme", "n": "enne", "o": "o", "p": "pe", "q": "ku", "r": "erre", "s": "esse",
    "t": "te", "u": "u", "v": "ve", "w": "double ve", "x": "ixe", "y": "i grec", "z": "zede",
}  # fmt: skip
CHIFFRES = {"0": "zero", "1": "un", "2": "deux", "3": "trois", "4": "quatre", "5": "cinq", "6": "six", "7": "sept",
            "8": "huit", "9": "neuf"}  # fmt: skip
EDITEURS = ("microsoft", "google", "adobe", "apple", "the")
SCORE_PARTIEL = 0.84  # au-dessus du seuil (0,80) ; plusieurs objets qui contiennent ce mot → « lequel ? »
SUFFIXES_INUTILES = {"us", "app", "io", "com", "desktop", "mac", "for", "macos", "player"}


@dataclass(frozen=True)
class Objet:
    genre: str  # alias, app, dossier, site, raccourci, routine, playlist
    nom: str  # affiché : « Notion », « Téléchargements »
    cible: str  # chemin, adresse, nom du raccourci…
    ident: str  # identifiant stable : bundle id, chemin, adresse
    formes: tuple[str, ...]


@dataclass(frozen=True)
class Candidat:
    objet: Objet
    score: float
    forme: str


def formes_parlees(nom: str) -> list[str]:
    """Les façons de dire un nom d'app : « GarageBand » → garageband, garage band ; « VLC » → vlc, ve elle ce."""
    formes: list[str] = []

    def ajouter(texte: str) -> None:
        t = forme_normale(texte)
        if t and t not in formes:
            formes.append(t)

    brut = re.sub(r"\.app$", "", nom.strip(), flags=re.IGNORECASE)
    ajouter(brut)
    separe = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", brut)  # camelCase → mots
    ajouter(separe)
    mots = forme_normale(separe).split()
    sans_suffixe = [m for m in mots if m not in SUFFIXES_INUTILES]
    if sans_suffixe and sans_suffixe != mots:
        ajouter(" ".join(sans_suffixe))
    sans_version = [m for m in sans_suffixe if not re.fullmatch(r"\d+(\.\d+)*", m)]
    if sans_version and sans_version != sans_suffixe:
        ajouter(" ".join(sans_version))
    if len(sans_version) > 1 and sans_version[0] in EDITEURS and len(" ".join(sans_version[1:])) >= 4:
        ajouter(" ".join(sans_version[1:]))
    # Sigles épelés à la française : « VLC » → « ve elle ce ».
    for mot in re.findall(r"\b[A-Z]{2,4}\b", brut):
        ajouter(brut.replace(mot, " ".join(LETTRES[c.lower()] for c in mot)))
    # Chiffres en mots : « 1Password » → « un password ».
    if re.search(r"\d", brut):
        ajouter(re.sub(r"\d", lambda m: f" {CHIFFRES[m.group(0)]} ", brut))
    return formes


@dataclass
class Catalogue:
    objets: list[Objet] = field(default_factory=list)
    _index: list[tuple[Forme, Objet]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.reindexer()

    def reindexer(self) -> None:
        self._index = [(Forme.de(f), o) for o in self.objets for f in o.formes]

    def ajouter(self, objets: Iterable[Objet]) -> None:
        self.objets.extend(objets)
        self.reindexer()

    def du_genre(self, genre: str) -> list[Objet]:
        return [o for o in self.objets if o.genre == genre]

    def chercher(self, texte: str, genres: Iterable[str] | None = None, plancher: float = 0.5) -> list[Candidat]:
        """Les objets qui ressemblent à `texte`, du plus ressemblant au moins, un seul candidat par objet."""
        voulus = set(genres) if genres is not None else None
        requete = Forme.de(texte)
        if not requete.colle:
            return []
        mots = set(sans_articles(requete.texte).split())
        partiel = any(len(m) >= 4 for m in mots)
        meilleurs: dict[tuple[str, str], Candidat] = {}
        for forme, objet in self._index:
            if voulus is not None and objet.genre not in voulus:
                continue
            s = similarite(requete, forme)
            if partiel and s < SCORE_PARTIEL and mots < set(forme.texte.split()):
                s = SCORE_PARTIEL  # une partie du nom : « ma playlist jazz » → « Jazz du soir » (s'il est seul)
            if s < plancher:
                continue
            cle = (objet.genre, objet.ident)
            if cle not in meilleurs or s > meilleurs[cle].score:
                meilleurs[cle] = Candidat(objet, s, forme.texte)
        return sorted(meilleurs.values(), key=lambda c: (-c.score, c.objet.genre, c.objet.nom))


def apps_connues() -> dict[str, dict]:
    """Les formes parlées connues des apps courantes (noms français des apps Apple, prononciations à la française)."""
    return json.loads((ICI / "apps_connues.json").read_text(encoding="utf-8"))


def sites() -> list[Objet]:
    donnees = json.loads((ICI / "sites.json").read_text(encoding="utf-8"))
    resultat = []
    for s in donnees:
        nom = forme_normale(re.sub(r"\s*\(.*\)$", "", s["nom"]))
        formes = tuple(dict.fromkeys(f for f in [nom, *(forme_normale(x) for x in s["formes"])] if f))
        resultat.append(Objet("site", s["nom"], s["url"], s["url"], formes))
    return resultat


def objet_app(bundle_id: str, nom: str, chemin: str, connues: dict[str, dict] | None = None) -> Objet:
    """Une app : son nom affiché (français pour les apps Apple) et ses formes parlées."""
    connues = apps_connues() if connues is None else connues
    fiche = connues.get(bundle_id)
    affiche = fiche["nom"] if fiche else nom
    formes = formes_parlees(affiche) + formes_parlees(nom)
    if fiche:
        formes += [forme_normale(f) for f in fiche["formes"]]
    return Objet("app", affiche, chemin, bundle_id or chemin, tuple(dict.fromkeys(f for f in formes if f)))


DOSSIERS_COURANTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("Téléchargements", "~/Downloads", ("telechargements", "telechargement", "downloads", "mes telechargements")),
    ("Bureau", "~/Desktop", ("bureau", "desktop", "mon bureau")),
    ("Documents", "~/Documents", ("documents", "document", "mes documents")),
    ("Images", "~/Pictures", ("images", "image", "pictures", "mes images")),
    ("Musique (dossier)", "~/Music", ("dossier musique", "musique")),
    ("Films", "~/Movies", ("films", "videos", "movies", "mes videos", "mes films")),
    ("Applications", "/Applications", ("applications", "dossier applications", "mes applications")),
    ("Dossier personnel", "~", ("dossier personnel", "dossier de depart", "home", "mon dossier")),
    ("iCloud Drive", "~/Library/Mobile Documents/com~apple~CloudDocs", ("icloud", "icloud drive", "aille cloud")),
]
CLASSES = ("Classés", "~/Documents/Classés", ("classes", "mes documents classes", "dossier classes", "classe"))


def dossiers(maison: Path, existe: Callable[[Path], bool] = lambda p: p.is_dir()) -> list[Objet]:
    """Les dossiers courants (« Classés » seulement si le Trieur l'a créé : on regarde s'il existe, rien de plus)."""
    resultat = []
    for nom, chemin, formes in [*DOSSIERS_COURANTS, CLASSES]:
        reel = str(maison) + chemin[1:] if chemin.startswith("~") else chemin
        if (nom, chemin, formes) == CLASSES and not existe(Path(reel)):
            continue
        resultat.append(Objet("dossier", nom, reel, chemin, formes))
    return resultat
