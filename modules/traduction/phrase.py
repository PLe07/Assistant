"""La phrase qui vient de finir par un point : la trouver, décider s'il faut la traduire. 100 % local, sans macOS.

macOS compte les positions dans un texte en « unités UTF-16 » (un emoji en vaut 2) : les fonctions ci-dessous
convertissent, pour ne jamais remplacer le mauvais morceau.
"""

import re
import unicodedata

FINS = ".!?…\n\r"  # ce qui termine la phrase d'avant (une ponctuation seulement si une espace la suit : « 3.5 », non)
SUITE_MAX = 40  # le début de la phrase suivante, déjà tapé après le point
MOTS_FR = set("""le la les un une des du de d l au aux et est sont je j tu il elle on nous vous ils elles ne n pas
que qu qui quoi dans pour avec sur par ce c cette ces mon ma mes ton ta tes son sa ses notre votre leur leurs mais ou
donc car si plus très bien faire fait été être avoir ai as a avons avez ont suis es sommes êtes y en se s m t""".split())
MOTS_EN = set("""the a an and is are was were i you he she it we they not that this these those of to in for with on
at by my your his her our their but or so if very be been have has had do does did will would can could""".split())


def unites(texte: str) -> int:
    """La longueur de ce texte pour macOS (unités UTF-16)."""
    return len(texte.encode("utf-16-le")) // 2


def position(texte: str, unites_utf16: int) -> int:
    """Une position macOS (UTF-16) → la position Python correspondante dans ce texte."""
    total = 0
    for i, car in enumerate(texte):
        if total >= unites_utf16:
            return i
        total += 2 if ord(car) > 0xFFFF else 1
    return len(texte)


def _fin_de_phrase(texte: str, j: int) -> bool:
    """Une phrase se termine juste avant la position j : retour à la ligne, ou ponctuation suivie d'une espace."""
    car = texte[j - 1]
    return car in "\n\r" or (car in FINS and (j == len(texte) or texte[j].isspace()))


def phrase_avant(texte: str, curseur: int) -> tuple[int, str] | None:
    """(début en unités macOS, phrase) : la phrase qui finit par le dernier point avant le curseur ; None sinon.
    Après le point, tu as pu taper une espace, un retour à la ligne, ou le début de la phrase suivante
    (au plus SUITE_MAX caractères, après une espace)."""
    fin = position(texte, curseur)
    i = texte.rfind(".", 0, fin)
    if i < 0:
        return None
    suite = texte[i + 1:fin]
    if suite.strip() and (not suite[0].isspace() or len(suite) > SUITE_MAX or any(c in FINS for c in suite)):
        return None
    fin = i + 1
    debut = i
    while debut > 0 and not _fin_de_phrase(texte, debut):
        debut -= 1
    while debut < fin and texte[debut].isspace():
        debut += 1
    phrase = texte[debut:fin]
    return (unites(texte[:debut]), phrase) if phrase.strip(" .") else None


def phrases_de_fin(texte: str, combien: int = 1) -> list[tuple[int, str]]:
    """Les dernières phrases finies par un point (au plus « combien », qui se suivent), dans l'ordre du texte :
    [(position Python, phrase)]. Seule la toute dernière peut être suivie du début de la suivante."""
    trouvees, fin = [], len(texte)
    while len(trouvees) < combien:
        trouve = phrase_avant(texte[:fin], unites(texte[:fin]))
        if trouve is None:
            break
        fin = position(texte, trouve[0])
        trouvees.insert(0, (fin, trouve[1]))
    return trouvees


def graphemes(texte: str) -> int:
    """Le nombre de caractères que tu vois (une flèche ← en passe un) : un emoji composé, un drapeau ou une lettre
    avec son accent séparé comptent pour un."""
    n, colle, drapeau = 0, False, False
    for car in texte:
        if colle:  # le caractère après un « liant » (ZWJ) fait partie du même emoji
            colle = False
            continue
        if car == "\u200d":
            colle = True
            continue
        if unicodedata.combining(car) or "\ufe00" <= car <= "\ufe0f" or "\U0001f3fb" <= car <= "\U0001f3ff":
            continue
        if "\U0001f1e6" <= car <= "\U0001f1ff":  # un drapeau = deux lettres spéciales
            drapeau = not drapeau
            if not drapeau:
                continue
        n += 1
    return n


def langue(phrase: str) -> str | None:
    """« fr », « en »… détectée sur ton Mac (macOS NaturalLanguage) ; sinon une estimation par mots courants."""
    try:
        from NaturalLanguage import NLLanguageRecognizer

        trouvee = NLLanguageRecognizer.dominantLanguageForString_(phrase)
        if trouvee:
            return str(trouvee)
    except Exception:  # pas sur un Mac, ou bibliothèque absente : l'estimation suffit
        pass
    mots = re.findall(r"[a-zàâäçéèêëîïôöùûüÿœæ]+", phrase.lower())
    fr, en = sum(m in MOTS_FR for m in mots), sum(m in MOTS_EN for m in mots)
    if re.search(r"[àâçéèêëîïôùûœ]", phrase.lower()):
        fr += 1
    return "fr" if fr > en else "en" if en > fr else None


def raison_de_ne_pas_traduire(phrase: str, mots_min: int = 3) -> str | None:
    """None : la phrase est à traduire. Sinon, pourquoi pas (nombre, adresse, trop courte, pas du français)."""
    avant_point = phrase[:-1].rstrip()
    if avant_point.endswith((".", "…")):
        return "points de suspension"
    if not avant_point or avant_point[-1].isdigit():
        return "nombre"  # « 3.5 », « version 2. »
    dernier = avant_point.split()[-1] if avant_point.split() else ""
    if re.search(r"[/@]|www|\.[a-z]{2,4}$", dernier.lower()):
        return "adresse"  # « www.site.fr », « nom@mail.com »
    if len(re.findall(r"\w+", avant_point)) < mots_min:
        return "trop courte"
    if langue(avant_point) != "fr":
        return "pas du français"
    return None


def finir_comme(traduction: str) -> str:
    """La traduction sur une ligne, finie par un seul point (comme la phrase que tu as tapée)."""
    traduction = " ".join(traduction.split()).rstrip(" .…")
    return traduction + "." if traduction else ""
