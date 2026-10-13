"""Mettre une phrase transcrite sous une forme stable avant de la comprendre.

« Tu peux mettre le volume à trente pour cent, s'il te plaît ? » → `mettre le volume a 30 pourcent`.

- minuscules, apostrophes et traits d'union → espaces (« l'app » → `l app`, « rappelle-moi » → `rappelle moi`) ;
- ponctuation retirée ; `%` et « pour cent » → `pourcent` ; « 1h30 » → `1 h 30` ;
- deux versions de chaque mot, alignées : **avec** accents (pour les textes libres : une recherche, un rappel) et
  **sans** accents (pour reconnaître : la transcription met ou oublie des accents) ;
- nombres en lettres → chiffres ;
- politesse et hésitations retirées (« est-ce que tu peux », « s'il te plaît », « euh », « hey Jarvis ») ;
- **négation** repérée (« ne ferme pas Safari ») : une phrase négative ne déclenche jamais d'action.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from voix.nlu import nombres

LONGUEUR_MAX = 300  # caractères : au-delà, ce n'est pas une commande

_PONCTUATION = re.compile(r"[,!?;:«»\"“”„()\[\]{}…/\\*_+=<>|~^`¿¡•·]")
_POINT = re.compile(r"(?<!\d)\.|\.(?!\d)")  # un point, sauf entre deux chiffres (« 1.5 »)
_APOSTROPHES = re.compile(r"[’‘´`ʼ']")
_TIRETS = re.compile(r"[-‐‑‒–—]")
_POURCENT_COLLE = re.compile(r"(\d)\s*%")
_HEURE_COLLEE = re.compile(r"\b(\d{1,2})\s*h\s*(\d{2})\b")
_UNITE_COLLEE = re.compile(r"\b(\d+)(h|min|mn|s|sec|minutes?|secondes?|heures?)\b")
_DECIMAL = re.compile(r"(\d),(\d)")

# Retirés n'importe où (suites de mots, sans accents).
POLITESSE_PARTOUT = [
    "s il te plait", "s il vous plait", "si il te plait", "s te plait", "ste plait", "steuple", "steuplait",
    "stp", "svp", "please", "euh", "heu", "hum", "hmm", "bah", "attends", "attend", "genre", "tu vois", "en fait",
    "du coup", "voyons", "bref", "comment ca s appelle", "comment dire",
]  # fmt: skip
# Retirés en fin de phrase seulement (« traduis merci en anglais » garde son « merci »).
POLITESSE_FIN = ["merci beaucoup", "merci bien", "merci", "voila", "c est tout", "allez", "vas y", "hop", "alors"]
# L'oral : « tu me lances Spotify », « on met le volume à 35 », « coupe-moi le son », « ouvre donc Safari ».
SUJETS = {"tu", "on", "vous", "nous"}
CLITIQUES = {"me", "m", "nous", "te", "t"}
APRES_VERBE = {"moi", "nous", "vite", "donc", "rapidement", "completement", "direct", "directement", "juste",
               "simplement", "doucement"}  # fmt: skip
# Après ces verbes vient un texte libre (« traduis nous restons… ») : rien n'y est retiré.
VERBES_TEXTE_LIBRE = {"traduis", "traduire", "cherche", "chercher", "recherche", "google", "googlise", "tape"}
AUXILIAIRES = {
    "est", "es", "as", "a", "sommes", "etes", "avez", "sont", "ont", "avons", "peut", "peux", "sais", "fais", "connais",
    "aurais", "aurait", "auriez",
}  # fmt: skip
PRONOMINAUX = {"concentrer", "concentre", "reposer", "detendre", "calmer", "reveiller", "coucher"}
# Après ces verbes, « moi » porte le sens (« rappelle-moi », « aide-moi », « donne-moi l'heure ») : on le garde,
# et le pronom d'avant aussi (« tu me rappelles dans 10 minutes »).
GARDE_MOI = {
    "rappelle", "rappelles", "rappeler", "rappelez", "previens", "prevenir", "alerte", "fais", "parle", "aide",
    "donne", "dis", "dites",
}  # fmt: skip
# Compléments en fin de phrase qui n'ajoutent rien à l'ordre (les plus longs d'abord).
FINS_SUPERFLUES = [f.split() for f in (
    "de l ordinateur", "sur l ordinateur", "de mon ordinateur", "de mon mac", "sur mon mac", "de l ordi",
    "sur l ordi", "du mac", "sur le mac", "un petit moment", "tout de suite", "vite", "rapidement", "maintenant",
    "un moment", "un instant", "2 secondes",
    "quelques instants", "pour l instant", "doucement", "en fond", "en arriere plan",
)]  # fmt: skip
INFINITIFS_APRES_FAIS = {"demarrer", "ouvrir", "lancer", "jouer", "partir", "tourner", "marcher", "apparaitre"}
# Retirés en tête de phrase (répété tant que ça change : « ok euh est-ce que tu peux… »).
POLITESSE_DEBUT = [
    "hey jarvis", "he jarvis", "eh jarvis", "hey jarvi", "hei jarvis", "jarvis", "dis voix", "voix",
    "est ce que tu pourrais", "est ce que tu peux", "est ce que vous pouvez", "est ce que vous pourriez",
    "est ce que tu veux bien", "est ce que tu voudrais", "est ce que tu", "est ce qu on peut",
    "tu pourrais", "tu peux", "tu veux bien", "tu voudrais bien", "tu voudrais", "peux tu", "pourrais tu",
    "vous pouvez", "pouvez vous", "pourriez vous", "voudrais tu", "veux tu",
    "je voudrais que tu", "j aimerais que tu", "je veux que tu", "j ai besoin que tu", "il faut que tu",
    "il faudrait que tu", "faudrait que tu", "fais moi le plaisir de", "merci de", "essaie de", "essaye de",
    "je voudrais", "j aimerais", "je veux", "je souhaite", "on peut", "on va", "vas y", "allez",
    "allez hop", "hop", "ok", "okay", "bon", "alors", "ben", "oh", "he", "eh", "hey", "hello", "salut", "bonjour",
    "coucou",
    "dis moi", "dites moi", "dis",
    "tu vas", "il faudrait", "il faut", "faudrait", "faut", "j ai envie d", "j ai envie de", "sois gentil et",
    "sois sympa et", "sois gentil", "sois sympa", "tu serais gentil de", "ca te derange de",
    "j aimerais savoir", "je veux savoir", "je voudrais savoir", "tu peux me dire", "tu pourrais me dire",
    "peux tu me dire", "pourrais tu me dire", "je dois", "il faut que j", "faut que j", "c est bon", "pardon", "vite",
]  # fmt: skip
# Ceux-là font de la suite une question (« dis-moi le volume » = « quel est le volume »).
QUESTIONS_DEBUT = {
    "dis moi", "dites moi", "dis", "est ce que tu", "j aimerais savoir", "je veux savoir", "je voudrais savoir",
    "tu peux me dire", "tu pourrais me dire", "peux tu me dire", "pourrais tu me dire",
}  # fmt: skip
# Ceux-là disent une envie (« j'ai envie de musique » = « mets de la musique »).
ENVIES_DEBUT = {"j ai envie de", "j ai envie d", "j aimerais", "je voudrais", "je veux", "je souhaite"}
# Réécritures (partout, avant de chercher une négation) : la même demande, dite autrement.
REECRITURES = [
    ("tout ce qui n est pas", "tout sauf"), ("tout ce qui est pas", "tout sauf"), ("a l exception de", "sauf"),
    ("a l exception d", "sauf"), ("mais garde", "sauf"), ("wi fi", "wifi"),
    ("n oublie pas de me rappeler", "rappelle moi"), ("oublie pas de me rappeler", "rappelle moi"),
    ("n oublie pas de me dire", "rappelle moi"), ("oublie pas de me dire", "rappelle moi"),
    ("allez sur", "va sur"), ("allez dans", "va dans"), ("allez voir", "va voir"),
    ("point fr", ""), ("point com", ""), ("point org", ""), ("point net", ""), ("point gouv", ""),
]  # fmt: skip
NEGATIONS_FIN = {"pas", "jamais", "plus", "rien", "point"}


def sans_accents(texte: str) -> str:
    texte = texte.replace("œ", "oe").replace("æ", "ae").replace("ß", "ss").replace("Œ", "oe").replace("Æ", "ae")
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


@dataclass
class Phrase:
    brut: str
    jetons: list[str] = field(default_factory=list)  # minuscules, accents gardés
    cles: list[str] = field(default_factory=list)  # minuscules, sans accents : ce qu'on reconnaît
    negation: bool = False
    trop_longue: bool = False
    question: bool = False  # « dis-moi… », « tu sais… » : une question, même sans mot interrogatif
    envie: bool = False  # « j'ai envie de… », « je voudrais… » : une demande

    @property
    def texte(self) -> str:
        return " ".join(self.cles)

    @property
    def texte_accentue(self) -> str:
        return " ".join(self.jetons)

    def extrait(self, debut: int, fin: int) -> str:
        """Le texte accentué qui correspond à `texte[debut:fin]` (positions dans la forme sans accents)."""
        morceaux: list[str] = []
        position = 0
        for jeton, cle in zip(self.jetons, self.cles, strict=True):
            if position >= debut and position + len(cle) <= fin:
                morceaux.append(jeton)
            position += len(cle) + 1
        return " ".join(morceaux)


def _remplacer_suites(paires: list[tuple[str, str]], suites: list[list[str]], seulement_debut: bool) -> bool:
    """Retire les suites de clés données (au début seulement, ou partout). Vrai si quelque chose a changé."""
    change = False
    for suite in suites:
        n = len(suite)
        if seulement_debut:
            if [c for _, c in paires[:n]] == suite and len(paires) > n:
                del paires[:n]
                return True
            continue
        i = 0
        while i + n <= len(paires):
            if [c for _, c in paires[i : i + n]] == suite:
                del paires[i : i + n]
                change = True
            else:
                i += 1
    return change


def _reecrire(paires: list[tuple[str, str]]) -> None:
    """Les réécritures (« tout ce qui n'est pas X » → « tout sauf X ») et les mots répétés (« ouvre ouvre »)."""
    for avant, apres in REECRITURES:
        suite, nouveau = avant.split(), [(m, m) for m in apres.split()]
        n = len(suite)
        i = 0
        while i + n <= len(paires):
            if [c for _, c in paires[i : i + n]] == suite:
                paires[i : i + n] = nouveau
                i += len(nouveau) or 1
            else:
                i += 1
    i = 1
    while i < len(paires):
        if paires[i][1] == paires[i - 1][1] and len(paires[i][1]) >= 4 and not paires[i][1].isdigit():
            del paires[i]
        else:
            i += 1


def _negative(cles: list[str]) -> bool:
    """« ne ferme pas », « n'ouvre jamais », « surtout pas le son » : une négation verbale."""
    for i, mot in enumerate(cles):
        if mot in ("ne", "n") and any(c in NEGATIONS_FIN for c in cles[i + 1 : i + 5]):
            return True
    if len(cles) > 1 and cles[1] in ("pas", "jamais") and cles[0] not in ("ne", "n", "surtout"):
        return True  # l'oral sans « ne » : « ferme pas Safari », « cherche pas »
    if len(cles) > 1 and cles[0] == "surtout" and "pas" in cles[1:3]:
        return True  # « surtout pas le son »
    return (
        len(cles) > 1 and cles[0] == "pas" and cles[1] in ("le", "la", "les", "l", "de", "d", "ca", "ce", "maintenant")
    )


def normaliser(brut: str) -> Phrase:
    phrase = Phrase(brut=brut)
    texte = unicodedata.normalize("NFC", brut or "").strip()
    if len(texte) > LONGUEUR_MAX:
        phrase.trop_longue = True
        return phrase
    texte = texte.lower()
    texte = _APOSTROPHES.sub(" ", texte)
    texte = _TIRETS.sub(" ", texte)
    texte = _DECIMAL.sub(r"\1.\2", texte)
    texte = _POURCENT_COLLE.sub(r"\1 pourcent ", texte).replace("%", " pourcent ")
    texte = _HEURE_COLLEE.sub(r"\1 h \2", texte)
    texte = _UNITE_COLLEE.sub(r"\1 \2", texte)
    texte = _PONCTUATION.sub(" ", texte)
    texte = _POINT.sub(" ", texte)
    paires = [(j, sans_accents(j)) for j in texte.split()]
    # « trente pour cent » → « trente pourcent » (avant les nombres : « cent » ne doit pas devenir 100).
    i = 1
    while i + 1 < len(paires):
        precedent = paires[i - 1][1]
        if (
            paires[i][1] == "pour"
            and paires[i + 1][1] in ("cent", "sang", "sans")
            and (precedent.isdigit() or precedent in nombres.MOTS)
        ):
            paires[i : i + 2] = [("pourcent", "pourcent")]
        i += 1
    # Nombres en lettres → chiffres (les deux versions reçoivent les mêmes chiffres).
    for debut_n, fin_n, valeur in reversed(nombres.plages([c for _, c in paires])):
        paires[debut_n:fin_n] = [(str(valeur), str(valeur))]
    _reecrire(paires)
    phrase.negation = _negative([c for _, c in paires])
    # Politesse et hésitations.
    partout = [s.split() for s in POLITESSE_PARTOUT]
    debut = sorted((s.split() for s in POLITESSE_DEBUT), key=len, reverse=True)
    _remplacer_suites(paires, partout, seulement_debut=False)
    questions = [q.split() for q in QUESTIONS_DEBUT]
    envies = [e.split() for e in ENVIES_DEBUT]
    while True:
        if any([c for _, c in paires[: len(q)]] == q and len(paires) > len(q) for q in questions):
            phrase.question = True
        if any([c for _, c in paires[: len(e)]] == e and len(paires) > len(e) for e in envies):
            phrase.envie = True
        if not _remplacer_suites(paires, debut, seulement_debut=True):
            break
    fin = sorted((s.split() for s in POLITESSE_FIN), key=len, reverse=True)
    change = True
    while change:
        change = False
        for suite in fin:
            n = len(suite)
            if len(paires) > n and [c for _, c in paires[-n:]] == suite:
                del paires[-n:]
                change = True
    if [c for _, c in paires] in (["merci"], ["merci", "beaucoup"], ["merci", "bien"]):
        paires.clear()  # « merci » tout seul : politesse
    _oral(paires)
    phrase.jetons = [j for j, _ in paires]
    phrase.cles = [c for _, c in paires]
    return phrase


def _oral(paires: list[tuple[str, str]]) -> None:
    """Les tournures orales autour du verbe, retirées sans toucher au sens :
    « tu me lances X » → « lances X » ; « coupe-moi le son » → « coupe le son » ; « ouvre donc X » → « ouvre X » ;
    « fais démarrer X » → « demarrer X » ; « il est quelle heure là » → « il est quelle heure »."""
    if len(paires) > 1 and paires[0][1] == "t" and paires[1][1] in AUXILIAIRES:
        paires[0] = ("tu", "tu")  # « t'as l'heure » = « tu as l'heure »
    if len(paires) > 2 and paires[0][1] in SUJETS and paires[1][1] not in AUXILIAIRES:
        del paires[0]  # « on est quel jour », « tu as l'heure » : la grammaire les connaît tels quels
    if len(paires) > 2 and paires[0][1] in CLITIQUES and paires[1][1] not in GARDE_MOI | PRONOMINAUX | AUXILIAIRES:
        del paires[0]  # « (peux-tu) me lancer X » ; « me concentrer » garde son « me »
    if len(paires) > 1 and paires[0][1] == "fais" and paires[1][1] in INFINITIFS_APRES_FAIS:
        del paires[0]
    if len(paires) == 2 and paires[1][1] in APRES_VERBE - {"moi", "nous"}:
        del paires[1]  # « verrouille vite »
    while len(paires) > 2 and paires[1][1] in APRES_VERBE:
        if paires[1][1] == "nous" and paires[0][1] in VERBES_TEXTE_LIBRE:
            break  # « traduis nous restons à votre disposition »
        if paires[1][1] in ("moi", "nous") and paires[0][1] in GARDE_MOI:
            break
        del paires[1]
    if len(paires) > 1 and paires[-1][0] == "là":
        del paires[-1]
    cles = [c for _, c in paires]
    for fin in FINS_SUPERFLUES:  # « coupe le son de l'ordi », « arrête de m'écouter un moment »
        n = len(fin)
        if len(cles) > n + 1 and cles[-n:] == fin:
            del paires[-n:]
            break
