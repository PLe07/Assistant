"""Le registre des numéros et sites officiels (`sources.json`) : rien d'autre n'est jamais affiché.

Chaque numéro est écrit sur au moins une page officielle (URL dans `sources.json`). La revérification
(`verifier_en_ligne`) retélécharge ces pages sur le Mac et cherche le numéro et un mot-clé sur la page ; un numéro
qu'aucune de ses pages ne mentionne plus est signalé, puis retiré de la fiche urgence.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from bouclier import reseau

CHEMIN = Path(__file__).with_name("sources.json")


def chiffres(numero: str) -> str:
    return re.sub(r"\D", "", numero)


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    editeur: str


@dataclass(frozen=True)
class Numero:
    id: str
    numero: str
    libelle: str
    gratuit: bool
    mots: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Ressource:
    id: str
    adresse: str
    libelle: str
    mots: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Registre:
    verifie_le: str
    methode: str
    sources: dict[str, Source]
    numeros: tuple[Numero, ...]
    ressources: tuple[Ressource, ...]
    _par_id: dict[str, Numero | Ressource] = field(default_factory=dict, compare=False, repr=False)

    def elements(self) -> list[Numero | Ressource]:
        return [*self.numeros, *self.ressources]

    def element(self, ident: str) -> Numero | Ressource:
        return self._par_id[ident]

    def numero(self, ident: str) -> Numero:
        n = self._par_id[ident]
        assert isinstance(n, Numero)
        return n

    def chiffres_officiels(self) -> frozenset[str]:
        return frozenset(chiffres(n.numero) for n in self.numeros)

    def numeros_cites(self, texte: str) -> list[str]:
        """Les numéros de téléphone écrits dans un texte (4 chiffres et plus, ou les numéros courts du registre)."""
        trouves = []
        for m in re.finditer(r"(?<![\d*#])(?:\d[\s.]?){1,9}\d(?![\d#])", texte):
            c = chiffres(m.group(0))
            if len(c) >= 4 or c in self.chiffres_officiels():
                trouves.append(c)
        return trouves


@lru_cache(maxsize=1)
def charger(chemin: Path = CHEMIN) -> Registre:
    brut = json.loads(chemin.read_text(encoding="utf-8"))
    sources = {k: Source(k, v["url"], v["editeur"]) for k, v in brut["sources"].items()}
    numeros = tuple(
        Numero(n["id"], n["numero"], n["libelle"], bool(n["gratuit"]), tuple(n["mots"]), tuple(n["sources"]))
        for n in brut["numeros"]
    )
    ressources = tuple(
        Ressource(r["id"], r["adresse"], r["libelle"], tuple(r["mots"]), tuple(r["sources"]))
        for r in brut["ressources"]
    )
    registre = Registre(brut["verifie_le"], brut["methode"], sources, numeros, ressources)
    registre._par_id.update({e.id: e for e in registre.elements()})
    return registre


# --- Reverification sur les pages officielles -----------------------------------------------------------------------

Telecharger = Callable[..., reseau.Reponse]


def texte_de_page(corps: bytes) -> str:
    """Le texte d'une page : balises retirées, entités décodées, espaces (dont insécables) uniformes."""
    t = corps.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[\s  ]+", " ", t).lower()


def page_mentionne(texte_page: str, element: Numero | Ressource) -> bool:
    mots_ok = all(m.lower() in texte_page for m in element.mots)
    if isinstance(element, Ressource):
        return mots_ok
    cible = chiffres(element.numero)
    compact = re.sub(r"(?<=\d)[ .\-](?=\d)", "", texte_page)
    return mots_ok and re.search(rf"(?<!\d){cible}(?!\d)", compact) is not None


@dataclass
class Reverification:
    confirmes: list[str]  # identifiants confirmés par au moins une page
    absents: list[str]  # pages lues, mais le numéro n'y figure plus nulle part
    injoignables: list[str]  # aucune page lisible (réseau) : dernière vérification conservée
    pages_lues: int


def verifier_en_ligne(registre: Registre, telecharger: Telecharger = reseau.telecharger) -> Reverification:
    cache: dict[str, str | None] = {}

    def lire(source_id: str) -> str | None:
        if source_id not in cache:
            try:
                r = telecharger(registre.sources[source_id].url, delai=20, max_octets=5_000_000)
                cache[source_id] = texte_de_page(r.corps) if r.statut == 200 else None
            except (reseau.ErreurReseau, reseau.HoteInterdit):
                cache[source_id] = None
        return cache[source_id]

    resultat = Reverification([], [], [], 0)
    for element in registre.elements():
        textes = [t for t in (lire(s) for s in element.sources) if t is not None]
        if not textes:
            resultat.injoignables.append(element.id)
        elif any(page_mentionne(t, element) for t in textes):
            resultat.confirmes.append(element.id)
        else:
            resultat.absents.append(element.id)
    resultat.pages_lues = sum(1 for t in cache.values() if t is not None)
    return resultat
