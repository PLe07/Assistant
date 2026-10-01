"""Le détecteur d'intention, 100 % local : tant qu'il ne détecte rien, Claude n'est pas appelé.

Deux façons de déclencher :
- le mot d'appel en début de phrase (« Assistant, c'est quoi l'IFI ? ») ;
- en mode « passif », une tournure de besoin, de question ou d'oubli (« il faut que je… »).
"""

import re
import time
from dataclasses import dataclass

MOTIFS = [
    ("besoin", r"\b(il )?faut (absolument |vraiment |encore )?que j"),
    ("besoin", r"\bje dois\b"),
    ("besoin", r"\bj'ai besoin d"),
    ("besoin", r"\bil (me )?faudrait\b"),
    ("besoin", r"\bil faudra que j"),
    ("besoin", r"\bje devrais\b"),
    ("question", r"\bc'est quoi (déjà|deja)\b"),
    ("question", r"\bcomment (est-ce qu'|est ce qu')?(on|je|j') ?(fait|fais|peux|pourrais|dois|vais) (pour|faire)\b"),
    ("question", r"\bcomment (ça|ca) marche\b"),
    ("question", r"\bje (ne )?sais (pas|plus) (comment|quoi|où|ou|si|pourquoi)\b"),
    ("question", r"\b(ça|ca) veut dire quoi\b"),
    ("question", r"\bqu'est-ce que (c'est|ça veut dire|ca veut dire)\b"),
    ("oubli", r"\bje (ne )?(me )?(souviens|rappelle) (pas|plus)\b"),
    ("oubli", r"\bj'ai oublié\b"),
    ("oubli", r"\bc'est quand (déjà|deja)\b"),
    ("rappel", r"\b(rappelle|rappelez)[- ]moi\b"),
    ("rappel", r"\bn'oublie pas de\b"),
    ("rappel", r"\bpense à\b"),
]
_MOTIFS = [(t, re.compile(m, re.I)) for t, m in MOTIFS]
DELAI_REPETITION = 600  # la même phrase ne redéclenche pas avant 10 min


@dataclass
class Declenchement:
    type: str  # mot_appel, besoin, question, oubli, rappel, perso
    phrase: str


def normaliser(texte: str) -> str:
    texte = texte.replace("’", "'").replace("`", "'").lower()
    return re.sub(r"\s+", " ", texte).strip()


class Detecteur:
    def __init__(self):
        self.vues: dict[str, float] = {}

    def analyser(self, phrase: str, mode: str = "passif", mot_appel: str = "assistant",
                 perso: list[str] | None = None) -> Declenchement | None:
        norm = normaliser(phrase)
        maintenant = time.time()
        self.vues = {k: t for k, t in self.vues.items() if maintenant - t < DELAI_REPETITION}
        if not norm or norm in self.vues:
            return None

        trouve = None
        appel = re.match(rf"^\W*(?:hey |ok |dis |eh )?{re.escape(normaliser(mot_appel))}\b[\s,!.?:]*(.*)$", norm) if mot_appel else None
        if appel and len(appel.group(1).split()) >= 2:
            trouve = Declenchement("mot_appel", phrase)
        elif mode == "passif" and len(norm.split()) >= 4:
            for type_, motif in _MOTIFS:
                if motif.search(norm):
                    trouve = Declenchement(type_, phrase)
                    break
            else:
                for ligne in perso or []:
                    if normaliser(ligne) and normaliser(ligne) in norm:
                        trouve = Declenchement("perso", phrase)
                        break
        if trouve:
            self.vues[norm] = maintenant
        return trouve


def retirer_mot_appel(phrase: str, mot_appel: str = "assistant") -> str:
    """« Assistant, rappelle-moi… » → « rappelle-moi… » (ta demande, sans le mot d'appel)."""
    texte = " ".join((phrase or "").replace("’", "'").split())
    if not mot_appel:
        return texte
    return re.sub(rf"^\W*(?:hey |ok |dis |eh )?{re.escape(mot_appel)}\b[\s,!.?:]*", "", texte, count=1, flags=re.I) or texte


def lire_perso(fichier) -> list[str]:
    if not fichier.exists():
        return []
    return [l.strip() for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
