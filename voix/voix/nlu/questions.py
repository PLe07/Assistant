"""Les questions d'information, quelle que soit la tournure : « c'est quoi la date d'aujourd'hui », « la batterie est à
combien », « il reste combien de batterie », « quelle est la météo aujourd'hui ».

Plutôt qu'une règle par tournure, on regarde les mots : la phrase est une question sur un sujet connu si
- elle porte un mot interrogatif (quel, quoi, combien…) ;
- elle nomme **un seul** sujet (batterie, heure, date, météo, volume, chanson, menu, minuteur, modules) ;
- **tous** ses autres mots sont des mots-outils de question (c'est, est-ce que, le, la, aujourd'hui…).
La dernière condition rend la règle stricte : « quelle heure est-il à Tokyo » (Tokyo) ou « c'est quoi le menu du
restaurant » (restaurant) ne passent pas. Ces intentions ne font que lire et dire : jamais d'action.
"""

from __future__ import annotations

SIGNAUX = {"quel", "quelle", "quels", "quelles", "quoi", "combien", "donne", "dis", "ou", "qui", "dire", "savoir",
           "donner", "connaitre", "sais", "connais"}  # fmt: skip
OUTILS = {
    "c", "est", "ce", "que", "qu", "il", "y", "a", "on", "nous", "sommes", "moi", "me", "le", "la", "les", "l", "de",
    "du", "des", "d", "mon", "ma", "mes", "en", "sur", "au", "actuel", "actuelle", "actuellement", "maintenant",
    "aujourd", "hui", "moment", "cette", "cet", "niveau", "etat", "t", "tu", "ca", "dit", "donc", "exactement",
    "precisement", "alors", "encore", "comme", "j", "ai", "je", "assez", "nom",
}  # fmt: skip
# Sujet → (mots qui le nomment, mots-outils propres à ce sujet, mots dont il faut au moins un).
SUJETS: dict[str, tuple[set[str], set[str], set[str]]] = {
    "systeme.batterie": ({"batterie", "autonomie"}, {"reste", "pourcentage", "charge", "ordi", "mac"}, set()),
    "systeme.heure": ({"heure"}, set(), set()),
    "systeme.date": ({"date", "quantieme"}, {"jour"}, set()),
    "systeme.meteo": ({"meteo"}, {"dehors", "fait"}, set()),
    "son.niveau": ({"volume"}, {"regle"}, set()),
    "musique.titre": (
        {"chanson", "morceau", "titre", "artiste", "chanteur", "chanteuse", "chante"},
        {"qui", "passe", "joue", "ecoute"},
        set(),
    ),  # fmt: skip
    "module.quotidien_menu": ({"menu", "repas"}, {"semaine", "jour", "soir", "midi", "mange", "prevu"}, set()),
    "minuteur.restant": (
        {"minuteur", "timer", "chrono", "compte"},
        {"temps", "reste", "restant", "rebours"},
        {"reste", "restant", "combien", "ou"},
    ),  # fmt: skip
    "module.tableau_etat": ({"modules"}, {"vont", "va", "bien", "fonctionnent", "marchent", "tournent"}, set()),
}


def question(cles: list[str], interrogative: bool = False) -> str | None:
    """L'intention d'information de cette phrase (mots normalisés), ou None si ce n'en est pas une, sûrement.

    `interrogative` : la phrase commençait par « dis-moi », « tu sais »… (retirés à la normalisation)."""
    mots = set(cles)
    if not interrogative and not mots & SIGNAUX:
        return None
    if "son" in mots and mots & {"niveau", "combien"}:
        mots = (mots - {"son"}) | {
            "volume"
        }  # « le niveau du son », « le son est à combien » ; pas « c'est quoi ce son »
    trouves = [intention for intention, (noms, _, _) in SUJETS.items() if mots & noms]
    if len(trouves) != 1:
        return None
    intention = trouves[0]
    noms, propres, requis = SUJETS[intention]
    if requis and not mots & requis:
        return None
    reste = mots - noms - propres - OUTILS - SIGNAUX
    return intention if not reste else None
