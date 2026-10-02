"""Un point vient d'être tapé : lire la phrase, la traduire sur le Mac, la remplacer. Sans macOS (testable).

Rien n'est gardé : ni la phrase, ni sa traduction (seul un compteur du jour, pour « assistant.py etat »).
Le journal note ce qui s'est passé et dans quelle appli, jamais le texte.
"""

import time
from datetime import date

from core import etat
from core.notifications import notifier
from modules.traduction import parametres as p
from modules.traduction.phrase import (finir_comme, graphemes, phrase_avant, phrases_de_fin, position,
                                      raison_de_ne_pas_traduire, unites)
from modules.yeux.filtres import _appli_dans, exclue

TRADUITE, COPIEE = "traduite", "copiée"


def compter() -> int:
    """Phrases traduites aujourd'hui (le compteur repart à zéro chaque jour)."""
    brut = str(etat.lire("traduction_jour") or "")
    jour, _, n = brut.partition("|")
    return int(n) if jour == date.today().isoformat() and n.isdigit() else 0


def _compter_une(n: int = 1) -> None:
    etat.ecrire("traduction_jour", f"{date.today().isoformat()}|{compter() + n}")


def _copier(mac, anglais: str, pourquoi: str) -> str:
    """L'appli ne laisse pas remplacer : l'anglais est copié, une notification le dit (sans rien en garder)."""
    mac.copier(anglais)
    notifier("🇬🇧 Copié en anglais", f"{pourquoi} : Cmd + V pour coller « {anglais[:120]} »", module="traduction",
             urgent=True, prive=True)
    _compter_une()
    return COPIEE


def _par_le_clavier(mac, traducteur, appli: str, finies_avant: int | None) -> tuple[str, str]:
    """Pages, Keynote… cachent leur texte à macOS. On attend que tu t'arrêtes de taper, on lit le paragraphe en le
    sélectionnant et le copiant, puis l'anglais est collé à la place de tes phrases (presse-papiers remis)."""
    limite = time.time() + p.PAUSE_MAX
    while time.time() - mac.activite()[0] < p.PAUSE:
        if time.time() > limite:
            return "tu as tapé sans t'arrêter : phrase laissée", appli
        time.sleep(0.05)
    lu_a, finies = time.time(), mac.activite()[1]
    # finies_avant compte déjà la phrase de ce point : les phrases à traduire = elle + celles finies depuis
    combien = min(1 + max(0, finies - finies_avant if finies_avant is not None else 0), 10)
    texte = mac.copier_avant()
    if texte is None:
        return "rien n'a pu être copié (curseur en début de paragraphe ?)", appli
    a_traduire, raison = [], None
    for i, phrase in reversed(phrases_de_fin(texte, combien)):
        raison = raison_de_ne_pas_traduire(phrase, p.mots_min())
        if raison:
            break
        a_traduire.insert(0, (i, phrase))
    if not a_traduire:
        return raison or "pas de phrase finie par un point", appli
    debut = a_traduire[0][0]
    morceaux, anglais, curseur = [], [], debut
    for i, phrase in a_traduire:
        traduite = finir_comme(traducteur.traduire(phrase))
        if not traduite:
            return "traduction vide", appli
        anglais.append(traduite)
        morceaux.append(texte[curseur:i] + traduite)
        curseur = i + len(phrase)
    nouveau = "".join(morceaux) + texte[curseur:]
    if mac.remplacer_au_clavier(graphemes(texte[debut:]), nouveau, lu_a):
        _compter_une(len(anglais))
        etat.ecrire("traduction_derniere", time.time())
        return TRADUITE, appli
    return _copier(mac, " ".join(anglais), "Tu as tapé pendant la traduction"), appli


def traiter_point(mac, traducteur, finies_avant: int | None = None) -> tuple[str, str]:
    """(ce qui s'est passé, appli). « traduite », « copiée », ou la raison pour laquelle rien n'a été fait.
    finies_avant : le nombre de phrases finies au clavier au moment du point (pour le mode clavier)."""
    f = mac.appli_devant()
    if f is None:
        return "aucune appli au premier plan", ""
    appli = f.get("appli", "")
    raison = exclue(f, p.applis_exclues(), p.titres_exclus())
    if raison:
        return raison, appli
    champ = mac.champ(f.get("pid"))
    lu = mac.lire(champ) if champ is not None else None
    if lu is not None and lu.secret:
        return "champ secret (mot de passe)", appli
    if lu is None:
        if _appli_dans(f, p.applis_clavier()):
            return _par_le_clavier(mac, traducteur, appli, finies_avant)
        return ("pas de champ de texte" if champ is None else "texte illisible (ou sélection en cours)"), appli
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
