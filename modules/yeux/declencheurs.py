"""Le détecteur de blocage, 100 % local : tant qu'il ne détecte rien, Claude n'est pas appelé.

Un « signal » (une erreur, un formulaire, une question) ne déclenche que s'il RESTE affiché
dans la même fenêtre assez longtemps : c'est le signe que tu bloques, pas que tu passes devant.
"""

import re
import time
from dataclasses import dataclass, field

from modules.yeux import parametres as p
from modules.yeux.filtres import _simple

ERREUR = re.compile(
    r"\b(error|erreur|exception|traceback|failed|failure|echec|echoue|impossible de|n'a pas pu|introuvable|"
    r"not found|no such file|permission denied|acces refuse|invalid|invalide|command not found|"
    r"syntaxerror|typeerror|valueerror|modulenotfounderror|fatal|ne repond pas|has crashed|a plante|"
    r"(?:erreur|error|code)\s*(?:404|500|403|401))\b"
)
FORMULAIRE = re.compile(
    r"\b(cerfa|formulaire|champ obligatoire|champs obligatoires|obligatoire|date de naissance|lieu de naissance|"
    r"numero fiscal|numero de securite sociale|piece justificative|justificatif|declaration|"
    r"etape \d+ (?:sur|/) ?\d+|case \d+[a-z]*|code postal|situation familiale|revenu fiscal)\b"
)
QUESTION = re.compile(r"^(question|exercice|qcm|cas pratique|enonce|quiz)\b|\?\s*$")
MARQUEURS_FORMULAIRE = 3  # au moins 3 indices différents pour parler de « formulaire »


@dataclass
class Declenchement:
    type: str  # erreur, formulaire, question, perso
    lignes: list[int]  # les lignes qui ont déclenché (pour l'extrait)


@dataclass
class _Suivi:
    depuis: float
    vu: float
    lignes: list[int] = field(default_factory=list)


def signaux(lignes: list[str], perso: list[str] | None = None) -> dict[tuple[str, str], list[int]]:
    """Les signaux visibles maintenant : {(type, empreinte) : numéros de lignes}."""
    trouves: dict[tuple[str, str], list[int]] = {}
    simples = [_simple(l) for l in lignes]
    for i, s in enumerate(simples):
        if ERREUR.search(s):
            trouves.setdefault(("erreur", s[:120]), []).append(i)
        if len(s.split()) >= 6 and QUESTION.search(s):
            trouves.setdefault(("question", s[:120]), []).append(i)
    indices = {m.group(1) for s in simples for m in FORMULAIRE.finditer(s)}
    if len(indices) >= MARQUEURS_FORMULAIRE:
        lignes_form = [i for i, s in enumerate(simples) if FORMULAIRE.search(s)]
        trouves[("formulaire", "|".join(sorted(indices))[:120])] = lignes_form[:12]
    for mot in perso or []:
        m = _simple(mot)
        if m:
            idx = [i for i, s in enumerate(simples) if m in s]
            if idx:
                trouves[("perso", m)] = idx[:6]
    return trouves


class Detecteur:
    def __init__(self):
        self.suivis: dict[tuple, _Suivi] = {}  # (fenêtre, type, empreinte) → depuis quand c'est affiché
        self.declenches: dict[tuple, float] = {}  # déjà proposé : pas de redite avant 30 min

    def analyser(self, cle_fenetre: str, lignes: list[str], perso: list[str] | None = None,
                 maintenant: float | None = None) -> list[Declenchement]:
        maintenant = time.time() if maintenant is None else maintenant
        presents = {(cle_fenetre, t, e): idx for (t, e), idx in signaux(lignes, perso).items()}
        for cle, idx in presents.items():
            suivi = self.suivis.get(cle)
            if suivi is None:
                self.suivis[cle] = _Suivi(maintenant, maintenant, idx)
            else:
                suivi.vu, suivi.lignes = maintenant, idx
        # Un signal qui n'est plus affiché depuis un moment repart de zéro.
        self.suivis = {c: s for c, s in self.suivis.items() if maintenant - s.vu <= p.OUBLI_SIGNAL}
        self.declenches = {c: t for c, t in self.declenches.items() if maintenant - t < p.REPOS_SIGNAL}

        resultat: list[Declenchement] = []
        for cle in presents:
            _, type_, _ = cle
            if cle in self.declenches or maintenant - self.suivis[cle].depuis < p.DELAIS[type_]:
                continue
            # Une erreur sur plusieurs lignes (Traceback… ValueError…) = UNE seule vérification :
            # toutes les lignes de ce type visibles maintenant sont traitées ensemble.
            memes = [c for c in presents if c[1] == type_]
            for c in memes:
                self.declenches[c] = maintenant
            resultat.append(Declenchement(type_, sorted({i for c in memes for i in presents[c]})))
        return resultat

    def en_cours(self, maintenant: float | None = None) -> list[tuple[str, int]]:
        """Pour le mode test : (type, secondes restantes avant déclenchement) des signaux suivis."""
        maintenant = time.time() if maintenant is None else maintenant
        return sorted({(cle[1], max(0, int(p.DELAIS[cle[1]] - (maintenant - s.depuis))))
                       for cle, s in self.suivis.items() if cle not in self.declenches})

    def oublier(self) -> None:
        """Tu t'absentes : rien de ce qui était affiché ne compte plus."""
        self.suivis.clear()


def lire_perso(fichier) -> list[str]:
    if not fichier.exists():
        return []
    return [l.strip() for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
