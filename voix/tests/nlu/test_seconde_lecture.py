"""La seconde lecture : questions par mots, sacs de mots, phrases remises dans l'ordre — et leurs garde-fous."""

from __future__ import annotations

from datetime import datetime

import pytest

from outils import catalogue_reference as ref
from voix.nlu import questions, sacs
from voix.nlu.comprendre import Contexte, comprendre
from voix.nlu.normalisation import normaliser


@pytest.fixture(scope="module")
def ctx() -> Contexte:
    return Contexte(ref.catalogue(), ref.commandes(), maintenant=lambda: datetime(2026, 10, 13, 9, 0))


def intention(phrase: str, ctx: Contexte) -> str | None:
    c = comprendre(phrase, ctx)
    return c.intention if c.statut == "compris" else None


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [("la batterie est à combien", "systeme.batterie"), ("c'est quoi la date d'aujourd'hui", "systeme.date"),
     ("c'est quoi le nom de cette chanson", "musique.titre"), ("le minuteur il en est où", "minuteur.restant"),
     ("quelle heure est-il à Tokyo", None), ("c'est quoi le menu du restaurant", None),
     ("la batterie de cuisine", None), ("c'est quoi ce son", None)],
)  # fmt: skip
def test_questions_par_mots(phrase: str, attendu: str | None) -> None:
    p = normaliser(phrase)
    assert questions.question(p.cles, p.question) == attendu


def test_question_annoncee_sans_mot_interrogatif() -> None:
    p = normaliser("dis-moi le volume")
    assert p.question and questions.question(p.cles, p.question) == "son.niveau"
    assert questions.question(p.cles) is None


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [("le son plus fort", "son.monter"), ("passe en sombre", "systeme.mode_sombre"),
     ("enlève le thème sombre", "systeme.mode_clair"), ("j'ai encore de la batterie", "systeme.batterie"),
     ("une autre chanson", "musique.suivant"), ("la batterie de mon téléphone est morte", None),
     ("volume 30", None), ("musique", None), ("monte dans le train", None)],
)  # fmt: skip
def test_sacs_de_mots(phrase: str, attendu: str | None) -> None:
    assert sacs.lire(normaliser(phrase).cles) == attendu


def test_oui_non_par_mots() -> None:
    assert sacs.oui_non(normaliser("ouais carrément").cles) == "controle.oui"
    assert sacs.oui_non(normaliser("non c'est pas la peine").cles) == "controle.non"
    assert sacs.oui_non(normaliser("oui non").cles) is None


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("Safari, ouvre-le", "app.ouvrir"),  # ordre inversé
        ("j'ai fini avec Excel, ferme-le", "app.fermer"),
        ("je m'en vais, verrouille le Mac", "systeme.verrouiller"),  # l'ordre est à la fin
        ("ouvre Teams pour la réunion", "app.ouvrir"),  # le but
        ("ferme Chrome il rame", "app.fermer"),  # une proposition de plus
        ("coupe le son, le bébé dort", "son.couper"),  # une fin sans liaison
        ("ouvre Excel le fichier des ventes", "app.ouvrir"),  # le nom exact, puis une fin
        ("ouvre Safari non Chrome", "app.ouvrir"),  # l'auto-correction
        ("dans une heure rappelle-moi d'appeler Marc", "rappel.creer"),
        ("garde que Word et cache le reste", "app.cacher_autres"),
    ],
)
def test_remises_dans_l_ordre(ctx: Contexte, phrase: str, attendu: str) -> None:
    assert intention(phrase, ctx) == attendu


def test_l_auto_correction_retient_le_second_nom(ctx: Contexte) -> None:
    assert comprendre("ouvre Safari non Chrome", ctx).params["objet"].nom == "Google Chrome"


@pytest.mark.parametrize(
    "phrase",
    [
        "ouvre Safari je veux pas",  # une négation dans la fin coupée
        "j'ai cherché partout",  # un participe, pas un ordre
        "va chercher le pain",  # aller + infinitif
        "le mode sombre c'est joli",  # un avis
        "monte le son de la guitare",  # un complément, pas une fin
        "mets la musique dans la voiture",
        "ouvre le dossier secret de la NASA",  # un nom commun seul ne désigne rien
        "joue aux cartes",  # jouer à quelque chose
        "quelle heure est-il à Tokyo",  # « il » est le sujet inversé
        "d'accord je vois",  # une réponse se dit franchement
        "traduis-moi ton silence",
        "cherche dans le placard",
    ],
)
def test_garde_fous_rien_n_est_fait(ctx: Contexte, phrase: str) -> None:
    assert comprendre(phrase, ctx).statut in ("pas_compris", "vide", "negation")
