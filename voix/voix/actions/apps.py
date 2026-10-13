"""Les apps : ouvrir, aller sur, fermer, cacher, tout fermer (avec confirmation).

Ouvrir et aller sur : `open -b <identifiant>` (l'app vient devant, lancée si besoin). Fermer et cacher passent par
l'app Commandes Vocales (NSRunningApplication : « Quitter » comme ⌘Q, sans autorisation particulière).
"""

from __future__ import annotations

from voix.actions.base import CheminRefuse, Outils, Reponse, chemin_ouvrable, erreur, fait
from voix.actions.pont import BUNDLE
from voix.nlu.catalogue import Objet


def _identifiant(objet: Objet) -> str | None:
    return objet.ident if "." in objet.ident and BUNDLE.fullmatch(objet.ident) and "/" not in objet.ident else None


def ouvrir(o: Outils, objet: Objet, intention: str = "app.ouvrir") -> Reponse:
    bundle = _identifiant(objet)
    if bundle is not None:
        r = o.lancer("open", "-b", bundle)
    else:
        try:
            chemin = chemin_ouvrable(objet.cible, o.chemins.maison, apps=True)
        except CheminRefuse as e:
            return erreur(f"Je ne peux pas ouvrir {objet.nom} ({e}).", intention)
        r = o.lancer("open", "-a", chemin)
    if not r.ok:
        return erreur(f"{objet.nom} n'a pas pu s'ouvrir.", intention)
    return fait(f"{objet.nom} ouvert" if intention == "app.ouvrir" else objet.nom, intention, objet=objet.nom)


def fermer(o: Outils, objet: Objet) -> Reponse:
    bundle = _identifiant(objet)
    if bundle is None:
        return erreur(f"Je ne sais pas fermer {objet.nom}.", "app.fermer")
    r = o.demander("app.quitter", bundle=bundle)
    if not r.ok:
        return erreur(f"Je n'ai pas pu fermer {objet.nom} : {r.erreur or 'refusé'}.", "app.fermer")
    return fait(f"{objet.nom} fermé", "app.fermer", objet=objet.nom)


def cacher(o: Outils, objet: Objet) -> Reponse:
    bundle = _identifiant(objet)
    if bundle is None:
        return erreur(f"Je ne sais pas cacher {objet.nom}.", "app.cacher")
    r = o.demander("app.cacher", bundle=bundle)
    if not r.ok:
        return erreur(f"Je n'ai pas pu cacher {objet.nom} : {r.erreur or 'refusé'}.", "app.cacher")
    return fait(f"{objet.nom} caché", "app.cacher", objet=objet.nom)


def cacher_autres(o: Outils, objet: Objet | None) -> Reponse:
    sauf = _identifiant(objet) if objet is not None else None
    r = o.demander("app.cacher_autres", sauf=sauf)
    if not r.ok:
        return erreur(f"Je n'ai pas pu cacher les autres apps : {r.erreur or 'refusé'}.", "app.cacher_autres")
    return fait("Les autres apps sont cachées" + (f" (sauf {objet.nom})" if objet else ""), "app.cacher_autres")


def fermer_tout(o: Outils, objet: Objet | None) -> Reponse:
    intention = "app.fermer_tout_sauf" if objet is not None else "app.fermer_tout"
    sauf = _identifiant(objet) if objet is not None else None
    r = o.demander("app.quitter_tout", sauf=sauf)
    if not r.ok:
        return erreur(f"Je n'ai pas pu tout fermer : {r.erreur or 'refusé'}.", intention)
    n = r.donnees.get("fermees")
    detail = f" ({n} app{'s' if n != 1 else ''})" if isinstance(n, int) else ""
    return fait("Tout est fermé" + (f" sauf {objet.nom}" if objet else "") + detail, intention)
