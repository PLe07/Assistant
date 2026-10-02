"""Un point vient d'être tapé : lire la phrase, la traduire sur le Mac, la remplacer. Sans macOS (testable).

Rien n'est gardé : ni la phrase, ni sa traduction (seul un compteur du jour, pour « assistant.py etat »).
Le journal note ce qui s'est passé et dans quelle appli, jamais le texte.
"""

import time
from datetime import date

from core import etat
from core.notifications import notifier
from modules.traduction import parametres as p
from modules.traduction.phrase import finir_comme, phrase_avant, position, raison_de_ne_pas_traduire, unites
from modules.yeux.filtres import exclue

TRADUITE, COPIEE = "traduite", "copiée"


def compter() -> int:
    """Phrases traduites aujourd'hui (le compteur repart à zéro chaque jour)."""
    brut = str(etat.lire("traduction_jour") or "")
    jour, _, n = brut.partition("|")
    return int(n) if jour == date.today().isoformat() and n.isdigit() else 0


def _compter_une() -> None:
    etat.ecrire("traduction_jour", f"{date.today().isoformat()}|{compter() + 1}")


def _copier(mac, anglais: str, pourquoi: str) -> str:
    """L'appli ne laisse pas remplacer : l'anglais est copié, une notification le dit (sans rien en garder)."""
    mac.copier(anglais)
    notifier("🇬🇧 Copié en anglais", f"{pourquoi} : Cmd + V pour coller « {anglais[:120]} »", module="traduction",
             urgent=True, prive=True)
    _compter_une()
    return COPIEE


def traiter_point(mac, traducteur) -> tuple[str, str]:
    """(ce qui s'est passé, appli). « traduite », « copiée », ou la raison pour laquelle rien n'a été fait."""
    f = mac.appli_devant()
    if f is None:
        return "aucune appli au premier plan", ""
    appli = f.get("appli", "")
    raison = exclue(f, p.applis_exclues(), p.titres_exclus())
    if raison:
        return raison, appli
    champ = mac.champ(f.get("pid"))
    if champ is None:
        return "pas de champ de texte", appli
    lu = mac.lire(champ)
    if lu is None:
        return "texte illisible (ou sélection en cours)", appli
    if lu.secret:
        return "champ secret (mot de passe)", appli
    trouve = phrase_avant(lu.texte, lu.curseur)
    if trouve is None:
        return "pas de phrase finie par un point", appli
    debut, francais = trouve
    raison = raison_de_ne_pas_traduire(francais, p.mots_min())
    if raison:
        return raison, appli
    anglais = finir_comme(traducteur.traduire(francais))
    if not anglais:
        return "traduction vide", appli
    relu = mac.lire(champ)  # tu as pu continuer à taper pendant la traduction : la phrase est-elle toujours là ?
    if relu is None or relu.secret:
        return _copier(mac, anglais, "Le champ a changé"), appli
    i = position(relu.texte, debut)
    if relu.texte[i:i + len(francais)] != francais:
        return _copier(mac, anglais, "Ta phrase a bougé pendant la traduction"), appli
    curseur = max(relu.curseur, debut + unites(francais)) + unites(anglais) - unites(francais)
    if mac.remplacer(champ, debut, unites(francais), anglais, curseur):
        _compter_une()
        etat.ecrire("traduction_derniere", time.time())
        return TRADUITE, appli
    return _copier(mac, anglais, f"« {appli} » ne laisse pas remplacer le texte"), appli
