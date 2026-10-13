"""Le son et la musique.

Volume : `osascript` avec les commandes standard (`set volume`), qui ne demandent aucune autorisation ; le niveau est
passé en **argument** du script (`on run argv`), jamais collé dans le texte du script. Chaque changement est
annulable (« annule » remet le niveau et la sourdine d'avant, exactement).
Musique et Spotify : par l'app Commandes Vocales (Apple Events, autorisation « Automatisation » demandée en son nom).
"""

from __future__ import annotations

from dataclasses import dataclass

from voix.actions.base import Annulation, Etat, Outils, Reponse, erreur, fait, info
from voix.nlu.catalogue import Objet

LIRE = ("-e", "set v to get volume settings",
        "-e", "return ((output volume of v) as text) & \",\" & ((output muted of v) as text)")  # fmt: skip
REGLER = ("-e", "on run argv", "-e", "set volume output volume ((item 1 of argv) as integer)", "-e", "end run")
SOURDINE = ("-e", "set volume with output muted")
SANS_SOURDINE = ("-e", "set volume without output muted")


@dataclass(frozen=True)
class Volume:
    niveau: int
    muet: bool


def lire(o: Outils) -> Volume | None:
    r = o.lancer("osascript", *LIRE)
    if not r.ok:
        return None
    try:
        niveau_brut, muet_brut = r.sortie.strip().split(",")
        niveau = int(niveau_brut)
    except ValueError:
        return None
    if not 0 <= niveau <= 100:
        return None
    return Volume(niveau, muet_brut.strip() == "true")


def _regler(o: Outils, niveau: int) -> bool:
    if not 0 <= niveau <= 100:
        return False
    return o.lancer("osascript", *REGLER, str(int(niveau))).ok


def appliquer(o: Outils, v: Volume) -> bool:
    """Remet exactement un état du volume (niveau puis sourdine)."""
    ok = _regler(o, v.niveau)
    return o.lancer("osascript", *(SOURDINE if v.muet else SANS_SOURDINE)).ok and ok


def _retenir(etat: Etat, avant: Volume, libelle: str) -> None:
    etat.retenir(Annulation("volume", {"niveau": avant.niveau, "muet": avant.muet}, libelle))


def regler(o: Outils, etat: Etat, niveau: int) -> Reponse:
    if not 0 <= niveau <= 100:
        return erreur("Le volume va de 0 à 100.", "son.regler")
    avant = lire(o)
    if avant is None:
        return erreur("Je n'arrive pas à lire le volume.", "son.regler")
    if not _regler(o, niveau):
        return erreur("Je n'ai pas pu régler le volume.", "son.regler")
    if avant.muet and niveau > 0:
        o.lancer("osascript", *SANS_SOURDINE)
    _retenir(etat, avant, f"volume à {niveau} %")
    return fait(f"Volume à {niveau} %", "son.regler", niveau=niveau)


def varier(o: Outils, etat: Etat, intention: str, pas: int) -> Reponse:
    avant = lire(o)
    if avant is None:
        return erreur("Je n'arrive pas à lire le volume.", intention)
    signe = 1 if intention == "son.monter" else -1
    niveau = max(0, min(100, avant.niveau + signe * max(1, min(100, pas))))
    if not _regler(o, niveau):
        return erreur("Je n'ai pas pu régler le volume.", intention)
    if avant.muet and signe > 0:
        o.lancer("osascript", *SANS_SOURDINE)
    _retenir(etat, avant, f"volume {'monté' if signe > 0 else 'baissé'}")
    return fait(f"Volume à {niveau} %", intention, niveau=niveau)


def sourdine(o: Outils, etat: Etat, couper: bool) -> Reponse:
    intention = "son.couper" if couper else "son.remettre"
    avant = lire(o)
    if avant is None:
        return erreur("Je n'arrive pas à lire le volume.", intention)
    if not o.lancer("osascript", *(SOURDINE if couper else SANS_SOURDINE)).ok:
        return erreur("Je n'ai pas pu changer le son.", intention)
    _retenir(etat, avant, "son coupé" if couper else "son remis")
    return fait("Son coupé" if couper else "Son remis", intention)


def niveau(o: Outils) -> Reponse:
    v = lire(o)
    if v is None:
        return erreur("Je n'arrive pas à lire le volume.", "son.niveau")
    return info(f"Le volume est à {v.niveau} %" + (" (son coupé)" if v.muet else "") + ".", "son.niveau",
                niveau=v.niveau, muet=v.muet)  # fmt: skip


# --- musique (par l'app) ------------------------------------------------------------------------------------------

TEXTES = {"musique.lecture": "Lecture", "musique.pause": "Pause", "musique.suivant": "Morceau suivant",
          "musique.precedent": "Morceau précédent"}  # fmt: skip


def musique(o: Outils, intention: str, lecteur: str | None = None) -> Reponse:
    r = o.demander(intention, lecteur=lecteur)
    if not r.ok:
        return erreur(f"La musique ne répond pas : {r.erreur or 'refusé'}.", intention)
    if intention == "musique.titre":
        titre = str(r.donnees.get("titre") or "")
        artiste = str(r.donnees.get("artiste") or "")
        if not titre:
            return info("Rien ne joue en ce moment.", intention)
        return info(f"« {titre} »" + (f", {artiste}" if artiste else ""), intention, titre=titre, artiste=artiste)
    return fait(TEXTES[intention], intention)


def playlist(o: Outils, objet: Objet) -> Reponse:
    lecteur = "spotify" if objet.ident.startswith("spotify:") else "musique"
    r = o.demander("musique.playlist", lecteur=lecteur, playlist=objet.cible)
    if not r.ok:
        return erreur(f"La playlist {objet.nom} ne démarre pas : {r.erreur or 'refusé'}.", "musique.playlist")
    return fait(f"Playlist {objet.nom}", "musique.playlist")
