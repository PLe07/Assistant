"""Le web, dans ton navigateur par défaut : ouvrir un site, chercher sur Google, YouTube ou Wikipédia, un trajet dans
Plans, une traduction. Le texte dit est **encodé** dans l'adresse (jamais interprété) ; seules les adresses `https://`
sont ouvertes.
"""

from __future__ import annotations

from urllib.parse import quote, quote_plus

from voix.actions.base import CheminRefuse, Outils, Reponse, adresse_ouvrable, erreur, fait
from voix.nlu.catalogue import Objet

RECHERCHES = {
    "web.chercher_google": ("https://www.google.fr/search?q={}", "Google"),
    "web.chercher_youtube": ("https://www.youtube.com/results?search_query={}", "YouTube"),
    "web.chercher_wikipedia": ("https://fr.wikipedia.org/w/index.php?search={}", "Wikipédia"),
    "web.chercher_plans": ("https://maps.apple.com/?q={}", "Plans"),
}
TRADUCTION = "https://translate.google.fr/?sl=fr&tl={langue}&text={texte}&op=translate"
LANGUES = {"en", "es", "de", "it", "pt", "zh", "ja", "ar", "ru", "nl", "fr", "pl", "ko", "el", "tr", "sv"}
TEXTE_MAX = 300


def ouvrir_adresse(o: Outils, url: str, nom: str, intention: str) -> Reponse:
    try:
        sure = adresse_ouvrable(url)
    except CheminRefuse as e:
        return erreur(f"Je n'ouvre pas {nom} : {e}.", intention)
    r = o.lancer("open", sure)
    if not r.ok:
        return erreur(f"{nom} n'a pas pu s'ouvrir.", intention)
    return fait(f"{nom} ouvert", intention, adresse=sure)


def ouvrir_site(o: Outils, objet: Objet) -> Reponse:
    return ouvrir_adresse(o, objet.cible, objet.nom, "web.ouvrir_site")


def chercher(o: Outils, intention: str, requete: str) -> Reponse:
    modele, ou = RECHERCHES[intention]
    texte = " ".join(requete.split())[:TEXTE_MAX]
    if not texte:
        return erreur("Que dois-je chercher ?", intention)
    r = ouvrir_adresse(o, modele.format(quote_plus(texte)), ou, intention)
    if r.statut == "fait":
        r.texte = f"✓ « {texte} » sur {ou}"
    return r


def traduire(o: Outils, texte: str, langue: str) -> Reponse:
    propre = " ".join(texte.split())[:TEXTE_MAX]
    if langue not in LANGUES or not propre:
        return erreur("Je ne sais pas traduire ça.", "web.traduire")
    r = ouvrir_adresse(o, TRADUCTION.format(langue=langue, texte=quote(propre, safe="")), "la traduction",
                       "web.traduire")  # fmt: skip
    if r.statut == "fait":
        r.texte = f"✓ Traduction de « {propre} »"
    return r
