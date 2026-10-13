"""Les briques de la compréhension : normalisation, nombres, durées, phonétique, ressemblance, ambiguïtés."""

from __future__ import annotations

from datetime import datetime

import pytest

from voix.nlu import ambiguite, durees, nombres
from voix.nlu.approx import Forme, forme_normale, sans_articles, similarite
from voix.nlu.normalisation import LONGUEUR_MAX, normaliser
from voix.nlu.phonetique import cle

# --- normalisation ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("brut", "texte", "accentue"),
    [
        ("Tu peux mettre le volume à trente pour cent, s'il te plaît ?", "mettre le volume a 30 pourcent",
         "mettre le volume à 30 pourcent"),
        (" Ouvre Notion.", "ouvre notion", "ouvre notion"),
        ("Hey Jarvis, ouvre l'app Calculatrice", "ouvre l app calculatrice", "ouvre l app calculatrice"),
        ("Volume à 30%.", "volume a 30 pourcent", "volume à 30 pourcent"),
        ("Rappelle-moi dans vingt minutes", "rappelle moi dans 20 minutes", "rappelle moi dans 20 minutes"),
        ("Minuteur 1h30", "minuteur 1 h 30", "minuteur 1 h 30"),
        ("Mets un minuteur de 10min", "mets un minuteur de 10 min", "mets un minuteur de 10 min"),
        ("cherche sur Google « crêpes à la bière »", "cherche sur google crepes a la biere",
         "cherche sur google crêpes à la bière"),
        ("Est-ce que tu peux couper le son ?", "couper le son", "couper le son"),
        ("ok euh lance une playlist", "lance une playlist", "lance une playlist"),
        ("monte le son de 1,5", "monte le son de 1.5", "monte le son de 1.5"),
        ("Œuvre d’art", "oeuvre d art", "œuvre d art"),
        ("traduis merci en anglais merci", "traduis merci en anglais", "traduis merci en anglais"),
        ("cinq pour cent", "5 pourcent", "5 pourcent"),
        ("c'est pour cent personnes", "c est pour 100 personnes", "c est pour 100 personnes"),
        ("ouvre... YouTube!!", "ouvre youtube", "ouvre youtube"),
    ],
)  # fmt: skip
def test_normaliser(brut: str, texte: str, accentue: str) -> None:
    p = normaliser(brut)
    assert p.texte == texte and p.texte_accentue == accentue and not p.negation


@pytest.mark.parametrize(
    ("brut", "negation"),
    [("Ne ferme pas Safari !", True), ("n'ouvre jamais ça", True), ("surtout pas le son", True),
     ("pas le son", True), ("ouvre Notion", False), ("ne", False), ("pas mal", False), ("surtout", False)],
)  # fmt: skip
def test_negation(brut: str, negation: bool) -> None:
    assert normaliser(brut).negation is negation


def test_politesse_seule_vide_et_phrase_trop_longue() -> None:
    assert normaliser("merci").texte == "" and normaliser("merci beaucoup").texte == ""
    assert normaliser("euh... s'il te plaît").texte == ""
    assert normaliser("").texte == "" and normaliser(None).texte == ""  # type: ignore[arg-type]
    assert normaliser("x" * (LONGUEUR_MAX + 1)).trop_longue
    assert normaliser("vas-y").texte == "vas y"  # seul, ce n'est pas une politesse à retirer : c'est un « oui »


def test_extrait_garde_les_accents() -> None:
    p = normaliser("Cherche « la révolution française » sur Google")
    debut = p.texte.index("la revolution")
    assert p.extrait(debut, debut + len("la revolution francaise")) == "la révolution française"


# --- nombres et durées -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mots", "attendu"),
    [
        ("trente", ["30"]), ("vingt et un", ["21"]), ("quatre vingt dix neuf", ["99"]), ("quatre vingts", ["80"]),
        ("soixante et onze", ["71"]), ("soixante dix sept", ["77"]), ("deux cent trente", ["230"]),
        ("mille deux cents", ["1200"]), ("deux trois", ["2", "3"]), ("dix huit", ["18"]), ("cent un", ["101"]),
        ("une minute", ["1", "minute"]), ("lance une playlist", ["lance", "une", "playlist"]), ("le un", ["le", "1"]),
        ("vingt et", ["20", "et"]), ("un cent", ["un", "100"]), ("zero", ["0"]), ("vingt zero", ["20", "0"]),
        ("cent vingt", ["120"]), ("deux mille", ["2000"]), ("mille mille", ["1000", "1000"]),
        ("vingt trente", ["20", "30"]), ("trente et deux", ["30", "et", "2"]), ("un mille", ["1000"]),
    ],
)  # fmt: skip
def test_nombres(mots: str, attendu: list[str]) -> None:
    assert nombres.convertir(mots.split()) == attendu


@pytest.mark.parametrize(
    ("texte", "secondes"),
    [
        ("10 minutes", 600), ("1 h 30", 5400), ("1 heure et demie", 5400), ("1 demi heure", 1800),
        ("1 quart d heure", 900), ("3 quarts d heure", 2700), ("2 minutes 30", 150), ("90 secondes", 90),
        ("1 minute et 30 secondes", 90), ("10", 600), ("de 5 minutes", 300), ("pour 25 min", 1500),
        ("2 heures", 7200), ("0 minute", None), ("30 heures", None), ("1.5 heure", 5400), ("5 minutes et demie", 330),
        ("bientot", None), ("10 bananes", None), ("", None), ("1 demi minute", 30), ("10 minutes stp", 600),
    ],
)  # fmt: skip
def test_durees(texte: str, secondes: int | None) -> None:
    assert durees.duree(texte) == secondes


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [("a 18 h", (18, 0)), ("a 18 h 30", (18, 30)), ("a 18 heures 15", (18, 15)), ("a midi", (12, 0)),
     ("a minuit et demie", (0, 30)), ("a 7 heures du soir", (19, 0)), ("a 25 h", None), ("a 18 h et demie", (18, 30)),
     ("a midi et demie", (12, 30)), ("a minuit", (0, 0)), ("demain", None), ("a 3 h de l apres midi", (15, 0)),
     ("a 9 h 75", None)],
)  # fmt: skip
def test_heures(texte: str, attendu: tuple[int, int] | None) -> None:
    assert durees.heure(texte) == attendu


def test_dire_une_duree() -> None:
    assert [durees.dire_duree(s) for s in (600, 5400, 45, 150, 3600, 7200, 1, 60)] == [
        "10 minutes", "1 h 30", "45 secondes", "2 minutes 30", "1 heure", "2 heures", "1 seconde", "1 minute",
    ]  # fmt: skip


# --- phonétique et ressemblance -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [("notion", "nocion"), ("zoom", "zoum"), ("calculette", "calculète"), ("whatsapp", "ouatsape"), ("teams", "tims"),
     ("slack", "slaque"), ("photos", "foto"), ("musique", "music"), ("messages", "message"), ("bureau", "buro")],
)  # fmt: skip
def test_meme_cle_phonetique(a: str, b: str) -> None:
    assert cle(a) == cle(b)


def test_ressemblance() -> None:
    def s(a: str, b: str) -> float:
        return similarite(Forme.de(a), Forme.de(b))

    assert s("notion", "notion") == 1.0 and s("vs code", "vscode") == 1.0
    assert s("monde", "le monde") == 0.99  # article en plus
    assert s("nocion", "notion") >= 0.9 and s("spotifaille", "spotifaille") == 1.0
    assert s("notes", "notion") < 0.8 and s("frigo", "le figaro") < 0.8 and s("garage", "garage band") < 0.8
    assert s("tv", "tg") == 0.0 and s("tv", "tv") == 1.0  # très court : exact ou rien
    assert s("", "x") == 0.0 and s("note", "notes") >= 0.8
    assert sans_articles("le le monde") == "monde" and sans_articles("le") == "le"
    assert forme_normale("L'App Store !") == "l app store"


# --- ambiguïtés --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Notion", ("choisi", 1)), ("l'app Notes", ("choisi", 0)), ("la deuxième", ("choisi", 1)),
        ("le premier", ("choisi", 0)), ("2", ("choisi", 1)), ("le 3", ("inconnu", None)),
        ("la dernière", ("choisi", 1)),
        ("aucun", ("abandon", None)), ("ni l'un ni l'autre", ("abandon", None)), ("non", ("abandon", None)),
        ("ouvre YouTube", ("inconnu", None)), ("", ("inconnu", None)), ("plutôt Notion", ("choisi", 1)),
        ("prends la première", ("choisi", 0)),
    ],
)  # fmt: skip
def test_choisir_entre_deux(texte: str, attendu: tuple[str, int | None]) -> None:
    assert ambiguite.choisir(texte, ["Notes", "Notion"]) == attendu


def test_choix_pas_plus_clair_que_la_question() -> None:
    assert ambiguite.choisir("nautes", ["Notes", "Note"]) == ("inconnu", None)
    assert ambiguite.choisir("note", ["Notes", "Note"]) == ("choisi", 1)  # dit exactement


def test_heure_de_rappel_le_lendemain() -> None:
    # « à 8 h » dit à 9 h : c'est demain.
    from outils import catalogue_reference as ref
    from voix.nlu.comprendre import Contexte, comprendre

    ctx = Contexte(ref.catalogue(), ref.commandes(), maintenant=lambda: datetime(2026, 10, 13, 9, 0))
    c = comprendre("rappelle-moi à 8 h d'appeler Paul", ctx)
    assert c.intention == "rappel.creer" and c.params["duree_s"] == 23 * 3600 and c.params["heure"] == "08:00"
    c = comprendre("rappelle-moi d'appeler Paul à 18 h 30", ctx)
    assert c.params["duree_s"] == 9 * 3600 + 1800 and c.params["message"] == "appeler paul"
