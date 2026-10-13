"""§9.3 : chaque intention produit exactement la commande attendue (programme et arguments), ou l'ordre attendu vers
l'app — vérifié sur de faux exécutables qui notent tout."""

from __future__ import annotations

from typing import Any

import pytest

from tests.faux_mac import FauxMac
from voix.actions.registre import ACTIONS
from voix.nlu.intentions import INTENTIONS
from voix.session import Session

LIRE_VOLUME = ["-e", "set v to get volume settings",
               "-e", 'return ((output volume of v) as text) & "," & ((output muted of v) as text)']  # fmt: skip
REGLER = ["-e", "on run argv", "-e", "set volume output volume ((item 1 of argv) as integer)", "-e", "end run"]
OUI = object()  # la phrase demande une confirmation : on répond « oui »

# phrase → (appels attendus [(programme, arguments)], ordres attendus vers l'app [(ordre, paramètres)])
# « {M} » est remplacé par la maison du faux Mac.
ATTENDUS: list[tuple[str, list[tuple[str, list[str]]], list[tuple[str, dict[str, Any]]]]] = [
    ("ouvre Notion", [("open", ["-b", "notion.id"])], []),
    ("va sur Slack", [("open", ["-b", "com.tinyspeck.slackmacgap"])], []),
    ("ferme Spotify", [], [("app.quitter", {"bundle": "com.spotify.client"})]),
    ("cache Discord", [], [("app.cacher", {"bundle": "com.hnc.Discord"})]),
    ("cache les autres", [], [("app.cacher_autres", {})]),
    ("cache tout sauf Notion", [], [("app.cacher_autres", {"sauf": "notion.id"})]),
    ("ouvre mes téléchargements", [("open", ["{M}/Downloads"])], []),
    ("ouvre la compta", [("open", ["{M}/Documents/Compta.numbers"])], []),
    ("ouvre YouTube", [("open", ["https://www.youtube.com"])], []),
    (
        "cherche sur Google crêpes & cidre ; rm -rf",
        [("open", ["https://www.google.fr/search?q=cr%C3%AApes+%26+cidre+rm+rf"])],
        [],
    ),
    (
        "cherche sur YouTube un tuto python",
        [("open", ["https://www.youtube.com/results?search_query=un+tuto+python"])],
        [],
    ),
    ("cherche Victor Hugo sur Wikipédia", [("open", ["https://fr.wikipedia.org/w/index.php?search=victor+hugo"])], []),
    ("itinéraire vers la gare de Lyon", [("open", ["https://maps.apple.com/?q=la+gare+de+lyon"])], []),
    (
        "traduis bonjour en espagnol",
        [("open", ["https://translate.google.fr/?sl=fr&tl=es&text=bonjour&op=translate"])],
        [],
    ),
    ("volume à 30", [("osascript", LIRE_VOLUME), ("osascript", [*REGLER, "30"])], []),
    ("monte le son de 20", [("osascript", LIRE_VOLUME), ("osascript", [*REGLER, "65"])], []),
    ("baisse un peu le son", [("osascript", LIRE_VOLUME), ("osascript", [*REGLER, "40"])], []),
    ("coupe le son", [("osascript", LIRE_VOLUME), ("osascript", ["-e", "set volume with output muted"])], []),
    ("remets le son", [("osascript", LIRE_VOLUME), ("osascript", ["-e", "set volume without output muted"])], []),
    ("quel est le volume", [("osascript", LIRE_VOLUME)], []),
    ("mets de la musique sur Spotify", [], [("musique.lecture", {"lecteur": "spotify"})]),
    ("pause", [], [("musique.pause", {})]),
    ("chanson suivante", [], [("musique.suivant", {})]),
    ("chanson précédente", [], [("musique.precedent", {})]),
    ("c'est quoi cette chanson", [], [("musique.titre", {})]),
    (
        "lance la playlist jazz du soir",
        [],
        [("musique.playlist", {"lecteur": "spotify", "playlist": "spotify:playlist:37i9dQZF1DXbITWG1ZJKYt"})],
    ),
    ("lance la playlist révisions", [], [("musique.playlist", {"lecteur": "musique", "playlist": "Révisions"})]),
    ("verrouille l'écran", [], [("ecran.verrouiller", {})]),
    ("éteins l'écran", [("pmset", ["displaysleepnow"])], []),
    ("mode sombre", [("defaults", ["read", "-g", "AppleInterfaceStyle"])], [("apparence.regler", {"sombre": True})]),
    ("mode clair", [("defaults", ["read", "-g", "AppleInterfaceStyle"])], [("apparence.regler", {"sombre": False})]),
    (
        "active le wifi",
        [
            ("networksetup", ["-listallhardwareports"]),
            ("networksetup", ["-getairportpower", "en0"]),
            ("networksetup", ["-setairportpower", "en0", "on"]),
        ],
        [],
    ),
    ("état de la batterie", [("pmset", ["-g", "batt"])], []),
    ("quelle heure est-il", [], []),
    ("on est quel jour", [], []),
    ("la météo", [("open", ["-b", "com.apple.weather"])], []),
    ("active la concentration", [("shortcuts", ["run", "Activer concentration"])], []),
    ("mode concentration", [("ambiance", ["mode", "focus"])], []),
    ("désactive le mode concentration", [("shortcuts", ["run", "Désactiver concentration"])], []),
    ("minuteur 10 minutes", [], []),
    ("rappelle-moi dans 20 minutes de sortir le linge", [], []),
    ("lance le raccourci heure du café", [("shortcuts", ["run", "Heure du café"])], []),
    ("quels sont mes raccourcis", [], []),
    ("lance ma révision", [("open", ["-b", "notion.id"])], []),
    ("ouvre le tableau de bord", [("tableau", ["ouvrir"])], []),
    ("comment vont mes modules", [("tableau", ["etat"])], []),
    ("nouveau mood", [("ambiance", ["mood"])], []),
    ("menu de la semaine", [("quotidien", ["menu"])], []),
    ("vérifie le presse-papiers", [("bouclier", ["verifier", "--presse-papiers"])], []),
    ("cherche le fichier facture", [("mdfind", ["-onlyin", "{M}", "-name", "facture"])], []),
    ("ouvre le dernier PDF", [], []),
    ("ouvre le dernier fichier téléchargé", [], []),
    ("éteins le Mac", [], []),
]
CONFIRMES = [
    ("mets le Mac en veille", [("pmset", ["sleepnow"])], []),
    ("ferme tout", [], [("app.quitter_tout", {})]),
    ("ferme tout sauf Safari", [], [("app.quitter_tout", {"sauf": "com.apple.Safari"})]),
    (
        "coupe le wifi",
        [
            ("networksetup", ["-listallhardwareports"]),
            ("networksetup", ["-getairportpower", "en0"]),
            ("networksetup", ["-setairportpower", "en0", "off"]),
        ],
        [],
    ),
    ("fin de journée", [], [("app.quitter_tout", {})]),
]


def _maison(appels: list[tuple[str, list[str]]], mac: FauxMac) -> list[tuple[str, list[str]]]:
    return [(p, [a.replace("{M}", str(mac.maison)) for a in args]) for p, args in appels]


@pytest.mark.parametrize(("phrase", "appels", "ordres"), ATTENDUS, ids=[a[0] for a in ATTENDUS])
def test_commande_exacte(mac: FauxMac, phrase: str, appels: list[tuple[str, list[str]]],
                         ordres: list[tuple[str, dict[str, Any]]]) -> None:  # fmt: skip
    s = Session(mac.outils(modules={"tableau": "", "ambiance": "", "quotidien": "", "bouclier": ""}))
    r = s.entendre(phrase)
    assert r.statut in ("fait", "info", "refus"), r
    assert mac.appels() == _maison(appels, mac)
    assert mac.pont.ordres == ordres


@pytest.mark.parametrize(("phrase", "appels", "ordres"), CONFIRMES, ids=[a[0] for a in CONFIRMES])
def test_commande_exacte_apres_confirmation(mac: FauxMac, phrase: str, appels: list[tuple[str, list[str]]],
                                            ordres: list[tuple[str, dict[str, Any]]]) -> None:  # fmt: skip
    s = Session(mac.outils())
    assert s.entendre(phrase).statut == "question"
    assert mac.appels() == [] and mac.pont.ordres == []  # rien avant le « oui »
    assert s.entendre("oui").statut == "fait"
    assert mac.appels() == _maison(appels, mac)
    assert mac.pont.ordres == ordres


def test_chaque_intention_a_une_action_et_un_cas() -> None:
    assert set(ACTIONS) == set(INTENTIONS)


def test_reponses(mac: FauxMac) -> None:
    s = Session(mac.outils())
    assert s.entendre("ouvre Notion").texte == "✓ Notion ouvert"
    assert s.entendre("quelle heure est-il").texte == "Il est 9 h 00."
    assert s.entendre("on est quel jour").texte == "Nous sommes le mardi 13 octobre 2026."
    assert s.entendre("éteins le Mac").texte == "Je ne fais pas ça, par sécurité."
    assert s.entendre("ne ferme pas Safari").texte == "D'accord, je ne fais rien."
    r = s.entendre("ouvre spoutnik")
    assert r.statut == "incompris" and r.texte == "Je n'ai pas compris."
    assert s.entendre("merci").statut == "rien"


def test_batterie_et_titre(mac: FauxMac) -> None:
    mac.regler(batt="Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t76%; discharging; 4:12 remaining")
    s = Session(mac.outils())
    assert s.entendre("état de la batterie").texte == "Batterie à 76 %, sur batterie, environ 4 h 12 restantes."
    mac.pont.donnees["musique.titre"] = {"titre": "So What", "artiste": "Miles Davis"}
    assert s.entendre("c'est quoi cette chanson").texte == "« So What », Miles Davis"


def test_l_app_absente_le_dit(mac: FauxMac) -> None:
    from voix.actions.pont import PontAbsent

    s = Session(mac.outils(pont=PontAbsent()))
    r = s.entendre("ferme Spotify")
    assert r.statut == "erreur" and "n'est pas lancée" in r.texte


def test_un_programme_qui_echoue(mac: FauxMac) -> None:
    mac.regler(codes={"open": 1})
    r = Session(mac.outils()).entendre("ouvre Notion")
    assert r.statut == "erreur" and r.texte == "Notion n'a pas pu s'ouvrir."


def test_repeter_stop_aide_silence(mac: FauxMac) -> None:
    s = Session(mac.outils())
    assert s.entendre("répète").texte == "Je n'ai encore rien dit."
    s.entendre("quelle heure est-il")
    assert s.entendre("répète").texte == "Il est 9 h 00."
    assert s.entendre("stop").statut == "stop"
    assert s.entendre("qu'est-ce que je peux dire").statut == "info"  # pas encore d'aide-mémoire
    assert s.entendre("mode silencieux").texte == "✓ Je ne parle plus" and not s.etat.parler
    assert s.entendre("tu peux parler").texte == "✓ Je te réponds à voix haute" and s.etat.parler
    assert s.entendre("arrête de m'écouter").texte == "✓ Écoute en pause"
    assert mac.pont.ordres[-1] == ("ecoute.pause", {})
    assert s.entendre("oui").texte == "Il n'y a rien à confirmer."


def test_aide_memoire_ouverte(mac: FauxMac) -> None:
    o = mac.outils()
    o.chemins.aide_memoire.parent.mkdir(parents=True)
    o.chemins.aide_memoire.write_text("<html></html>")
    assert Session(o).entendre("aide").texte == "✓ Aide-mémoire ouvert"
    assert mac.appels() == [("open", [str(o.chemins.aide_memoire)])]


def test_ambiguite_par_la_voix(mac: FauxMac) -> None:
    from voix.nlu.catalogue import Catalogue, Objet

    o = mac.outils(catalogue=Catalogue([Objet("app", "Telegram", "/a/Telegram.app", "ru.keepcoder.Telegram",
                                              ("telegram",)), Objet("app", "Telegraph", "/a/T.app", "com.ex.telegraph",
                                                                    ("telegraph",))]))  # fmt: skip
    s = Session(o)
    r = s.entendre("ouvre telegra")
    assert r.statut == "choix" and r.donnees["choix"] == ["Telegram", "Telegraph"]
    assert s.entendre("la deuxième").texte == "✓ Telegraph ouvert"
    assert mac.appels() == [("open", ["-b", "com.ex.telegraph"])]
    s.entendre("ouvre telegra")
    assert s.entendre("aucun").texte == "D'accord, je ne fais rien."
    s.entendre("ouvre telegra")
    assert s.entendre("quelle heure est-il").texte == "Il est 9 h 00."  # pas un choix : une nouvelle commande
