"""Le comportement de la compréhension, cas par cas : ambiguïtés, priorités, refus, négations, modules, rappels."""

from __future__ import annotations

from datetime import datetime

import pytest

from outils import catalogue_reference as ref
from voix.nlu.catalogue import Catalogue, Objet
from voix.nlu.comprendre import Contexte, comprendre, exemples, nettoyer_objet, suggestions
from voix.nlu.intentions import INTENTIONS, SENSIBLES, par_famille


@pytest.fixture(scope="module")
def ctx() -> Contexte:
    return Contexte(ref.catalogue(), ref.commandes(), maintenant=lambda: datetime(2026, 10, 13, 9, 0))


def nom(c: object) -> str:
    return getattr(c, "nom", "")


def test_liste_blanche() -> None:
    assert len(INTENTIONS) >= 60
    assert SENSIBLES == {"app.fermer_tout", "app.fermer_tout_sauf", "systeme.veille", "systeme.wifi_desactiver"}
    groupes = par_famille()
    assert sum(len(v) for v in groupes.values()) == len(INTENTIONS) and all(groupes.values())


def test_ambiguite_entre_deux_apps_proches() -> None:
    c = Catalogue([
        Objet("app", "Telegram", "/a/Telegram.app", "t1", ("telegram",)),
        Objet("app", "Telegraph", "/a/Telegraph.app", "t2", ("telegraph",)),
    ])  # fmt: skip
    r = comprendre("ouvre telegra", Contexte(c))
    assert r.statut == "ambigu" and r.raison == "Telegram ou Telegraph ?" and r.intention == "app.ouvrir"
    assert [x.libelle for x in r.choix] == ["Telegram", "Telegraph"]
    assert r.choix[1].comprehension.statut == "compris" and r.choix[1].comprehension.params["objet"].ident == "t2"
    # Dit exactement : pas d'hésitation.
    assert comprendre("ouvre telegram", Contexte(c)).statut == "compris"


def test_priorites_entre_genres(ctx: Contexte) -> None:
    assert comprendre("ouvre musique", ctx).intention == "app.ouvrir"  # l'app avant le dossier
    assert comprendre("ouvre le dossier musique", ctx).intention == "dossier.ouvrir"  # sauf si tu dis « dossier »
    assert nom(comprendre("ouvre gmail", ctx).params["objet"]) == "Gmail"  # « mail » ne gagne pas sur un nom exact
    assert comprendre("ouvre la compta", ctx).intention == "alias.ouvrir"
    assert comprendre("ouvre le site youtube", ctx).intention == "web.ouvrir_site"
    assert comprendre("va sur youtube", ctx).intention == "web.ouvrir_site"
    assert comprendre("montre-moi mes téléchargements", ctx).intention == "dossier.ouvrir"
    assert comprendre("ouvre l'app spotify", ctx).intention == "app.ouvrir"


def test_objet_inconnu_et_suggestions(ctx: Contexte) -> None:
    r = comprendre("ouvre spotifo", ctx)
    assert r.statut == "compris"  # assez proche
    r = comprendre("ouvre spoutnik", ctx)
    assert r.statut == "pas_compris" and r.raison == "objet inconnu"
    r = comprendre("Notion", ctx)
    assert r.statut == "pas_compris" and r.suggestions[0] == "ouvre Notion" and len(r.suggestions) == 3
    assert suggestions("", ctx) == [] and suggestions("zzzzzzzz", ctx) == []
    assert ("app.ouvrir", "ouvre Notion") in exemples(ctx)


@pytest.mark.parametrize(
    ("phrase", "statut", "raison"),
    [
        ("merci", "vide", "Avec plaisir"), ("", "vide", ""), ("euh", "vide", ""),
        ("ne ferme pas Safari", "negation", "D'accord, je ne fais rien."),
        ("ne mets pas en veille", "negation", "D'accord, je ne fais rien."),
        ("comment fermer une app qui ne répond pas", "pas_compris", "phrase négative"),
        ("éteins l'ordinateur", "refus", "Je ne fais pas ça, par sécurité."), ("redémarre", "refus", ""),
        ("supprime le fichier", "refus", ""), ("envoie un mail à Paul", "refus", ""),
        ("vide la corbeille", "refus", ""),
        ("achète des piles", "refus", ""), ("appelle maman", "refus", ""), ("écris à Paul", "refus", ""),
        ("volume à 150", "pas_compris", "le volume va de 0 à 100"), ("monte le son de 200", "pas_compris", ""),
        ("minuteur 30 heures", "pas_compris", "durée incomprise"), ("mode ninja", "pas_compris", "mode inconnu"),
        ("x" * 400, "pas_compris", "phrase trop longue pour une commande"),
    ],
)  # fmt: skip
def test_statuts(ctx: Contexte, phrase: str, statut: str, raison: str) -> None:
    r = comprendre(phrase, ctx)
    assert r.statut == statut, r
    if raison:
        assert r.raison == raison


def test_les_refus_et_negations_ne_portent_aucune_intention_d_action(ctx: Contexte) -> None:
    for p in ("éteins le Mac", "ne coupe pas le wifi", "supprime tout"):
        r = comprendre(p, ctx)
        assert r.intention in (None, "refus") and not r.params


def test_parametres(ctx: Contexte) -> None:
    def p(phrase: str) -> tuple[str | None, dict[str, object]]:
        r = comprendre(phrase, ctx)
        return r.intention, {k: (v.ident if hasattr(v, "ident") else v) for k, v in r.params.items()}

    assert p("volume à trente pour cent") == ("son.regler", {"niveau": 30})
    assert p("mets le son à fond") == ("son.regler", {"niveau": 100})
    assert p("monte un peu le son") == ("son.monter", {"pas": 5})
    assert p("baisse le son de 25") == ("son.baisser", {"pas": 25})
    assert p("minuteur une heure et demie") == ("minuteur.lancer", {"duree_s": 5400})
    assert p("préviens-moi dans 5 minutes") == ("minuteur.lancer", {"duree_s": 300})
    assert p("rappelle-moi dans 20 minutes de sortir le linge") == (
        "rappel.creer", {"duree_s": 1200, "message": "sortir le linge"})  # fmt: skip
    assert p("rappelle-moi dans un quart d'heure de partir à la gare") == (
        "rappel.creer", {"duree_s": 900, "message": "partir à la gare"})  # fmt: skip
    assert p("cherche le fichier mes billets") == ("fichier.chercher", {"requete": "billets"})
    assert p("cherche sur Google la révolution française") == (
        "web.chercher_google", {"requete": "la révolution française"})  # fmt: skip
    assert p("traduis bonjour") == ("web.traduire", {"texte": "bonjour", "langue": "en"})
    assert p("ouvre le deuxième") == ("fichier.ouvrir_resultat", {"rang": 2})
    assert p("ouvre le dernier") == ("fichier.ouvrir_resultat", {"rang": -1})
    assert p("montre le 3 dans le Finder") == ("fichier.reveler_resultat", {"rang": 3})
    assert p("ouvre le 25")[0] is None  # pas un rang : rien
    assert p("mets de la musique sur Spotify") == ("musique.lecture", {"lecteur": "spotify"})
    assert p("lance la playlist jazz du soir") == ("musique.playlist", {"objet": "spotify:Jazz du soir"})
    assert p("cache les autres") == ("app.cacher_autres", {})
    assert p("cache tout sauf Notion") == ("app.cacher_autres", {"objet": "notion.id"})


def test_routines(ctx: Contexte) -> None:
    r = comprendre("lance ma révision", ctx)
    assert r.intention == "routine.lancer" and r.params["objet"].nom == "révision"
    assert comprendre("lance ma revisions", ctx).intention == "routine.lancer"  # presque exact
    assert comprendre("lance la routine fin de journée", ctx).params["objet"].nom == "fin de journée"
    assert comprendre("je termine ma journée", ctx).intention == "routine.lancer"
    assert comprendre("lance la routine bidule", ctx).statut == "pas_compris"


def test_ambiance_installee_ou_non(ctx: Contexte) -> None:
    assert comprendre("mode concentration", ctx).intention == "concentration.activer"
    avec = Contexte(ctx.catalogue, ctx.commandes, modules=frozenset({"ambiance"}),
                    modes_ambiance={"code": "code", "concentration": "focus"})  # fmt: skip
    r = comprendre("mode concentration", avec)
    assert r.intention == "module.ambiance_mode" and r.params == {"mode": "focus"}
    assert comprendre("active la concentration", avec).intention == "concentration.activer"
    assert comprendre("mode sombre", avec).intention == "systeme.mode_sombre"
    assert comprendre("mode détente", avec).statut == "pas_compris"  # pas annoncé par cet Ambiance-là


def test_sensibles(ctx: Contexte) -> None:
    for p in ("ferme tout", "ferme tout sauf Safari", "mets en veille", "coupe le wifi"):
        assert comprendre(p, ctx).sensible
    for p in ("ouvre Safari", "volume à 30"):
        assert not comprendre(p, ctx).sensible
    assert not comprendre("blabla", ctx).sensible


def test_nettoyer_objet() -> None:
    assert nettoyer_objet("l app notes maintenant") == (["notes", "l app notes", "app notes"], "app")
    assert nettoyer_objet("le site youtube") == (["youtube", "le site youtube", "site youtube"], "site")
    assert nettoyer_objet("mes images") == (["mes images", "images"], None)


@pytest.mark.parametrize(
    "injection",
    ["ouvre ; rm -rf ~", "lance $(rm -rf /)", "ouvre `whoami`", "ferme && sudo reboot", "ouvre | sh",
     "ouvre ../../etc/passwd", "va sur javascript:alert(1)", "lance /bin/sh", "ouvre file:///etc/hosts"],
)  # fmt: skip
def test_injections_jamais_comprises(ctx: Contexte, injection: str) -> None:
    assert comprendre(injection, ctx).statut == "pas_compris"
