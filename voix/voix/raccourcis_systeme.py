"""Le raccourci clavier global de Voix, et les raccourcis du système qu'il ne doit pas voler (§1.2).

- Une **combinaison** s'écrit `ctrl+option+espace` (ou `⌃⌥Espace`) : modificateurs `ctrl`, `option`, `cmd`, `shift`,
  plus une touche : `espace`, une lettre (mêmes positions sur un clavier AZERTY et QWERTY : B C D E F G H I J K L N O
  P R S T U V X Y) ou `f1` à `f12`.
- Les raccourcis du système sont lus dans l'export **en lecture seule** de `com.apple.symbolichotkeys`
  (`defaults export com.apple.symbolichotkeys -`). Une entrée absente de l'export garde sa valeur d'usine : les quatre
  raccourcis d'usine sur la barre d'espace (⌃Espace, ⌃⌥Espace : sources de saisie ; ⌘Espace : Spotlight ; ⌥⌘Espace :
  recherche du Finder) sont donc comptés comme pris tant que l'export ne dit pas qu'ils sont désactivés.
- Voix ne modifie jamais ces réglages : si ⌃⌥Espace est pris, il choisit le candidat libre suivant (D-08).
"""

from __future__ import annotations

import plistlib
from collections.abc import Iterable
from dataclasses import dataclass

# Masques des modificateurs dans com.apple.symbolichotkeys (ceux de CGEventFlags).
MASQUE_EXPORT = {"shift": 1 << 17, "ctrl": 1 << 18, "option": 1 << 19, "cmd": 1 << 20}
MASQUE_FN = 1 << 23  # « touche de fonction » (F1…F12, flèches) : ne change pas la combinaison
# Masques Carbon (RegisterEventHotKey) : cmdKey, shiftKey, optionKey, controlKey.
MASQUE_CARBON = {"cmd": 256, "shift": 512, "option": 2048, "ctrl": 4096}
ORDRE = ("ctrl", "option", "shift", "cmd")
SYMBOLES = {"ctrl": "⌃", "option": "⌥", "shift": "⇧", "cmd": "⌘"}
SYNONYMES_MODIFICATEURS = {
    "ctrl": "ctrl", "control": "ctrl", "controle": "ctrl", "contrôle": "ctrl", "⌃": "ctrl",
    "option": "option", "alt": "option", "opt": "option", "⌥": "option",
    "cmd": "cmd", "command": "cmd", "commande": "cmd", "⌘": "cmd",
    "shift": "shift", "maj": "shift", "majuscule": "shift", "⇧": "shift",
}  # fmt: skip

# Codes de touche virtuels (positions physiques). Seules les lettres à la même place en AZERTY et en QWERTY.
TOUCHES = {
    "espace": 49,
    "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37, "n": 45, "o": 31,
    "p": 35, "r": 15, "s": 1, "t": 17, "u": 32, "v": 9, "x": 7, "y": 16,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
    "f11": 103, "f12": 111,
}  # fmt: skip
NOMS_TOUCHES = {code: nom for nom, code in TOUCHES.items()}
SYNONYMES_TOUCHES = {"space": "espace", "spacebar": "espace", "barre d'espace": "espace"}

# Valeurs d'usine des raccourcis du système qui touchent la barre d'espace ou nos candidats (id → touche, masque).
USINE: dict[int, tuple[int, int]] = {
    60: (49, MASQUE_EXPORT["ctrl"]),  # source de saisie précédente
    61: (49, MASQUE_EXPORT["ctrl"] | MASQUE_EXPORT["option"]),  # source de saisie suivante
    64: (49, MASQUE_EXPORT["cmd"]),  # Spotlight
    65: (49, MASQUE_EXPORT["cmd"] | MASQUE_EXPORT["option"]),  # recherche du Finder
}
NOMS_USINE = {
    60: "sélectionner la source de saisie précédente",
    61: "sélectionner la source de saisie suivante",
    64: "Spotlight",
    65: "fenêtre de recherche du Finder",
}

CANDIDATS = ("ctrl+option+espace", "ctrl+option+cmd+espace", "ctrl+shift+espace", "ctrl+option+v")


class CombinaisonInvalide(ValueError):
    """Une combinaison illisible ou refusée (pas de modificateur, touche inconnue)."""


@dataclass(frozen=True, order=True)
class Combinaison:
    touche: int
    modificateurs: frozenset[str]

    @classmethod
    def lire(cls, texte: str) -> Combinaison:
        brut = texte.strip().lower()
        for symbole, nom in (("⌃", "ctrl+"), ("⌥", "option+"), ("⇧", "shift+"), ("⌘", "cmd+")):
            brut = brut.replace(symbole, nom)
        morceaux = [m.strip() for m in brut.replace("-", "+").split("+") if m.strip()]
        if not morceaux:
            raise CombinaisonInvalide("combinaison vide")
        *mods, touche = morceaux
        touche = SYNONYMES_TOUCHES.get(touche, touche)
        if touche not in TOUCHES:
            raise CombinaisonInvalide(f"touche inconnue : {touche!r} (espace, une lettre, ou f1 à f12)")
        noms = set()
        for m in mods:
            if m not in SYNONYMES_MODIFICATEURS:
                raise CombinaisonInvalide(f"modificateur inconnu : {m!r} (ctrl, option, cmd, shift)")
            noms.add(SYNONYMES_MODIFICATEURS[m])
        if not noms & {"ctrl", "option", "cmd"}:
            # Une lettre seule ou avec ⇧ taperait du texte partout : refusé.
            raise CombinaisonInvalide("il faut au moins ⌃, ⌥ ou ⌘ dans la combinaison")
        return cls(TOUCHES[touche], frozenset(noms))

    @classmethod
    def depuis_export(cls, touche: int, masque: int) -> Combinaison:
        mods = frozenset(nom for nom, bit in MASQUE_EXPORT.items() if masque & bit)
        return cls(touche, mods)

    @property
    def nom_touche(self) -> str:
        return NOMS_TOUCHES.get(self.touche, f"touche {self.touche}")

    def texte(self) -> str:
        """« ctrl+option+espace » : la forme des réglages."""
        return "+".join([m for m in ORDRE if m in self.modificateurs] + [self.nom_touche])

    def symboles(self) -> str:
        """« ⌃⌥Espace » : la forme affichée."""
        touche = self.nom_touche
        touche = "Espace" if touche == "espace" else touche.upper()
        return "".join(SYMBOLES[m] for m in ORDRE if m in self.modificateurs) + touche

    def masque_carbon(self) -> int:
        return sum(MASQUE_CARBON[m] for m in self.modificateurs)


@dataclass(frozen=True)
class RaccourciSysteme:
    ident: int
    combinaison: Combinaison
    actif: bool
    source: str  # « export » ou « usine »

    @property
    def nom(self) -> str:
        return NOMS_USINE.get(self.ident, f"raccourci du système n°{self.ident}")


def lire_export(donnees: bytes) -> list[RaccourciSysteme]:
    """Les raccourcis du système, d'après l'export (XML ou binaire) ; les entrées absentes gardent leur valeur
    d'usine. Un export illisible lève ValueError (on ne devine pas)."""
    try:
        racine = plistlib.loads(donnees)
    except Exception as e:  # noqa: BLE001 - plistlib lève des erreurs variées
        raise ValueError(f"export des raccourcis illisible ({e.__class__.__name__})") from e
    if not isinstance(racine, dict):
        raise ValueError("export des raccourcis illisible (pas un dictionnaire)")
    brutes = racine.get("AppleSymbolicHotKeys", {})
    if not isinstance(brutes, dict):
        brutes = {}
    resultat: dict[int, RaccourciSysteme] = {}
    for cle, entree in brutes.items():
        try:
            ident = int(cle)
        except (TypeError, ValueError):
            continue
        if not isinstance(entree, dict):
            continue
        actif = bool(entree.get("enabled", False))
        valeur = entree.get("value")
        params = valeur.get("parameters") if isinstance(valeur, dict) else None
        if isinstance(params, list) and len(params) == 3 and all(isinstance(p, int) for p in params):
            combi = Combinaison.depuis_export(params[1], params[2] & ~MASQUE_FN)
        elif ident in USINE:
            combi = Combinaison.depuis_export(*USINE[ident])
        else:
            continue
        resultat[ident] = RaccourciSysteme(ident, combi, actif, "export")
    for ident, (touche, masque) in USINE.items():
        if ident not in resultat:
            resultat[ident] = RaccourciSysteme(ident, Combinaison.depuis_export(touche, masque), True, "usine")
    return sorted(resultat.values(), key=lambda r: r.ident)


def pris(raccourcis: Iterable[RaccourciSysteme]) -> dict[Combinaison, RaccourciSysteme]:
    return {r.combinaison: r for r in raccourcis if r.actif}


def choisir(
    raccourcis: Iterable[RaccourciSysteme], candidats: Iterable[str] = CANDIDATS
) -> tuple[Combinaison, list[str]]:
    """Le premier candidat libre, et pourquoi les précédents ont été écartés."""
    occupes = pris(raccourcis)
    ecartes: list[str] = []
    for texte in candidats:
        combi = Combinaison.lire(texte)
        if combi in occupes:
            ecartes.append(f"{combi.symboles()} est pris par macOS ({occupes[combi].nom})")
            continue
        return combi, ecartes
    raise CombinaisonInvalide("aucun raccourci candidat n'est libre : choisis-en un dans reglages.toml")


def conflit(combi: Combinaison, raccourcis: Iterable[RaccourciSysteme]) -> str | None:
    """Le nom du raccourci du système déjà sur cette combinaison, ou None."""
    r = pris(raccourcis).get(combi)
    return r.nom if r is not None else None
