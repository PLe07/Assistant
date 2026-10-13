"""Comprendre une phrase : intention de la liste blanche + paramètres validés, ou « je n'ai pas compris ».

Statuts :
- `compris` : une intention et ses paramètres (objet du catalogue, nombre, durée, texte libre) ;
- `ambigu` : deux ou trois objets proches (« Notes ou Notion ? ») : tu choisis par la voix ou d'un clic ;
- `pas_compris` : rien de sûr ; jusqu'à trois suggestions proches, cliquables ;
- `refus` : une demande reconnue mais non prise en charge par choix (éteindre, supprimer, envoyer…) ;
- `negation` : « ne ferme pas Safari » : rien n'est fait ;
- `vide` : rien d'exploitable (silence, politesse seule).
Une phrase n'est jamais « à moitié » comprise : la règle doit couvrir toute la phrase, et l'objet doit ressembler à un
objet connu au-delà du seuil.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from rapidfuzz import fuzz

from voix.nlu import durees, questions, sacs
from voix.nlu import grammaire as g
from voix.nlu.alias import Commandes
from voix.nlu.approx import forme_normale
from voix.nlu.catalogue import Candidat, Catalogue
from voix.nlu.intentions import INTENTIONS
from voix.nlu.nombres import ordinal
from voix.nlu.normalisation import Phrase, normaliser

MOTS_VIDES = {"pas", "rien", "plus", "jamais", "ca", "ce", "quelque chose", "tout", "le", "la", "les"}
NEGATION_MOTS = {"ne", "n", "pas", "jamais", "plus", "rien", "point", "surtout"}
PRIORITE_GENRES = ("alias", "app", "dossier", "site", "routine", "playlist", "raccourci")
REQUETE_MAX = 200

# Les modes d'Ambiance qu'on sait reconnaître (forme dite → nom du mode chez Ambiance) ; remplacés par ceux que
# son README annonce s'il est installé.
MODES_AMBIANCE = {
    "code": "code", "concentration": "focus", "focus": "focus", "detente": "detente", "relax": "detente",
    "lecture": "lecture", "sommeil": "sommeil", "dodo": "sommeil", "travail": "travail", "sport": "sport",
    "creatif": "creatif", "creation": "creatif", "fete": "fete", "cuisine": "cuisine", "meditation": "meditation",
}  # fmt: skip
MODES_RESERVES = {"sombre", "clair", "nuit", "jour", "silencieux", "muet", "discret", "parle", "vocal", "voix", "dark",
                  "light", "noir", "blanc"}  # fmt: skip


@dataclass
class Contexte:
    catalogue: Catalogue
    commandes: Commandes = field(default_factory=Commandes)
    modules: frozenset[str] = frozenset()
    modes_ambiance: dict[str, str] = field(default_factory=lambda: dict(MODES_AMBIANCE))
    seuil: float = 0.80
    marge: float = 0.06
    maintenant: Callable[[], datetime] = datetime.now


@dataclass
class Choix:
    libelle: str
    comprehension: Comprehension


@dataclass
class Comprehension:
    statut: str  # compris, ambigu, pas_compris, refus, negation, vide
    intention: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    confiance: float = 0.0
    choix: list[Choix] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    texte: str = ""
    raison: str = ""

    @property
    def sensible(self) -> bool:
        return self.intention is not None and INTENTIONS[self.intention].sensible


def _compris(intention: str, confiance: float = 1.0, **params: Any) -> Comprehension:
    assert intention in INTENTIONS, intention
    return Comprehension("compris", intention, dict(params), confiance)


def _pas_compris(raison: str = "", suggestions: Iterable[str] = ()) -> Comprehension:
    return Comprehension("pas_compris", raison=raison, suggestions=list(dict.fromkeys(suggestions))[:3])


def _premier(motifs: list[re.Pattern[str]], texte: str) -> re.Match[str] | None:
    for m in motifs:
        r = m.fullmatch(texte)
        if r:
            return r
    return None


# --- objets du catalogue -------------------------------------------------------------------------------------------


@dataclass
class Resolution:
    statut: str  # trouve, ambigu, echec
    candidat: Candidat | None = None
    rivaux: list[Candidat] = field(default_factory=list)
    proches: list[Candidat] = field(default_factory=list)


def nettoyer_objet(texte: str) -> tuple[list[str], str | None]:
    """Les variantes de l'objet dit (avec et sans articles), et l'indice de genre (« l'app », « le site »)."""
    brut = re.sub(g.SUFFIXES_OBJET, "", texte).strip()
    t = brut
    indice = "dossier" if re.search(r"\bdans le finder$", texte) else None
    for _ in range(2):  # « la fenêtre de l'app Notes » : deux mots qui décrivent, puis le nom
        for genre, motif in g.INDICES_GENRE:
            m = re.match(rf"^(?:{g.developper('{DETS}')}){motif} (.+)$", t)
            if m:
                indice, t = indice or genre, m.group(1)
                break
        else:
            break
    variantes: list[str] = []
    for v in (t, brut):  # « le dossier personnel » : « dossier » est un indice… et une partie du nom
        sans_det = re.sub(rf"^(?:{g.developper('{DET}')} )+", "", v)
        for x in (v, sans_det):
            if x and x not in variantes:
                variantes.append(x)
    return variantes, indice


# Des mots qui ne nomment jamais rien : « ouvre ce que… » n'est pas un objet.
MOTS_OUTILS = {"ce", "que", "qu", "qui", "ca", "cela", "ceci", "il", "elle", "y", "en", "j", "ai", "tout", "rien",
               "quoi", "le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "mon", "ma", "mes"}  # fmt: skip


def resoudre(ctx: Contexte, variantes: list[str], genres: tuple[str, ...], indice: str | None) -> Resolution:
    variantes = [v for v in variantes if not set(v.split()) <= MOTS_OUTILS]
    if indice is not None and indice in genres:
        genres = tuple(x for x in genres if x in (indice, "alias"))
    meilleurs: dict[tuple[str, str], Candidat] = {}
    for v in variantes:
        for c in ctx.catalogue.chercher(v, genres, plancher=0.5):
            cle = (c.objet.genre, c.objet.ident)
            if cle not in meilleurs or c.score > meilleurs[cle].score:
                meilleurs[cle] = c
    candidats = sorted(meilleurs.values(), key=lambda c: (-c.score, c.objet.genre, c.objet.nom))
    if not candidats or candidats[0].score < ctx.seuil:
        return Resolution("echec", proches=candidats[:3])
    haut = candidats[0]
    # Un genre prioritaire (alias > app > dossier > site…) l'emporte s'il est presque aussi ressemblant ; mais un nom
    # dit exactement (« lance Révisions », la playlist) n'est pas battu par un nom seulement proche.
    for genre in PRIORITE_GENRES:
        prio = next((x for x in candidats if x.objet.genre == genre), None)
        if haut.score >= 0.99 and prio is not None and prio.score < 0.99:
            continue
        if prio is not None and prio.score >= ctx.seuil and prio.score >= haut.score - ctx.marge:
            haut = prio
            break
    if haut.score >= 1.0:
        return Resolution("trouve", haut)  # dit exactement : pas d'hésitation
    rivaux = [
        c
        for c in candidats
        if c is not haut
        and c.objet.genre == haut.objet.genre
        and c.score >= ctx.seuil
        and haut.score - c.score <= ctx.marge
    ]
    if rivaux:
        return Resolution("ambigu", haut, rivaux[:2])
    return Resolution("trouve", haut)


INTENTION_PAR_GENRE_OUVRIR = {
    "app": "app.ouvrir",
    "dossier": "dossier.ouvrir",
    "site": "web.ouvrir_site",
    "alias": "alias.ouvrir",
    "routine": "routine.lancer",
    "playlist": "musique.playlist",
    "raccourci": "raccourci.lancer",
}
INTENTION_PAR_GENRE_AFFICHER = {**INTENTION_PAR_GENRE_OUVRIR, "app": "app.afficher"}
GENRES_OUVRIR = ("alias", "app", "dossier", "site", "routine", "playlist", "raccourci")


def _depuis_resolution(
    r: Resolution, par_genre: dict[str, str], verbe: str, ctx: Contexte, params: dict[str, Any] | None = None
) -> Comprehension:
    def comprendre_candidat(c: Candidat) -> Comprehension:
        return _compris(par_genre[c.objet.genre], c.score, objet=c.objet, **(params or {}))

    if r.statut == "trouve" and r.candidat is not None:
        return comprendre_candidat(r.candidat)
    if r.statut == "ambigu" and r.candidat is not None:
        options = [r.candidat, *r.rivaux]
        noms = [c.objet.nom for c in options]
        question = (", ".join(noms[:-1]) + " ou " + noms[-1]) + " ?"
        return Comprehension(
            "ambigu",
            par_genre[r.candidat.objet.genre],
            confiance=r.candidat.score,
            choix=[Choix(c.objet.nom, comprendre_candidat(c)) for c in options],
            raison=question,
        )
    return _pas_compris(
        "objet inconnu", [f"{verbe} {c.objet.nom}" for c in r.proches if c.score >= 0.6 and c.objet.genre in par_genre]
    )


# Après le nom exact d'un objet, une fin qui ne le complète pas (« ferme VLC, le film est fini », « ouvre Excel le
# fichier des ventes ») ; pas un complément du nom (« le dossier de presse » n'est pas « le dossier »).
_COMPLEMENTS = {"de", "du", "des", "d", "a", "au", "aux", "en"}
_NEGATIONS_FIN = {"ne", "n", "pas", "jamais", "non", "rien"}
# Des noms communs qui ne désignent rien seuls : « ouvre le dossier secret de la NASA » n'est pas « mon dossier ».
_GENERIQUES = {"dossier", "fichier", "document", "site", "page", "app", "appli", "application", "logiciel",
               "programme", "fenetre", "liste", "boite", "truc"}  # fmt: skip


def _objet(ctx: Contexte, m: re.Match[str], genres: tuple[str, ...], par_genre: dict[str, str], verbe: str,
           params: dict[str, Any] | None = None) -> Comprehension:  # fmt: skip
    variantes, indice = nettoyer_objet(m.group("objet"))
    r = resoudre(ctx, variantes, genres, indice)
    return _depuis_resolution(r, par_genre, verbe, ctx, params)


# --- textes libres ----------------------------------------------------------------------------------------------


def _libre(phrase: Phrase, m: re.Match[str], groupe: str, sans_articles: bool = False) -> str | None:
    """Le texte libre d'un groupe (recherche, message), avec ses accents ; None s'il est vide ou trop long.

    Les articles sont gardés (« la révolution française »), sauf pour Spotlight (« mes billets » → « billets »)."""
    texte = phrase.extrait(m.start(groupe), m.end(groupe)).strip()
    texte = re.sub(r"^(?:sur |pour )+", "", texte)
    if sans_articles:
        texte = re.sub(r"^(?:le |la |les |l |un |une |des |du |de |d |mon |ma |mes |ton |ta |tes )+", "", texte)
    if not forme_normale(texte) or len(texte) > REQUETE_MAX:
        return None
    return texte


def _rang(mot: str) -> int | None:
    if mot.isdigit():
        n = int(mot)
        return n if 1 <= n <= 20 else None
    return ordinal(mot)


# --- la compréhension ---------------------------------------------------------------------------------------------


def comprendre(texte: str, ctx: Contexte) -> Comprehension:
    phrase = normaliser(texte)
    if phrase.trop_longue:
        return replace(_pas_compris("phrase trop longue pour une commande"), texte="")
    resultat = _comprendre(phrase, ctx)
    if resultat.statut == "pas_compris" and resultat.raison in ("rien de sûr", "objet inconnu", "durée incomprise"):
        seconde = _seconde_lecture(phrase, ctx)
        if seconde is not None:
            resultat = seconde
    resultat.texte = phrase.texte
    return resultat


# --- la seconde lecture ----------------------------------------------------------------------------------------
# Quand la grammaire ne reconnaît pas la phrase telle quelle, on essaie la même demande remise dans l'ordre, puis
# les sacs de mots. Chaque essai repasse par toute la grammaire et le catalogue : rien n'est « à moitié » compris.

_VERBES_TETE = {
    v for classe in ("OUVRIR", "LANCER", "DEMARRER", "FERMER", "QUITTER", "CACHER", "AFFICHER", "MONTER", "BAISSER",
                     "COUPER", "METTRE", "REMETTRE", "ACTIVER", "DESACTIVER", "VERROUILLER", "JOUER", "CHERCHER",
                     "TRADUIRE", "RAPPELER")
    for v in g.VERBES[classe].split()
} - {"mais", "regarde", "regarder", "voir"}  # fmt: skip
_PRONOMS = {"le", "la", "les", "l"}
_BRUITS_DEBUT = [
    b.split()
    for b in (
        "j en ai fini avec",
        "j ai fini avec",
        "j ai termine avec",
        "j ai plus besoin de",
        "j ai plus besoin d",
        "je n ai plus besoin de",
        "pour",
        "et",
        "bon",
    )
]
_CONNECTEURS = {"pour", "parce", "car", "avec", "comme", "histoire", "afin", "pendant", "durant", "quand", "lorsque",
                "apres", "avant"}  # fmt: skip
# Une fin coupée ne commence pas par un complément : « monte le son de la guitare », « mets la musique dans la
# voiture ».
_DEBUTS_COMPLEMENT = {"de", "du", "des", "d", "a", "au", "aux", "en", "dans", "sur", "sous", "chez", "vers", "contre",
                      "derriere", "devant", "entre"}  # fmt: skip
_VERBES_FAIBLES = set(g.VERBES["METTRE"].split()) | set(g.VERBES["JOUER"].split()) | set(g.VERBES["ARRETER"].split())
_VERBES_ALLER = {"va", "vas", "aller", "allez", "passe", "bascule", "reviens", "retourne"}
# Une phrase qui commence par un article parle d'une chose (« le mode sombre, c'est joli ») : ce n'est pas un ordre.
_ARTICLES_TETE = {"le", "la", "les", "l", "un", "une", "des", "du", "mon", "ma", "mes", "ton", "ta", "tes", "ce",
                  "cet", "cette", "ces", "son", "sa", "ses", "notre", "nos", "votre", "vos"}  # fmt: skip
# Ce qu'une fin coupée peut laisser : un ordre sans objet ni paramètre (le son, la musique, le système…).
_ORDRES_SIMPLES = {
    "son.monter", "son.baisser", "son.couper", "son.remettre", "son.regler", "musique.lecture", "musique.pause",
    "musique.suivant",
    "musique.precedent", "systeme.verrouiller", "systeme.veille", "systeme.ecran_eteindre", "systeme.mode_sombre",
    "systeme.mode_clair", "systeme.wifi_activer", "systeme.wifi_desactiver", "concentration.activer",
    "concentration.desactiver", "minuteur.annuler", "module.ambiance_mood", "controle.annuler", "controle.stop",
    "controle.silencieux", "controle.parler", "controle.pause", "app.fermer_tout", "app.cacher_autres",
}  # fmt: skip
# Une nouvelle proposition commence : « ferme Chrome, il rame », « coupe le son, j'ai un appel ».
_OUVRE_PROPOSITION = {"je", "j", "il", "elle", "on", "ca", "c", "faut", "que", "qu", "nous", "tu", "ils", "elles"}
_NEGATIFS = {"ne", "n", "pas", "jamais", "plus", "non", "rien", "aucun", "aucune"}
# « quelle heure est-il à Tokyo » : « il » après le verbe est le sujet inversé, pas une nouvelle proposition.
_VERBES_INVERSES = {"est", "fait", "va", "a", "sont", "peut", "faut", "reste", "vont", "etait", "sera", "fera", "as",
                    "peux", "dois", "doit"}  # fmt: skip
# Les intentions qui ne font que dire (l'heure, la météo…) : une proposition de plus en change le sens.
_INFORMATIONS = {"systeme.heure", "systeme.date", "systeme.meteo", "systeme.batterie", "son.niveau",
                 "musique.titre", "minuteur.restant", "module.tableau_etat", "module.quotidien_menu"}  # fmt: skip
_CORRECTIONS = {"non", "pardon", "plutot", "enfin", "euh", "ou"}
_CONNECTEURS_DOUBLES = {("j", "ai"), ("on", "a"), ("il", "y"), ("j", "en"), ("c", "est")}
_INTENTIONS_A_OBJET = {
    "app.ouvrir", "app.fermer", "app.afficher", "app.cacher", "web.ouvrir_site", "dossier.ouvrir", "alias.ouvrir",
    "musique.playlist", "raccourci.lancer",
}  # fmt: skip
_RAPPELS_TETE = {"rappelle", "rappelles", "rappeler", "previens", "alerte", "reveille", "fais"}
_GARDER = re.compile(
    r"(?:garde|laisse) (?:que|seulement|juste|uniquement) (?P<x>.+?) et (?P<v>cache|ferme|quitte|masque) "
    r"(?:le reste|tout le reste|les autres|tout)"
)


def _sous_phrase(phrase: Phrase, paires: list[tuple[str, str]]) -> Phrase:
    p = Phrase(
        phrase.brut, [j for j, _ in paires], [c for _, c in paires], question=phrase.question, envie=phrase.envie
    )
    return p


def _reformulations(phrase: Phrase) -> Iterable[tuple[Phrase, bool | str | None]]:
    """(phrase remise dans l'ordre, seulement pour un objet ?) : du plus sûr au moins sûr.

    `None` : n'importe quelle action, mais pas une information (dont le sens dépend de la fin coupée)."""
    paires = list(zip(phrase.jetons, phrase.cles, strict=True))
    cles = phrase.cles
    n = len(cles)
    # « garde que Word et cache le reste » → « cache tout sauf Word ».
    m = _GARDER.fullmatch(phrase.texte)
    if m:
        debut_x = len(phrase.texte[: m.start("x")].split())
        fin_x = debut_x + len(m.group("x").split())
        v = m.group("v")
        yield _sous_phrase(phrase, [(v, v), ("tout", "tout"), ("sauf", "sauf"), *paires[debut_x:fin_x]]), False
    # « dans une heure rappelle-moi d'appeler Marc » → « rappelle-moi dans une heure d'appeler Marc ».
    if n > 3 and cles[0] == "dans":
        k = next((i for i, c in enumerate(cles) if c in _RAPPELS_TETE), None)
        if k is not None and k > 1:
            fin_verbe = k + 2 if k + 1 < n and cles[k + 1] in ("moi", "nous") else k + 1
            yield _sous_phrase(phrase, paires[k:fin_verbe] + paires[:k] + paires[fin_verbe:]), False
    # « Safari, ouvre-le », « j'ai fini avec Excel, ferme-le » → « ouvre Safari », « ferme Excel ».
    if n >= 3 and cles[-1] in _PRONOMS and cles[-2] in _VERBES_TETE:
        objet = paires[:-2]
        for bruit in _BRUITS_DEBUT:
            if [c for _, c in objet[: len(bruit)]] == bruit and len(objet) > len(bruit):
                objet = objet[len(bruit) :]
                break
        yield _sous_phrase(phrase, [paires[-2], *objet]), False
    # « je m'en vais, verrouille le Mac », « j'entends rien, monte le son » : l'ordre est à la fin.
    for i in range(1, min(n - 1, 10)):
        if phrase.jetons[i].endswith(("é", "ée", "és", "ées")):
            continue  # « j'ai cherché partout » : un participe, pas un ordre
        infinitif = cles[i].endswith(("er", "ir", "re"))
        if cles[i] in _VERBES_TETE and not (infinitif and cles[i - 1] in ("va", "vas", "aller", "allez", "vais")):
            if not any(c in _VERBES_TETE for c in cles[:i]):
                yield _sous_phrase(phrase, paires[i:]), False
            break
    # « ouvre Safari… non, Chrome » : la correction remplace l'objet.
    if n >= 4 and cles[0] in _VERBES_TETE:
        for i in range(2, n - 1):
            if cles[i] in _CORRECTIONS and cles[i - 1] not in _NEGATIFS:
                yield _sous_phrase(phrase, [paires[0], *paires[i + 1 :]]), True
                break
    # « ouvre Teams pour la réunion », « lance Zoom, j'ai une visio » : le but ne change pas l'ordre.
    for i in range(n - 1, 1, -1):
        if cles[i] in _CONNECTEURS or (i + 1 < n and (cles[i], cles[i + 1]) in _CONNECTEURS_DOUBLES):
            yield _sous_phrase(phrase, paires[:i]), True
    # « ferme Chrome, il rame », « mets le Mac en veille, j'ai fini » : une proposition de plus, sans négation
    # (« ouvre Safari, je veux pas » n'est pas un ordre d'ouvrir).
    for i in range(2, n - 1):
        if cles[0] in _ARTICLES_TETE:
            break  # « le mode sombre, c'est joli » : un avis, pas un ordre
        if cles[i] in ("il", "elle", "on", "nous", "tu") and cles[i - 1] in _VERBES_INVERSES:
            continue
        if cles[i] in _OUVRE_PROPOSITION | _CONNECTEURS:
            fin = " ".join(cles[i:]).replace("plus tard", "")
            if not set(fin.split()) & _NEGATIFS:
                yield _sous_phrase(phrase, paires[:i]), None
            break
    # « baisse le son, les enfants dorment » : une fin sans mot de liaison ; l'ordre qui reste doit être reconnu
    # tel quel par la grammaire (au moins trois mots) — jamais par un sac de mots.
    for k in range(n - 1, 2, -1):
        queue = cles[k:]
        if len(queue) > 4 or cles[0] in _ARTICLES_TETE:
            break
        if queue[0] in _DEBUTS_COMPLEMENT or set(queue) & _NEGATIFS or any(c.isdigit() for c in queue):
            continue
        yield _sous_phrase(phrase, paires[:k]), "grammaire"
    # « ouvre Excel le fichier des ventes », « va sur Twitch voir le live » : le nom exact d'un objet, puis une fin.
    if n >= 3 and cles[0] in (_VERBES_TETE - _VERBES_FAIBLES) | _VERBES_ALLER:
        for k in range(n - 1, 1, -1):
            queue = cles[k:]
            if queue[0] in _DEBUTS_COMPLEMENT or set(queue) & _NEGATIONS_FIN or cles[k - 1] in _GENERIQUES:
                continue
            yield _sous_phrase(phrase, paires[:k]), "exact"


def _seconde_lecture(phrase: Phrase, ctx: Contexte) -> Comprehension | None:
    for autre, objet_seulement in _reformulations(phrase):
        if not autre.cles or autre.cles == phrase.cles:
            continue
        c = _comprendre(autre, ctx)
        if objet_seulement == "grammaire":
            if c.statut == "compris" and c.intention in _ORDRES_SIMPLES:
                return c
            continue
        if objet_seulement == "exact":
            if c.statut == "compris" and c.intention in _INTENTIONS_A_OBJET and c.confiance >= 0.97:
                return c
            continue
        if objet_seulement is None and c.statut == "pas_compris":
            intention = sacs.lire(autre.cles)  # « mets le Mac en mode sombre pour la soirée »
            if intention is not None and intention not in _INFORMATIONS:
                return _compris(intention, 0.9)
        if c.statut not in ("compris", "ambigu", "refus"):
            continue
        if objet_seulement and c.intention not in _INTENTIONS_A_OBJET:
            continue
        if objet_seulement is None and c.intention in _INFORMATIONS:
            continue
        if c.intention in ("controle.oui", "controle.non"):
            continue  # une réponse se dit franchement : « d'accord, je vois » n'est pas un « oui »
        return c
    intention = sacs.lire(phrase.cles)
    if intention is None and phrase.envie:
        intention = sacs.lire([*phrase.cles, "envie"])
    if intention in ("son.monter", "son.baisser"):
        mots = set(phrase.cles)
        return _compris(intention, 0.9, pas=5 if "peu" in mots else 20 if "beaucoup" in mots else 10)
    if intention is not None:
        return _compris(intention, 0.9)
    return None


def _comprendre(phrase: Phrase, ctx: Contexte) -> Comprehension:  # noqa: C901 - une liste de règles, lue de haut en bas
    t = phrase.texte
    if not t:
        if re.search(r"\bmerci\b", normaliser_brut(phrase.brut)):
            return Comprehension("vide", raison="Avec plaisir")
        return Comprehension("vide")
    # Oui / non d'abord : « surtout pas » répond à une confirmation, ce n'est pas une négation d'ordre.
    if _premier(g.OUI, t):
        return _compris("controle.oui")
    if _premier(g.NON, t):
        return _compris("controle.non")
    reponse = sacs.oui_non(phrase.cles)
    if reponse is not None:
        return _compris(reponse)
    # Les tournures négatives qui SONT des commandes : « ne parle plus », « ne m'écoute plus », « ne pas déranger ».
    for intention, motifs in g.CONTROLE.items():
        if _premier(motifs, t):
            return _compris(intention)
    if _premier(g.CONCENTRATION_DESACTIVER, t):
        return _compris("concentration.desactiver")
    if _premier(g.CONCENTRATION_ACTIVER, t) and not _premier(g.AMBIANCE_MODE, t):
        return _compris("concentration.activer")
    if phrase.negation:
        # « ne ferme pas Safari » : sans la négation, ce serait une commande → on ne fait rien, et on le dit.
        # « comment fermer une app qui ne répond pas » : ce n'est pas une commande → pas compris.
        sans = Phrase(phrase.brut)
        for jeton, cle in zip(phrase.jetons, phrase.cles, strict=True):
            if cle not in NEGATION_MOTS:
                sans.jetons.append(jeton)
                sans.cles.append(cle)
        if _comprendre(sans, ctx).statut in ("compris", "ambigu", "refus"):
            return Comprehension("negation", raison="D'accord, je ne fais rien.")
        return _pas_compris("phrase négative")
    if _premier(g.REFUS, t):
        return Comprehension("refus", "refus", raison="Je ne fais pas ça, par sécurité.")
    # Les questions d'information, toutes tournures (« la batterie est à combien ») : avant « il reste combien… ».
    info = questions.question(phrase.cles, phrase.question)
    if info is not None:
        return _compris(info)

    # Minuteur, rappel.
    m = _premier(g.RAPPEL, t)
    if m:
        rappel = _rappel(phrase, m.start("reste"), ctx)
        if rappel is not None:
            return rappel
        # Sans message (« préviens-moi dans 5 minutes ») : c'est un minuteur, plus bas.
    if _premier(g.MINUTEUR_RESTANT, t):
        return _compris("minuteur.restant")
    m = _premier(g.MINUTEUR, t)
    if m:
        d = durees.duree(m.group("duree"))
        mots = m.group("duree").split()
        for i in range(1, min(len(mots), 5)):  # « minuteur pour les pâtes 9 minutes » : l'étiquette, puis la durée
            if d is None and mots[i][0].isdigit():
                d = durees.duree(" ".join(mots[i:]))
        for k in range(len(mots) - 1, 0, -1):  # « minuteur de 5 minutes de pause » : la durée, puis l'étiquette
            if d is None and mots[k] in ("de", "d", "pour"):
                d = durees.duree(" ".join(mots[:k]))
        if d:
            return _compris("minuteur.lancer", duree_s=d)
        return _pas_compris("durée incomprise", ["minuteur 10 minutes", "minuteur 30 secondes"])

    # Raccourcis Apple et routines.
    if _premier(g.RACCOURCI_LISTE, t):
        return _compris("raccourci.lister")
    m = _premier(g.RACCOURCI, t)
    if m:
        return _objet(ctx, m, ("raccourci",), {"raccourci": "raccourci.lancer"}, "lance le raccourci")
    m = _premier(g.ROUTINE, t)
    if m:
        return _objet(ctx, m, ("routine",), {"routine": "routine.lancer"}, "lance la routine")
    routine = _phrase_de_routine(t, ctx)
    if routine is not None:
        return routine

    # Mes modules.
    if _premier(g.TABLEAU_ETAT, t):
        return _compris("module.tableau_etat")
    if _premier(g.TABLEAU_OUVRIR, t):
        return _compris("module.tableau_ouvrir")
    if _premier(g.AMBIANCE_MOOD, t):
        return _compris("module.ambiance_mood")
    if _premier(g.BOUCLIER, t):
        return _compris("module.bouclier_presse_papiers")
    if _premier(g.QUOTIDIEN_MENU, t):
        return _compris("module.quotidien_menu")

    # Son.
    if _premier(g.SON_NIVEAU, t):
        return _compris("son.niveau")
    m = _premier(g.SON_EXTREME, t)
    if m:
        ou = m.group("ou")
        niveau = (
            100
            if ou.startswith("a fond") or ou in ("au maximum", "au max")
            else 0
            if ou in ("au minimum", "au min")
            else 50
        )
        return _compris("son.regler", niveau=niveau)
    m = _premier(g.SON_REGLER, t)
    if m:
        n = int(m.group("n"))
        if n > 100:
            return _pas_compris("le volume va de 0 à 100", ["volume à 30 %", "volume à 100 %"])
        return _compris("son.regler", niveau=n)
    if _premier(g.SON_COUPER, t):
        return _compris("son.couper")
    if _premier(g.SON_REMETTRE, t):
        return _compris("son.remettre")
    for motifs, intention in ((g.SON_MONTER, "son.monter"), (g.SON_BAISSER, "son.baisser")):
        m = _premier(motifs, t)
        if m:
            pas = 10
            if m.groupdict().get("pas"):
                pas = int(m.group("pas"))
                if not 1 <= pas <= 100:
                    return _pas_compris("le volume va de 0 à 100")
            elif m.groupdict().get("qte"):
                pas = {
                    "un peu": 5,
                    "encore un peu": 5,
                    "un petit peu": 3,
                    "beaucoup": 20,
                    "un max": 30,
                    "un bon coup": 20,
                    "un poil": 5,
                    "un chouia": 5,
                    "un chouilla": 5,
                    "legerement": 5,
                }.get(  # fmt: skip
                    m.group("qte"), 10
                )
            return _compris(intention, pas=pas)

    # Musique.
    m = _premier(g.MUSIQUE_PLAYLIST, t)
    if m:
        return _objet(ctx, m, ("playlist",), {"playlist": "musique.playlist"}, "lance la playlist")
    if _premier(g.MUSIQUE_TITRE, t):
        return _compris("musique.titre")
    if _premier(g.MUSIQUE_PAUSE, t):
        return _compris("musique.pause")
    m = _premier(g.MUSIQUE_LECTURE, t)
    if m:
        lecteur = m.groupdict().get("lecteur")
        params: dict[str, Any] = {"lecteur": "spotify" if lecteur == "spotify" else "musique"} if lecteur else {}
        return _compris("musique.lecture", **params)
    if _premier(g.MUSIQUE_SUIVANT, t):
        return _compris("musique.suivant")
    if _premier(g.MUSIQUE_PRECEDENT, t):
        return _compris("musique.precedent")

    # Système.
    simples = [
        (g.VERROUILLER, "systeme.verrouiller"), (g.ECRAN_ETEINDRE, "systeme.ecran_eteindre"),
        (g.VEILLE, "systeme.veille"), (g.MODE_SOMBRE, "systeme.mode_sombre"), (g.MODE_CLAIR, "systeme.mode_clair"),
        (g.WIFI_ACTIVER, "systeme.wifi_activer"), (g.WIFI_DESACTIVER, "systeme.wifi_desactiver"),
        (g.BATTERIE, "systeme.batterie"), (g.HEURE, "systeme.heure"), (g.DATE, "systeme.date"),
        (g.METEO, "systeme.meteo"), (g.CONCENTRATION_DESACTIVER, "concentration.desactiver"),
    ]  # fmt: skip
    for motifs, intention in simples:
        if _premier(motifs, t):
            return _compris(intention)

    # « mode concentration » : Ambiance s'il est installé, sinon la concentration de macOS.
    m = _premier(g.AMBIANCE_MODE, t)
    if m and "ambiance" not in ctx.modules:
        # « lance mode lecture » : ton raccourci « Mode lecture » passe avant un mode d'Ambiance absent.
        debut_mode = t.rfind("mode ") if "mode " in t else 0
        exacts = [c for c in ctx.catalogue.chercher(t[debut_mode:], ("raccourci", "routine", "playlist", "alias"))
                  if c.score >= 0.99]  # fmt: skip
        if len(exacts) == 1:
            c = exacts[0]
            return _compris(INTENTION_PAR_GENRE_OUVRIR[c.objet.genre], c.score, objet=c.objet)
    if m and m.group("mode") not in MODES_RESERVES:
        mode = m.group("mode")
        cli = ctx.modes_ambiance.get(mode)
        if cli is not None and ("ambiance" in ctx.modules or mode not in ("concentration", "focus")):
            return _compris("module.ambiance_mode", mode=cli)
    if _premier(g.CONCENTRATION_ACTIVER, t):
        return _compris("concentration.activer")
    if m and m.group("mode") not in MODES_RESERVES:
        return _pas_compris("mode inconnu", ["mode sombre", "mode silencieux", "mode concentration"])

    # Fichiers.
    derniers = (
        (g.DERNIER_PDF, "fichier.dernier_pdf"),
        (g.DERNIER_TELECHARGE, "fichier.dernier_telecharge"),
        (g.DERNIERE_CAPTURE, "fichier.derniere_capture"),
    )
    for motifs, intention in derniers:
        if _premier(motifs, t):
            return _compris(intention)
    m = _premier(g.REVELER, t)
    if m:
        rang = _rang(m.group("rang"))
        if rang:
            return _compris("fichier.reveler_resultat", rang=rang)
    m = _premier(g.RESULTAT, t)
    if m:
        rang = _rang(m.group("rang"))
        if rang:
            return _compris("fichier.ouvrir_resultat", rang=rang)

    # Web.
    m = _premier(g.TRADUIRE, t)
    if m:
        texte_libre = _libre(phrase, m, "texte")
        if texte_libre and m.group("texte").split()[0] not in ("ton", "ta", "tes", "toi"):
            langue = g.LANGUES.get(m.groupdict().get("langue") or "anglais", "en")
            texte_libre = (
                re.sub(r"^(?:le mot|l expression|la phrase|le terme|la formule) ", "", texte_libre) or texte_libre
            )
            return _compris("web.traduire", texte=texte_libre, langue=langue)
    for motifs, intention in ((g.YOUTUBE, "web.chercher_youtube"), (g.WIKIPEDIA, "web.chercher_wikipedia"),
                              (g.GOOGLE, "web.chercher_google"), (g.PLANS, "web.chercher_plans")):  # fmt: skip
        m = _premier(motifs, t)
        if m:
            requete = _libre(phrase, m, "requete")
            if requete:
                return _compris(intention, requete=requete)

    # Apps.
    m = _premier(g.FERMER_TOUT_SAUF, t)
    if m:
        return _objet(ctx, m, ("app",), {"app": "app.fermer_tout_sauf"}, "ferme tout sauf")
    if _premier(g.FERMER_TOUT, t):
        return _compris("app.fermer_tout")
    m = _premier(g.CACHER_AUTRES, t)
    if m:
        if m.groupdict().get("objet"):
            return _objet(ctx, m, ("app",), {"app": "app.cacher_autres"}, "cache tout sauf")
        return _compris("app.cacher_autres")
    m = _premier(g.FERMER, t)
    if m:
        return _objet(ctx, m, ("app", "alias"), {"app": "app.fermer"}, "ferme")
    m = _premier(g.CACHER, t)
    if m:
        return _objet(ctx, m, ("app",), {"app": "app.cacher"}, "cache")
    m = _premier(g.AFFICHER, t)
    if m:
        return _objet(ctx, m, ("alias", "app", "dossier", "site"), INTENTION_PAR_GENRE_AFFICHER, "va sur")
    m = _premier(g.OUVRIR, t)
    if m:
        return _objet(ctx, m, GENRES_OUVRIR, INTENTION_PAR_GENRE_OUVRIR, "ouvre")
    m = _premier(g.OUVRIR_FAIBLE, t)
    if m:
        faible = _objet(ctx, m, GENRES_OUVRIR, INTENTION_PAR_GENRE_OUVRIR, "ouvre")
        if faible.statut == "compris" and faible.confiance >= 0.95:
            return faible

    # Recherche de fichiers (Spotlight) : en dernier, le texte est libre.
    m = _premier(g.CHERCHER_FICHIER, t)
    if m:
        requete = _libre(phrase, m, "requete", sans_articles=True)
        if requete and forme_normale(requete) not in MOTS_VIDES and m.group("requete").split()[0] not in (
            "ton", "ta", "tes", "votre", "vos", "toi", "dans", "sous", "derriere", "chez", "sur"):  # fmt: skip
            return _compris("fichier.chercher", requete=requete)

    return _pas_compris("rien de sûr", suggestions(t, ctx))


_SEPARATEURS = ("qu il faut ", "a propos de ", "pour ", "que ", "de ", "qu ", "d ", "a ")  # les plus longs d'abord


def _quand(texte: str, ctx: Contexte) -> dict[str, Any] | None:
    """« dans 20 minutes » ou « a 18 h 30 » → {duree_s (, heure)} ; None si ce n'est pas un moment."""
    if texte.startswith("dans "):
        d = durees.duree(texte[5:])
        return {"duree_s": d} if d else None
    demain = texte.startswith("demain ")
    h = durees.heure(texte[len("demain ") :] if demain else texte)
    if h is None:
        return None
    maintenant = ctx.maintenant()
    cible = maintenant.replace(hour=h[0], minute=h[1], second=0, microsecond=0)
    if demain:
        cible += timedelta(days=1)
    elif cible <= maintenant:
        cible += timedelta(days=1)
    return {"duree_s": int((cible - maintenant).total_seconds()), "heure": f"{h[0]:02d}:{h[1]:02d}"}


def _rappel(phrase: Phrase, debut: int, ctx: Contexte) -> Comprehension | None:
    """Après « rappelle-moi » : « dans 20 minutes de sortir le linge » ou « de sortir le linge dans 20 minutes ».

    Toutes les coupures sont essayées (« dans 1 quart d heure de partir » : la bonne coupure est après « heure »)."""
    t = phrase.texte
    reste = t[debut:]
    # Le moment d'abord : « dans … <séparateur> message ».
    for i in range(len(reste)):
        if i and reste[i - 1] != " ":
            continue
        for sep in _SEPARATEURS:
            if reste.startswith(sep, i) and i > 0:
                quand = _quand(reste[: i - 1], ctx)
                message = phrase.extrait(debut + i + len(sep), len(t)).strip()
                if quand and forme_normale(message) and len(message) <= REQUETE_MAX:
                    return _compris("rappel.creer", message=message, **quand)
    # Sans séparateur : « dans 5 minutes thé » (la plus longue durée qui se lit).
    mots = reste.split()
    if len(mots) > 2 and mots[0] == "dans" and not durees.duree(" ".join(mots[1:])):
        for k in range(len(mots) - 1, 1, -1):
            d = durees.duree(" ".join(mots[1:k]))
            if d:
                debut_message = debut + len(" ".join(mots[:k])) + 1
                message = phrase.extrait(debut_message, len(t)).strip()
                if forme_normale(message) and len(message) <= REQUETE_MAX:
                    return _compris("rappel.creer", message=message, duree_s=d)
                break
    # Le message d'abord : « <séparateur> message dans … » (ou « … à 18 h »).
    for sep in (*_SEPARATEURS, ""):
        if not reste.startswith(sep):
            continue
        corps = reste[len(sep) :]
        for coupe in [m.start() for m in re.finditer(r" (?=dans |a |demain a )", corps)]:
            quand = _quand(corps[coupe + 1 :], ctx)
            debut_message = debut + len(sep)
            message = phrase.extrait(debut_message, debut_message + coupe).strip()
            if quand and forme_normale(message) and len(message) <= REQUETE_MAX:
                return _compris("rappel.creer", message=message, **quand)
    return None


def normaliser_brut(brut: str) -> str:
    return forme_normale(brut or "")


def _phrase_de_routine(t: str, ctx: Contexte) -> Comprehension | None:
    """Une routine se lance par une de ses phrases (« lance ma révision »), dite presque exactement."""
    meilleur: tuple[float, str] | None = None
    t = re.sub(
        r"^(?:(?:c est parti pour|c est|voila|bon|et) )*(?:(?:la|le|l|ma|mon) )?", "", t
    )  # « c'est la fin de journée »
    for r in ctx.commandes.routines:
        for forme in (*r.phrases, r.nom):
            s = fuzz.ratio(t, normaliser(forme).texte) / 100
            if s >= 0.9 and (meilleur is None or s > meilleur[0]):
                meilleur = (s, r.nom)
    if meilleur is None:
        return None
    objet = next(o for o in ctx.commandes.objets() if o.genre == "routine" and o.nom == meilleur[1])
    return _compris("routine.lancer", meilleur[0], objet=objet)


# Des intentions dont les exemples nomment un objet qui n'existe pas forcément chez toi (« la compta », « la routine
# matin ») : les suggestions les remplacent par tes vrais alias, playlists, raccourcis et routines.
NOMMEES = ("alias.ouvrir", "musique.playlist", "raccourci.lancer", "routine.lancer")


def _disponible(intention: str, ctx: Contexte) -> bool:
    if intention in NOMMEES:
        return False
    if intention.startswith("module."):  # module.tableau_ouvrir → tableau
        return intention.split(".")[1].split("_")[0] in ctx.modules
    return INTENTIONS[intention].famille != "Refus"


def exemples(ctx: Contexte) -> list[tuple[str, str]]:
    """Des phrases d'exemple (intention, phrase) qui marchent chez toi : celles de la liste blanche (sans les modules
    absents), avec tes apps, sites, dossiers, alias, playlists, raccourcis et routines."""
    resultat = [(i.ident, ex) for i in INTENTIONS.values() if _disponible(i.ident, ctx) for ex in i.exemples]
    phrases = {
        "app": (("app.ouvrir", "ouvre {}"), ("app.fermer", "ferme {}")),
        "site": (("web.ouvrir_site", "ouvre {}"),),
        "dossier": (("dossier.ouvrir", "ouvre {}"),),
        "alias": (("alias.ouvrir", "ouvre {}"),),
        "playlist": (("musique.playlist", "lance la playlist {}"),),
        "raccourci": (("raccourci.lancer", "lance le raccourci {}"),),
        "routine": (("routine.lancer", "lance la routine {}"),),
    }
    for objet in ctx.catalogue.objets:
        if objet.nom.endswith(" (dossier)"):  # « Musique (dossier) » : l'app Musique passe devant « ouvre Musique »
            resultat.append(("dossier.ouvrir", f"ouvre le dossier {objet.nom.removesuffix(' (dossier)')}"))
            continue
        resultat += [(intention, modele.format(objet.nom)) for intention, modele in phrases.get(objet.genre, ())]
    return resultat


def suggestions(texte: str, ctx: Contexte, n: int = 3) -> list[str]:
    """Les phrases connues les plus proches de ce qui a été dit (une par intention)."""
    if not texte:
        return []
    classees = sorted(
        ((fuzz.token_set_ratio(texte, forme_normale(ex)), intention, ex) for intention, ex in exemples(ctx)),
        key=lambda x: -x[0],
    )
    vues: set[str] = set()
    resultat: list[str] = []
    for score, intention, ex in classees:
        if score < 50 or intention in vues:
            continue
        vues.add(intention)
        resultat.append(ex)
        if len(resultat) == n:
            break
    return resultat
