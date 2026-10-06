"""L'émetteur d'un document : d'abord la base (emetteurs.json, et emetteurs_perso.json), sinon le haut du document.

Où le nom compte :
- en haut du document (les premières lignes : l'en-tête, le logo lu par l'OCR) ;
- son site web (« www.fnac.com », « amazon.fr »), où qu'il soit ;
- ailleurs dans le texte, un peu (un relevé cite « CB CARREFOUR », une facture « Casque Sony » : l'en-tête gagne).
Un nom courant (« orange », « free », « but ») ne compte qu'en haut ou par son site (« strict »).

Sans émetteur connu, c'est la première ligne de l'en-tête qui ressemble à un nom (pas un titre, une adresse, une
date ni un numéro).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from modules.trieur.classement.texte import normaliser

BASE = Path(__file__).with_name("emetteurs.json")
HAUT = 6  # les lignes de l'en-tête


@dataclass(frozen=True)
class Emetteur:
    nom: str
    categorie: str
    motifs: tuple[str, ...]
    domaines: tuple[str, ...] = ()
    strict: bool = False
    poids: float = 1.0
    motif: re.Pattern[str] = field(default=re.compile("(?!)"), compare=False)


@dataclass(frozen=True)
class EmetteurTrouve:
    nom: str
    categorie: str | None  # None : inconnu de la base
    score: float
    source: str  # « en-tête », « site », « texte », « première ligne »

    @property
    def connu(self) -> bool:
        return self.categorie is not None


def _motif(motifs: tuple[str, ...]) -> re.Pattern[str]:
    variantes = sorted({m.strip() for m in motifs if m.strip()}, key=len, reverse=True)
    corps = "|".join(re.escape(v).replace(r"\ ", r"[\s.\-]*") for v in variantes)
    return re.compile(rf"(?<![a-z0-9])(?:{corps})(?![a-z0-9])")


def _depuis(d: dict[str, Any]) -> Emetteur:
    motifs = tuple(normaliser(m) for m in d.get("motifs", [])) or (normaliser(d["nom"]),)
    return Emetteur(
        nom=d["nom"],
        categorie=d.get("categorie", "autre"),
        motifs=motifs,
        domaines=tuple(x.lower() for x in d.get("domaines", [])),
        strict=bool(d.get("strict", False)),
        poids=float(d.get("poids", 1.0)),
        motif=_motif(motifs),
    )


@lru_cache(maxsize=4)
def charger(perso: Path | None = None) -> tuple[Emetteur, ...]:
    """La base embarquée, puis les tiens (emetteurs_perso.json) qui la complètent ou la remplacent par nom."""
    donnees = json.loads(BASE.read_text(encoding="utf-8"))["emetteurs"]
    if perso is not None and perso.exists():
        try:
            ajouts = json.loads(perso.read_text(encoding="utf-8")).get("emetteurs", [])
        except (OSError, ValueError, AttributeError):
            ajouts = []
        noms = {a.get("nom") for a in ajouts if isinstance(a, dict)}
        donnees = [d for d in donnees if d["nom"] not in noms] + [
            a for a in ajouts if isinstance(a, dict) and a.get("nom")
        ]
    return tuple(_depuis(d) for d in donnees)


def _domaine(e: Emetteur, texte: str) -> bool:
    return any(re.search(rf"(?<![a-z0-9\-]){re.escape(d)}(?![a-z0-9\-])", texte) for d in e.domaines)


def trouver(texte: str, base: tuple[Emetteur, ...] | None = None, moi: str = "") -> EmetteurTrouve | None:
    """Le meilleur émetteur de la base, sinon le nom lu en haut. « moi » : ton nom, jamais pris pour l'émetteur."""
    base = base if base is not None else charger()
    lignes = [li for li in normaliser(texte).splitlines() if li.strip()]
    haut = lignes[:HAUT]
    plat = "\n".join(lignes)
    meilleur: tuple[float, Emetteur, str] | None = None
    for e in base:
        score, source = 0.0, ""
        for i, ligne in enumerate(haut):
            if e.motif.search(ligne):
                score, source = 10.0 - i, "en-tête"
                break
        if _domaine(e, plat):
            score, source = max(score, 6.0) + 1.0, source or "site"
        if not e.strict:
            reste = sum(1 for ligne in lignes[HAUT:] if e.motif.search(ligne))
            if reste:
                score += min(reste, 3)
                source = source or "texte"
        score *= e.poids
        seuil = 3 * e.poids if e.poids < 1 else 3  # un émetteur générique : dès qu'il est en haut
        if score >= seuil and score > 0 and (meilleur is None or score > meilleur[0]):
            meilleur = (score, e, source)
    if meilleur is not None:
        return EmetteurTrouve(meilleur[1].nom, meilleur[1].categorie, meilleur[0], meilleur[2])
    nom = premiere_ligne(texte, moi)
    return EmetteurTrouve(nom, None, 1.0, "première ligne") if nom else None


# Ce qui n'est pas un nom d'émetteur : les titres de documents, les adresses, les dates, les numéros.
_PAS_UN_NOM = re.compile(
    r"^(facture|devis|ticket|recu|releve|avis|attestation|quittance|contrat|bail|bulletin|certificat|notice|"
    r"ordonnance|carte|passeport|permis|confirmation|votre|objet|madame|monsieur|date|le |page|tel|telephone|"
    r"service|direction|republique|liberte|siret|siren|tva|n°|no |www\.|http|e-billet|conditions|decompte|"
    r"[a-z]+, le |document|copie|duplicata|original|merci|bienvenue|caisse|client|nom\b|nom:|prenoms?\b|"
    r"adresse|ne\(?e?\)? le|numero|reference|periode)"
)
_ADRESSE = re.compile(
    r"^\d{1,4}(?: ?(?:bis|ter))?,? (?:rue|avenue|av\.|boulevard|bd|place|chemin|allee|impasse|quai|route|cours)\b|"
    r"\b\d{5}\b|\bcedex\b|\bbp \d|\btsa \d|@|\+33|\b0\d(?:[ .]?\d\d){4}\b"
)


def premiere_ligne(texte: str, moi: str = "") -> str | None:
    """Le nom écrit en haut du document, tel quel (avec ses accents), mis en forme : « FNAC » → « Fnac »."""
    moi_n = normaliser(moi)
    for brute in [li.strip() for li in texte.splitlines() if li.strip()][:4]:
        brute = _premier_morceau(brute)
        n = normaliser(brute)
        lettres = re.sub(r"[^a-z]", "", n)
        if len(lettres) < 2 or _PAS_UN_NOM.match(n) or _ADRESSE.search(n) or re.search(r"\d{2}[/.\-]\d{2}", n):
            continue
        if moi_n and (moi_n in n or n in moi_n):
            continue
        if sum(c.isdigit() for c in brute) > len(brute) / 3:
            continue
        return mise_en_forme(brute)
    return None


_LIENS = {"de", "du", "des", "d'", "la", "le", "les", "&", "et", "l'", "sur", "en"}


def _premier_morceau(ligne: str) -> str:
    """Le premier bloc de la ligne (avant la colonne suivante), en recollant les mots d'un nom écrit en grand
    (« Mairie  de  Rezé », « Université de  Bordeaux ») : deux blocs sont un seul nom s'ils sont liés par
    « de », « du », « & »…"""
    blocs = [b.strip() for b in re.split(r"\s{2,}|·", ligne) if b.strip()]
    if not blocs:
        return ""
    nom = blocs[0]
    for b in blocs[1:]:
        dernier = normaliser(nom).split()[-1] if nom.split() else ""
        premier = normaliser(b).split()[0]
        if dernier in _LIENS or premier in _LIENS:
            nom = f"{nom} {b}"
        else:
            break
    return nom.strip(" -:|")


_PETITS_MOTS = {"de", "du", "des", "la", "le", "les", "et", "au", "aux", "en", "sur", "mon", "ma", "mes", "un", "une",
                "chez", "son", "sa", "ses", "nos", "vos", "l", "d", "a"}  # fmt: skip


def mise_en_forme(nom: str) -> str:
    """Un nom tout en capitales devient « Fnac » ; un sigle court (HP, LG, JBL, EDF) reste en capitales."""
    nom = re.sub(r"\s+", " ", nom).strip()[:60]
    nom = re.sub(r"(?<=[a-zà-ÿ]{2})(?=[A-ZÀ-Ý])", " ", nom)  # les mots collés par l'OCR : « BackMarket »
    if nom.isupper():
        mots = []
        for i, m in enumerate(nom.split(" ")):
            nu = re.sub(r"[^A-Za-zÀ-ÿ]", "", m).lower()
            if nu in _PETITS_MOTS:
                mots.append(m.lower() if i else m.capitalize())
            else:
                mots.append(m if len(nu) <= 3 else m.capitalize())  # un sigle (HP, SFR) reste en capitales
        return " ".join(mots)
    return nom


def cle(nom: str) -> str:
    """Pour comparer deux noms : « Leroy-Merlin » = « LEROY MERLIN »."""
    return re.sub(r"[^a-z0-9]", "", normaliser(nom))
