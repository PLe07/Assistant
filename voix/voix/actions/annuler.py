"""« Annule » : défait la dernière action réversible (volume, apparence, Wi-Fi, concentration), en remettant
**exactement** l'état d'avant. Les autres actions (ouvrir une app, un site…) ne s'annulent pas : on le dit.
"""

from __future__ import annotations

from voix.actions import raccourcis, son, systeme
from voix.actions.base import Etat, Outils, Reponse, erreur, fait, info


def defaire(o: Outils, etat: Etat) -> Reponse:
    if not etat.annulations:
        return info("Il n'y a rien à annuler.", "controle.annuler")
    a = etat.annulations.pop()
    if a.genre == "volume":
        ok = son.appliquer(o, son.Volume(int(a.avant["niveau"]), bool(a.avant["muet"])))
        texte = f"Volume remis à {a.avant['niveau']} %" + (" (son coupé)" if a.avant["muet"] else "")
    elif a.genre == "apparence":
        ok = systeme.regler_apparence(o, bool(a.avant["sombre"]))
        texte = "Mode sombre remis" if a.avant["sombre"] else "Mode clair remis"
    elif a.genre == "wifi":
        ok = systeme.regler_wifi(o, str(a.avant["interface"]), bool(a.avant["actif"]))
        texte = "Wi-Fi rallumé" if a.avant["actif"] else "Wi-Fi recoupé"
    elif a.genre == "concentration":
        nom = raccourcis.ACTIVER if a.avant["active"] else raccourcis.DESACTIVER
        ok = raccourcis.executer(o, nom, "controle.annuler").statut == "fait"
        texte = "Concentration réactivée" if a.avant["active"] else "Concentration désactivée"
    else:  # pragma: no cover - les genres sont fixés plus haut
        return erreur("Je ne sais pas annuler ça.", "controle.annuler")
    if not ok:
        etat.annulations.append(a)  # rien n'a changé : on pourra réessayer
        return erreur(f"Je n'ai pas pu annuler ({a.libelle}).", "controle.annuler")
    return fait(f"Annulé : {texte}", "controle.annuler")
