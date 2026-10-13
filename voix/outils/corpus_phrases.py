"""Le corpus de phrases (§9.1) : des formulations générées pour chaque intention, et des phrases hors catalogue.

- Chaque intention a ses tournures (impératif, infinitif, question polie, familier) ; on y ajoute, au hasard (graine
  fixe), de la politesse, des hésitations, la casse et la ponctuation d'une transcription, des fautes réalistes
  (homophones, élisions ratées), des nombres en lettres ou en chiffres, des noms d'apps déformés.
- Les phrases hors catalogue (≥ 300) doivent toutes donner « pas compris » : jamais d'action.
Les jeux 2 à 8 (`corpus_phrases_2.py` … `corpus_phrases_8.py`) sont écrits à la main, chacun passé une seule fois à
neuf (la mesure anti-triche, DECISIONS D-13) avant de servir au réglage.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any

from outils import catalogue_reference as ref
from voix.nlu.catalogue import Objet

GRAINE = 20261013


@dataclass
class Cas:
    phrase: str
    intention: str | None  # None : hors catalogue (attendu : pas compris)
    params: dict[str, Any] = field(default_factory=dict)
    statut: str = "compris"


# --- nombres en lettres -----------------------------------------------------------------------------------------------

_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
           "treize", "quatorze", "quinze", "seize"]  # fmt: skip
_DIZAINES = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}


def en_lettres(n: int) -> str:
    if n < 17:
        return _UNITES[n]
    if n < 20:
        return f"dix-{_UNITES[n - 10]}"
    if n == 100:
        return "cent"
    if n < 70:
        d, u = divmod(n, 10)
        base = _DIZAINES[d * 10]
        return base if u == 0 else f"{base} et un" if u == 1 else f"{base}-{_UNITES[u]}"
    if n < 80:
        reste = n - 60
        return "soixante et onze" if reste == 11 else f"soixante-{en_lettres(reste)}"
    reste = n - 80
    return "quatre-vingts" if reste == 0 else f"quatre-vingt-{en_lettres(reste)}"


# --- déformations ---------------------------------------------------------------------------------------------------


def deformer(nom: str, r: random.Random) -> str:
    """Une déformation légère d'un nom (≥ 6 lettres) comme en produit une transcription : une lettre doublée, une
    voyelle changée, un e final ajouté ou retiré."""
    if len(nom) < 6 or " " in nom:
        return nom
    choix = r.choice(["double", "final", "voyelle"])
    if choix == "double":
        i = r.randrange(1, len(nom) - 1)
        if nom[i].isalpha():
            return nom[: i + 1] + nom[i] + nom[i + 1 :]
    if choix == "final":
        return nom[:-1] if nom.endswith("e") else nom + "e"
    voyelles = {"a": "e", "e": "é", "o": "au", "i": "y", "é": "e"}
    positions = [i for i, c in enumerate(nom[1:], 1) if c in voyelles]
    if positions:
        i = r.choice(positions)
        return nom[:i] + voyelles[nom[i]] + nom[i + 1 :]
    return nom


POLITESSE_AVANT = [
    "tu peux ", "est-ce que tu peux ", "peux-tu ", "s'il te plaît ", "hé ", "ok ", "euh ", "alors ", "dis ",
    "tu pourrais ", "j'aimerais que tu ", "est-ce que tu pourrais ", "vas-y ", "bon ", "allez ",
]  # fmt: skip
POLITESSE_APRES = [" s'il te plaît", " stp", " merci", " s'il te plait", " svp", " merci beaucoup"]


def infinitif(phrase: str) -> str:
    """« ouvre Notion » → « ouvrir Notion » (après « tu peux… »)."""
    mots = phrase.split(" ", 1)
    table = {
        "ouvre": "ouvrir", "lance": "lancer", "ferme": "fermer", "quitte": "quitter", "cache": "cacher",
        "mets": "mettre", "monte": "monter", "baisse": "baisser", "coupe": "couper", "active": "activer",
        "désactive": "désactiver", "cherche": "chercher", "passe": "passer", "va": "aller", "verrouille": "verrouiller",
        "remets": "remettre", "joue": "jouer", "démarre": "démarrer", "affiche": "afficher", "montre": "montrer",
        "traduis": "traduire", "rappelle-moi": "me rappeler", "allume": "allumer", "éteins": "éteindre",
        "règle": "régler", "trouve": "trouver", "augmente": "augmenter", "diminue": "diminuer", "annule": "annuler",
        "répète": "répéter", "bascule": "basculer", "arrête": "arrêter", "recherche": "rechercher",
    }  # fmt: skip
    if mots[0] in table:
        return table[mots[0]] + (" " + mots[1] if len(mots) > 1 else "")
    return phrase


HOMOPHONES = [
    (r"\bouvre\b", "ouvres"), (r"\bouvre\b", "ouvrent"), (r"\bmets\b", "met"), (r"\bmets\b", "mais"),
    (r"\bferme\b", "fermes"), (r"\blance\b", "lances"), (r"\bà\b", "a"), (r"\bl'app\b", "la app"),
    (r"\bl'écran\b", "l écran"), (r"\bd'écran\b", "d écran"), (r"\bcoupe\b", "coupes"), (r"\bmonte\b", "montes"),
    (r"\bbaisse\b", "baisses"), (r"\bquitte\b", "quittes"), (r"\bé", "e"), (r"è", "e"), (r"ê", "e"), (r"ç", "c"),
    (r"\bminuteur\b", "minuteurs"), (r"\bcherche\b", "cherches"), (r"\bl'heure\b", "l heure"),
]  # fmt: skip


def bruiter(phrase: str, r: random.Random, polie: bool = True) -> str:
    """Politesse, hésitations, fautes réalistes, casse et ponctuation de transcription."""
    p = phrase
    if polie and r.random() < 0.35:
        avant = r.choice(POLITESSE_AVANT)
        if avant.strip() in ("tu peux", "est-ce que tu peux", "peux-tu", "tu pourrais", "j'aimerais que tu",
                             "est-ce que tu pourrais"):  # fmt: skip
            p = infinitif(p)
        p = avant + p
    if polie and r.random() < 0.2:
        p += r.choice(POLITESSE_APRES)
    if r.random() < 0.25:
        motif, remplacement = r.choice(HOMOPHONES)
        p = re.sub(motif, remplacement, p, count=1)
    style = r.random()
    if style < 0.45:
        p = p[0].upper() + p[1:] + r.choice([".", ".", " !", " ?", ""])
    elif style < 0.6:
        p = " " + p[0].upper() + p[1:] + "."
    elif style < 0.7:
        p = p.upper() if len(p) < 25 else p
    return p


# --- les tournures par intention -----------------------------------------------------------------------------------

DUREES = [
    ("10 minutes", 600), ("dix minutes", 600), ("5 min", 300), ("cinq minutes", 300), ("1 heure", 3600),
    ("une heure", 3600), ("30 secondes", 30), ("trente secondes", 30), ("1h30", 5400), ("une heure et demie", 5400),
    ("une demi-heure", 1800), ("un quart d'heure", 900), ("2 minutes 30", 150), ("deux minutes", 120),
    ("vingt-cinq minutes", 1500), ("45 minutes", 2700), ("trois quarts d'heure", 2700), ("90 secondes", 90),
    ("une minute", 60), ("12 minutes", 720), ("quarante minutes", 2400), ("2 heures", 7200), ("15 min", 900),
]  # fmt: skip
MESSAGES = ["sortir le linge", "appeler maman", "prendre mes médicaments", "regarder le four", "arroser les plantes",
            "partir à la gare", "rappeler le plombier", "faire une pause", "envoyer le dossier à Paul",
            "boire de l'eau", "vérifier la lessive", "sortir les poubelles"]  # fmt: skip
REQUETES = ["recette de crêpes", "horaires de la piscine", "meilleur film de 2024", "prix du gazole", "météo à Lyon",
            "comment faire un nœud de cravate", "traduction de chat en anglais", "concert de jazz", "cours de guitare",
            "résultats du match", "tarte aux pommes", "trajet Paris Lyon", "Victor Hugo", "la révolution française",
            "les volcans d'Auvergne"]  # fmt: skip
FICHIERS = ["facture Fnac", "contrat de location", "devis cuisine", "attestation CAF", "relevé de notes", "billet de train",
            "ordonnance", "bulletin de salaire", "quittance de loyer", "photos de vacances"]  # fmt: skip
LIEUX = ["la gare de Lyon", "la tour Eiffel", "la mairie", "Bordeaux", "le parc de la Tête d'Or", "l'aéroport"]


def _objets(genre: str) -> list[Objet]:
    return [o for o in CATALOGUE.objets if o.genre == genre]


CATALOGUE = ref.catalogue()


def _dit(o: Objet, r: random.Random, deformation: float = 0.15) -> str:
    """Une façon de dire l'objet : son nom, ou une de ses formes parlées, parfois déformée."""
    candidates = [*([o.nom] if "(" not in o.nom else []), *o.formes]
    dit = r.choice(candidates)
    dit = re.sub(r"\s*\(.*\)$", "", dit)  # « Musique (dossier) » → « Musique »
    if r.random() < deformation:
        dit = deformer(dit, r)
    return dit


def generer(n_par_intention: int = 30, fois: int = 3, graine: int = GRAINE) -> list[Cas]:  # noqa: C901 - une table
    r = random.Random(graine)
    cas: list[Cas] = []

    def ajouter(phrase: str, intention: str | None, statut: str = "compris", polie: bool = True, **params: Any) -> None:
        # Chaque tournure, plusieurs fois, avec un bruit différent (les doublons exacts sont retirés à la fin).
        for _ in range(fois):
            cas.append(Cas(bruiter(phrase, r, polie), intention, params, statut))

    apps = [o for o in _objets("app") if o.ident != "com.example.Inconnue"]
    sites = _objets("site")
    dossiers = [o for o in _objets("dossier") if o.ident not in ("~/Music", "/Applications")]
    # Apps, en variant les tournures.
    for _ in range(n_par_intention * 2):
        o = r.choice(apps)
        v = r.choice(["ouvre {x}", "lance {x}", "démarre {x}", "ouvre l'app {x}", "ouvre-moi {x}", "lance l'application {x}",
                      "ouvre {x} pour moi", "lance {x} maintenant"])  # fmt: skip
        ajouter(v.format(x=_dit(o, r)), "app.ouvrir", objet=o.ident)
    for _ in range(n_par_intention):
        o = r.choice(apps)
        v = r.choice(["ferme {x}", "quitte {x}", "ferme l'app {x}", "quitte l'application {x}", "fermer {x}"])
        ajouter(v.format(x=_dit(o, r)), "app.fermer", objet=o.ident)
    for _ in range(n_par_intention // 2):
        o = r.choice(apps)
        ajouter(r.choice(["cache {x}", "masque {x}", "cache l'app {x}"]).format(x=_dit(o, r)), "app.cacher",
                objet=o.ident)  # fmt: skip
    for _ in range(n_par_intention // 2):
        o = r.choice(apps)
        v = r.choice(
            ["va sur {x}", "passe sur {x}", "bascule sur {x}", "montre-moi {x}", "affiche {x}", "reviens sur {x}"]
        )
        ajouter(v.format(x=_dit(o, r)), "app.afficher", objet=o.ident)
    for _ in range(6):
        o = r.choice(apps)
        ajouter(r.choice(["cache tout sauf {x}", "cache les autres sauf {x}"]).format(x=_dit(o, r, 0)),
                "app.cacher_autres", objet=o.ident)  # fmt: skip
    for p in ["cache les autres", "cache toutes les autres apps", "cache les autres applications"]:
        ajouter(p, "app.cacher_autres")
    for p in ["ferme tout", "quitte toutes les apps", "ferme toutes les applications", "ferme tout ce qui est ouvert",
              "quitte tout", "ferme tous les programmes", "fermer toutes les applis"]:  # fmt: skip
        ajouter(p, "app.fermer_tout")
    for _ in range(10):
        o = r.choice(apps)
        v = r.choice(["ferme tout sauf {x}", "quitte tout sauf {x}", "ferme toutes les apps sauf {x}",
                      "ferme tout à part {x}"])  # fmt: skip
        ajouter(v.format(x=_dit(o, r, 0)), "app.fermer_tout_sauf", objet=o.ident)

    # Fichiers et dossiers.
    for _ in range(n_par_intention):
        o = r.choice(dossiers)
        v = r.choice(["ouvre {x}", "ouvre le dossier {x}", "montre-moi {x}", "va dans {x}", "affiche {x}",
                      "ouvre mon dossier {x}"])  # fmt: skip
        dit = r.choice(o.formes)
        ajouter(v.format(x=dit), "dossier.ouvrir", objet=o.ident)
    for p in ["ouvre mon dernier PDF", "ouvre le dernier PDF", "affiche mon dernier pdf", "ouvre le PDF le plus récent",
              "ouvre mon dernier fichier PDF", "montre-moi mon dernier PDF"]:  # fmt: skip
        ajouter(p, "fichier.dernier_pdf")
    for p in ["ouvre le dernier fichier téléchargé", "ouvre mon dernier téléchargement", "ouvre le fichier que je viens de "
              "télécharger", "ouvre ce que je viens de télécharger", "affiche le dernier téléchargement",
              "ouvre le dernier document téléchargé"]:  # fmt: skip
        ajouter(p, "fichier.dernier_telecharge")
    for p in ["ouvre ma dernière capture d'écran", "ouvre la dernière capture", "montre ma dernière capture d'écran",
              "affiche la dernière capture d'écran", "ouvre ma dernière capture"]:  # fmt: skip
        ajouter(p, "fichier.derniere_capture")
    for f in FICHIERS:
        v = r.choice(["cherche {x}", "trouve {x}", "cherche le fichier {x}", "recherche {x}", "trouve-moi {x}",
                      "cherche {x} dans mes fichiers", "cherche le document {x}"])  # fmt: skip
        ajouter(v.format(x=f), "fichier.chercher", requete=f)
        ajouter(f"cherche {f}", "fichier.chercher", polie=False, requete=f)
    for n, mots in [(1, ["le premier", "le 1", "le numéro 1"]), (2, ["le deuxième", "le 2", "le second"]),
                    (3, ["le troisième", "le 3", "le numéro trois"]), (4, ["le quatrième", "le 4"])]:  # fmt: skip
        for m in mots:
            ajouter(r.choice(["ouvre {x}", "{x}", "prends {x}", "ouvre {x} résultat"]).format(x=m),
                    "fichier.ouvrir_resultat", rang=n)  # fmt: skip
    for p, n in [("montre le 2 dans le Finder", 2), ("affiche le premier dans le Finder", 1),
                 ("montre le troisième dans le Finder", 3)]:  # fmt: skip
        ajouter(p, "fichier.reveler_resultat", rang=n)
    for o in _objets("alias"):
        for _ in range(4):
            ajouter(r.choice(["ouvre {x}", "lance {x}", "montre-moi {x}"]).format(x=r.choice(o.formes)), "alias.ouvrir",
                    objet=o.ident)  # fmt: skip

    # Web.
    for _ in range(n_par_intention * 2):
        o = r.choice(sites)
        v = r.choice(["ouvre {x}", "va sur {x}", "ouvre le site {x}", "lance {x}", "affiche {x}", "va sur le site {x}"])
        ajouter(v.format(x=_dit(o, r, 0.1)), "web.ouvrir_site", objet=o.ident)
    for q in REQUETES:
        v = r.choice(["cherche sur Google {q}", "cherche {q} sur Google", "google {q}", "recherche {q} sur internet",
                      "fais une recherche sur {q}", "cherche sur internet {q}"])  # fmt: skip
        ajouter(v.format(q=q), "web.chercher_google", requete=q)
    for q in REQUETES[:12]:
        v = r.choice(["cherche sur YouTube {q}", "cherche {q} sur YouTube", "mets {q} sur YouTube"])
        ajouter(v.format(q=q), "web.chercher_youtube", requete=q)
    for q in ["Victor Hugo", "la tour Eiffel", "Marie Curie", "le Mont-Blanc", "la photosynthèse", "Napoléon",
              "les dinosaures", "le jazz", "Bordeaux", "la Seconde Guerre mondiale"]:  # fmt: skip
        v = r.choice(["cherche {q} sur Wikipédia", "cherche sur Wikipédia {q}", "recherche {q} sur wiki"])
        ajouter(v.format(q=q), "web.chercher_wikipedia", requete=q)
    for lieu in LIEUX:
        v = r.choice(["itinéraire vers {q}", "montre {q} sur Plans", "comment aller à {q}", "cherche {q} sur la carte",
                      "trajet vers {q}"])  # fmt: skip
        ajouter(v.format(q=lieu), "web.chercher_plans", requete=lieu)
    for texte, langue, code in [("bonjour", "anglais", "en"), ("merci beaucoup", "espagnol", "es"),
                                ("où est la gare", "allemand", "de"), ("je t'aime", "italien", "it"),
                                ("bonne nuit", "anglais", "en"), ("à demain", "portugais", "pt"),
                                ("le chat dort", "anglais", "en"), ("bon appétit", "japonais", "ja")]:  # fmt: skip
        v = r.choice(["traduis {t} en {l}", "comment on dit {t} en {l}", "traduire {t} en {l}"])
        ajouter(v.format(t=texte, l=langue), "web.traduire", texte=texte, langue=code)

    # Son et musique.
    for _ in range(n_par_intention * 2):
        n = r.choice([0, 5, 10, 15, 20, 25, 30, 33, 40, 45, 50, 60, 66, 70, 75, 80, 90, 95, 100])
        dit = str(n) if r.random() < 0.5 else en_lettres(n)
        pourcent = r.choice([" %", "%", " pour cent", "", " pourcent"])
        v = r.choice(["volume à {n}{p}", "mets le volume à {n}{p}", "mets le son à {n}{p}", "règle le volume sur {n}{p}",
                      "son à {n}{p}", "volume {n}{p}", "passe le volume à {n}{p}", "baisse le son à {n}{p}",
                      "monte le volume à {n}{p}"])  # fmt: skip
        ajouter(v.format(n=dit, p=pourcent), "son.regler", niveau=n)
    for p, n in [("mets le son à fond", 100), ("volume au maximum", 100), ("monte le son à fond", 100),
                 ("volume au minimum", 0), ("mets le volume à la moitié", 50), ("son au max", 100)]:  # fmt: skip
        ajouter(p, "son.regler", niveau=n)
    for p, pas in [("monte le son", 10), ("plus fort", 10), ("augmente le volume", 10), ("monte le volume", 10),
                   ("monte le son un peu", 5), ("monte un peu le son", 5), ("augmente le son de 20", 20),
                   ("monte le son de vingt", 20), ("un peu plus fort", 5), ("monte le son beaucoup", 20),
                   ("monte", 10), ("augmente le volume de 15 %", 15), ("encore plus fort", 10)]:  # fmt: skip
        ajouter(p, "son.monter", pas=pas)
    for p, pas in [("baisse le son", 10), ("moins fort", 10), ("diminue le volume", 10), ("baisse le volume", 10),
                   ("baisse le son un peu", 5), ("baisse le son de 20", 20), ("baisse le son de dix", 10),
                   ("un peu moins fort", 5), ("baisse", 10), ("diminue le son de 30 %", 30), ("plus bas", 10),
                   ("baisse la musique", 10)]:  # fmt: skip
        ajouter(p, "son.baisser", pas=pas)
    for p in ["coupe le son", "coupe le volume", "mute", "mets en sourdine", "désactive le son", "coupe les sons",
              "éteins le son", "coupe tout le son", "sourdine"]:  # fmt: skip
        ajouter(p, "son.couper")
    for p in ["remets le son", "réactive le son", "rallume le son", "enlève la sourdine", "remets le volume",
              "active le son", "désactive la sourdine"]:  # fmt: skip
        ajouter(p, "son.remettre")
    for p in ["quel est le volume", "le volume est à combien", "c'est quoi le volume", "à combien est le volume"]:
        ajouter(p, "son.niveau")
    for p in ["lecture", "joue de la musique", "mets la musique", "lance la musique", "reprends la musique", "play",
              "mets de la musique", "remets la musique", "joue la musique", "relance la musique"]:  # fmt: skip
        ajouter(p, "musique.lecture")
    for p, lecteur in [("mets de la musique sur Spotify", "spotify"), ("lance la musique sur Spotify", "spotify"),
                       ("joue de la musique avec Musique", "musique")]:  # fmt: skip
        ajouter(p, "musique.lecture", lecteur=lecteur)
    for p in ["pause", "mets en pause", "mets la musique en pause", "arrête la musique", "stop la musique",
              "pause la musique", "coupe la musique", "mets pause", "arrête la chanson"]:  # fmt: skip
        ajouter(p, "musique.pause")
    for p in ["suivant", "chanson suivante", "morceau suivant", "passe à la suivante", "next", "titre suivant",
              "passe à la chanson suivante", "zappe cette chanson", "la suivante"]:  # fmt: skip
        ajouter(p, "musique.suivant")
    for p in ["précédent", "chanson précédente", "morceau précédent", "titre précédent", "reviens à la chanson précédente",
              "remets la chanson d'avant", "la précédente"]:  # fmt: skip
        ajouter(p, "musique.precedent")
    for p in ["c'est quoi cette chanson", "quelle est cette chanson", "qu'est-ce qui passe", "c'est quoi ce morceau",
              "qui chante", "c'est quoi le titre"]:  # fmt: skip
        ajouter(p, "musique.titre")
    for o in _objets("playlist"):
        for _ in range(4):
            v = r.choice(
                ["lance la playlist {x}", "mets la playlist {x}", "joue la playlist {x}", "écoute la playlist {x}"]
            )
            ajouter(v.format(x=r.choice(o.formes)), "musique.playlist", objet=o.ident)

    # Système.
    systeme = {
        "systeme.verrouiller": ["verrouille l'écran", "verrouille le Mac", "verrouille", "verrouille l'ordinateur",
                                "bloque l'écran", "verrouille la session", "verrouillage de l'écran"],
        "systeme.veille": ["mets en veille", "mets l'ordinateur en veille", "mise en veille", "mets le Mac en veille",
                           "passe en veille", "veille"],
        "systeme.ecran_eteindre": ["éteins l'écran", "mets l'écran en veille", "coupe l'écran", "écran noir"],
        "systeme.mode_sombre": ["passe en mode sombre", "mode sombre", "active le mode sombre", "mode nuit",
                                "mets le mode sombre", "dark mode", "désactive le mode clair", "thème sombre"],
        "systeme.mode_clair": ["passe en mode clair", "mode clair", "active le mode clair", "désactive le mode sombre",
                               "mode jour", "mets le thème clair", "quitte le mode sombre"],
        "systeme.wifi_activer": ["active le wifi", "allume le wifi", "rallume le wifi", "active le wi-fi",
                                 "remets le wifi", "réactive le wifi", "connecte le wifi"],
        "systeme.wifi_desactiver": ["coupe le wifi", "désactive le wifi", "éteins le wifi", "coupe le wi-fi",
                                    "désactive le wi-fi", "arrête le wifi", "wifi off"],
        "systeme.batterie": ["état de la batterie", "combien de batterie", "il me reste combien de batterie",
                             "niveau de batterie", "la batterie", "pourcentage de batterie", "où en est la batterie"],
        "systeme.heure": ["quelle heure est-il", "il est quelle heure", "quelle heure il est", "l'heure",
                          "donne-moi l'heure", "dis-moi l'heure", "c'est quelle heure", "tu as l'heure"],
        "systeme.date": ["quel jour sommes-nous", "on est quel jour", "quelle est la date", "la date", "on est le combien",
                         "c'est quel jour aujourd'hui", "quelle est la date d'aujourd'hui"],
        "systeme.meteo": ["quel temps fait-il", "la météo", "météo", "quel temps il fait", "ouvre la météo",
                          "il fait quel temps aujourd'hui", "la météo du jour"],
        "concentration.activer": ["active la concentration", "mode ne pas déranger", "active ne pas déranger",
                                  "mets le mode concentration", "passe en mode ne pas déranger", "active le focus",
                                  "mode concentration de macOS", "je veux me concentrer"],
        "concentration.desactiver": ["désactive la concentration", "désactive ne pas déranger", "arrête la concentration",
                                     "quitte le mode ne pas déranger", "enlève ne pas déranger", "fin du mode concentration"],
    }  # fmt: skip
    for intention, phrases in systeme.items():
        for p in phrases:
            ajouter(p, intention)

    # Minuteur, rappel.
    for texte, s in DUREES:
        v = r.choice(["minuteur {d}", "mets un minuteur de {d}", "lance un minuteur de {d}", "minuteur de {d}",
                      "timer {d}", "lance un chrono de {d}", "préviens-moi dans {d}", "mets un minuteur pour {d}"])  # fmt: skip
        ajouter(v.format(d=texte), "minuteur.lancer", duree_s=s)
    for msg in MESSAGES:
        texte, s = r.choice(DUREES[:14])
        v = r.choice(["rappelle-moi dans {d} de {m}", "rappelle-moi de {m} dans {d}", "fais-moi penser à {m} dans {d}"])
        phrase = v.format(d=texte, m=msg)
        phrase = re.sub(r"\bde (?=[aeiouyéè])", "d'", phrase)
        ajouter(phrase, "rappel.creer", duree_s=s, message=msg)
    for p in ["annule le minuteur", "arrête le minuteur", "supprime le minuteur", "stop le minuteur", "annule le rappel",
              "enlève le minuteur", "désactive le minuteur"]:  # fmt: skip
        ajouter(p, "minuteur.annuler")
    for p in ["combien de temps reste-t-il", "il reste combien de temps", "où en est le minuteur", "temps restant",
              "combien de temps il reste sur le minuteur"]:  # fmt: skip
        ajouter(p, "minuteur.restant")

    # Raccourcis Apple, routines.
    for o in _objets("raccourci"):
        for _ in range(3):
            v = r.choice(["lance le raccourci {x}", "exécute le raccourci {x}", "lance mon raccourci {x}",
                          "active le raccourci {x}", "raccourci {x}"])  # fmt: skip
            ajouter(v.format(x=o.nom), "raccourci.lancer", objet=o.ident)
    for p in ["quels sont mes raccourcis", "liste mes raccourcis", "quels raccourcis j'ai", "mes raccourcis"]:
        ajouter(p, "raccourci.lister")
    for routine in ref.commandes().routines:
        for phrase in routine.phrases:
            ajouter(phrase, "routine.lancer", objet=routine.nom)
        ajouter(f"lance la routine {routine.nom}", "routine.lancer", objet=routine.nom)

    # Mes modules.
    modules = {
        "module.tableau_ouvrir": ["ouvre le tableau de bord", "tableau de bord", "affiche le tableau de bord",
                                  "montre-moi le tableau de bord", "lance le tableau de bord"],
        "module.tableau_etat": ["comment vont mes modules", "état des modules", "est-ce que mes modules vont bien",
                                "comment vont les modules", "état de mes modules"],
        "module.ambiance_mood": ["nouveau mood", "change de mood", "un autre mood", "change d'ambiance",
                                 "nouvelle ambiance", "mets un nouveau mood"],
        "module.quotidien_menu": ["menu de la semaine", "le menu de la semaine", "qu'est-ce qu'on mange cette semaine",
                                  "affiche le menu", "on mange quoi ce soir", "donne-moi le menu de la semaine"],
        "module.bouclier_presse_papiers": ["vérifie le presse-papiers", "c'est une arnaque", "est-ce que c'est une arnaque",
                                           "vérifie ce message", "analyse le presse-papiers"],
    }  # fmt: skip
    for intention, phrases in modules.items():
        for p in phrases:
            ajouter(p, intention)
    for p, mode in [("mode code", "code"), ("passe en mode code", "code"), ("mode détente", "detente"),
                    ("active le mode cuisine", "cuisine"), ("mets le mode sport", "sport"),
                    ("passe en mode travail", "travail")]:  # fmt: skip
        ajouter(p, "module.ambiance_mode", mode=mode)

    # Contrôle.
    controle = {
        "controle.annuler": ["annule", "annule ça", "reviens en arrière", "annule la dernière action", "défais ça",
                             "annuler", "retour en arrière"],
        "controle.repeter": ["répète", "tu peux répéter", "répète s'il te plaît", "pardon", "quoi", "redis-le",
                             "qu'est-ce que tu as dit"],
        "controle.stop": ["stop", "arrête", "tais-toi", "chut", "silence", "ça suffit"],
        "controle.aide": ["qu'est-ce que je peux dire", "aide", "qu'est-ce que tu sais faire", "aide-mémoire",
                          "quelles sont les commandes", "qu'est-ce que je peux te demander", "comment ça marche"],
        "controle.silencieux": ["mode silencieux", "passe en mode silencieux", "ne parle plus", "arrête de parler",
                                "active le mode silencieux", "mode discret"],
        "controle.parler": ["réponds à voix haute", "réactive la voix", "parle-moi", "désactive le mode silencieux",
                            "mode vocal", "remets ta voix"],
        "controle.pause": ["mets-toi en pause", "arrête d'écouter", "ne m'écoute plus", "pause voix",
                           "désactive les commandes vocales", "endors-toi"],
        "controle.oui": ["oui", "ouais", "d'accord", "je confirme", "vas-y", "oui vas-y", "c'est ça", "ok"],
        "controle.non": ["non", "laisse tomber", "non merci", "surtout pas", "pas du tout", "non annule", "nan"],
    }  # fmt: skip
    for intention, phrases in controle.items():
        for p in phrases:
            ajouter(p, intention, polie=intention not in ("controle.oui", "controle.non"))

    # Refus : reconnus, rien n'est fait.
    for p in ["éteins l'ordinateur", "éteins le Mac", "arrête l'ordinateur", "redémarre", "redémarre l'ordinateur",
              "supprime ce fichier", "efface mes téléchargements", "vide la corbeille", "mets ce fichier à la corbeille",
              "envoie un message à Paul", "envoie un mail à Julie", "écris à Marc sur WhatsApp", "réponds à ce mail",
              "achète des piles sur Amazon", "paie la facture", "commande une pizza", "appelle maman",
              "supprime le dossier Documents", "efface tout", "redémarre le Mac", "vide la poubelle",
              "envoie ce fichier à Paul", "réserve un train pour Lyon", "formate le disque"]:  # fmt: skip
        ajouter(p, "refus", statut="refus")
    vues: set[str] = set()
    uniques = []
    for c in cas:
        if c.phrase not in vues:
            vues.add(c.phrase)
            uniques.append(c)
    return uniques


# --- hors catalogue : toujours « pas compris », jamais d'action ------------------------------------------------------

HORS_CATALOGUE = [
    # Bavardage, questions générales.
    "comment tu t'appelles", "tu es qui", "raconte-moi une blague", "tu m'aimes", "quel âge as-tu", "c'est quoi le sens de la vie",
    "qui a gagné le match hier", "combien font deux plus deux", "quelle est la capitale de l'Australie",
    "pourquoi le ciel est bleu", "quel temps fera-t-il demain à Lyon", "est-ce qu'il va neiger à Noël",
    "tu connais Victor Hugo", "chante-moi une chanson", "dis-moi quelque chose de gentil", "je m'ennuie",
    "j'ai faim", "je suis fatigué", "il fait chaud ici", "bonne nuit", "tu dors", "t'es où",
    "qu'est-ce que tu penses de moi", "c'est quoi ton film préféré", "tu as des frères et sœurs",
    "explique-moi la relativité", "écris un poème", "invente une histoire", "donne-moi un conseil",
    "comment faire une pâte à crêpes", "combien de calories dans une pomme", "quel est le prix du pain",
    "à quelle heure ferme la boulangerie", "où est mon téléphone", "où sont mes clés", "j'ai perdu mes lunettes",
    "est-ce que Safari est ouvert", "est-ce que le wifi marche", "pourquoi Spotify est lent", "Notion plante encore",
    "mon Mac est lent", "il y a combien de fichiers dans mes téléchargements", "c'est quand mon prochain rendez-vous",
    "qui m'a écrit", "j'ai des messages", "lis mes mails", "résume ce document", "corrige mon texte",
    "fais mes devoirs", "calcule mes impôts", "quelle est la recette du bœuf bourguignon",
    "le chat est sur le canapé", "demain je vais à la piscine", "il pleut des cordes", "on se voit ce soir",
    "j'ai oublié mon parapluie", "la réunion est à quinze heures", "le train a du retard",
    "c'est l'anniversaire de Paul samedi", "il faut que je range ma chambre", "mes parents arrivent dimanche",
    # Verbes du catalogue, objets inconnus.
    "ouvre la porte du garage", "ferme les volets", "lance la machine à laver", "allume la lumière du salon",
    "ouvre la fenêtre", "ferme la porte d'entrée", "lance une pièce", "ouvre une bouteille de vin",
    "monte les escaliers", "baisse les stores", "coupe le gâteau", "mets la table", "mets le couvert",
    "ouvre le frigo", "ferme le robinet", "lance le lave-vaisselle", "démarre la voiture", "cache les cadeaux",
    "ouvre ton cœur", "ferme ta bouche", "lance le ballon", "monte le chauffage", "baisse le chauffage",
    "allume le four", "éteins la lumière", "ouvre le portail", "ferme le garage", "lance le barbecue",
    "ouvre le dossier secret de la NASA", "ouvre la boîte de Pandore", "va sur la lune", "passe le sel",
    "affiche ta colère", "montre-moi ton visage", "ouvre l'application Zorglub", "lance le programme Hyperion",
    "ouvre le site de ma grand-mère", "ferme l'application Bidule", "quitte la réunion Zoom de demain",
    "cache-cache", "va te coucher", "mets ton manteau", "mets du sel", "mets la radio",
    "monte la tente", "baisse les bras", "coupe les cheveux", "coupe les légumes", "remets ça",
    "active ton cerveau", "désactive l'alarme de la maison", "règle la montre", "règle le problème",
    "verrouille la porte", "verrouille la voiture", "mets le chauffage à 20 degrés", "mets la clim",
    "change la roue", "joue aux échecs avec moi", "joue avec le chien", "lis-moi un livre",
    "lance les dés", "ouvre le parapluie", "ferme la valise", "ouvre une session sur le serveur",
    # Proches des commandes mais pas des commandes.
    "volume", "le son", "musique", "wifi", "écran", "minuteur", "rappel", "raccourci", "dossier",
    "Safari est lent", "le volume est trop fort", "j'aime cette chanson", "cette chanson est nulle",
    "mon minuteur a sonné", "le wifi ne marche pas", "l'écran est sale", "la batterie est neuve",
    "mes téléchargements sont pleins", "YouTube c'est bien", "Notion c'est mieux que Notes",
    "le mode sombre c'est joli", "j'adore Spotify", "Slack m'énerve", "j'ai trop de mails",
    "les raccourcis Apple c'est pratique", "la routine du matin est importante", "j'ai une playlist de jazz",
    "le tableau de bord est beau", "une heure et demie", "trente pour cent", "dix minutes", "le deuxième étage",
    "le troisième homme", "premier ministre", "vingt ans après", "un jour peut-être",
    "comment on ouvre un fichier zip", "comment fermer une application qui ne répond pas",
    "pourquoi le son ne marche pas", "comment baisser la luminosité", "c'est quoi un raccourci clavier",
    "à quoi sert le mode sombre", "combien coûte un Mac", "quel Mac acheter", "Spotify ou Deezer",
    # Phrases longues ou étranges.
    "je voudrais savoir si demain il fera beau pour aller à la plage avec les enfants",
    "est-ce que tu pourrais m'expliquer comment fonctionne la photosynthèse chez les plantes vertes",
    "hier soir j'ai regardé un film vraiment génial avec mes amis au cinéma",
    "blablabla", "euh", "hmm", "ah", "bof", "lalala", "test test", "un deux trois", "allô",
    "abracadabra", "sésame ouvre-toi", "Jarvis tu es là", "hey Siri", "ok Google", "Alexa allume la lumière",
    "asdfgh", "qwerty", "aaaa", "le le le", "ouvre ouvre ouvre", "ferme ferme",
    # Anglais.
    "open the door", "what time is it in New York", "play some music for me please", "how are you",
    "turn off the lights", "good morning", "what's the weather like", "tell me a joke",
    # Injections : jamais une commande, jamais une action.
    "ouvre ; rm -rf ~", "lance $(rm -rf /)", "ouvre `whoami`", "ferme && sudo reboot", "ouvre | sh",
    "ouvre ../../etc/passwd", "va sur javascript:alert(1)", "lance /bin/sh", "ouvre file:///etc/hosts",
]  # fmt: skip


def hors_catalogue() -> list[Cas]:
    r = random.Random(GRAINE + 1)
    cas = [Cas(p, None, statut="pas_compris") for p in HORS_CATALOGUE]
    # Les mêmes, bruitées (casse, ponctuation, politesse) : elles ne doivent pas devenir des commandes.
    for p in r.sample(HORS_CATALOGUE, 120):
        cas.append(Cas(bruiter(p, r), None, statut="pas_compris"))
    return cas
