"""Les fuites qui te concernent : la partie du tableau de bord, et la vérification quotidienne."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from bouclier.config import Chemins
from bouclier.db import Base
from bouclier.fuites import croisement, hibp, traductions
from bouclier.notifier import Notifieur


@dataclass
class Resultat:
    bilan: croisement.Bilan
    liste: str  # état de la liste publique
    adresse_verifiee: bool


def verifier(chemins: Chemins, reglages: dict[str, Any], base: Base, notifieur: Notifieur,
             telecharger: hibp.Telecharger = hibp.reseau.telecharger, forcer: bool = False) -> Resultat:  # fmt: skip
    liste = hibp.ListeFuites(chemins.caches, telecharger)
    _, etat = liste.mettre_a_jour(forcer)
    cle = str(reglages["fuites"].get("cle_hibp") or "")
    confirmees = hibp.par_adresse(str(reglages["gmail"].get("adresse") or ""), cle, telecharger) if cle else None
    correspondances = croisement.croiser(liste.fuites(), croisement.comptes_surveilles(base), confirmees)
    return Resultat(croisement.signaler(base, correspondances, notifieur), etat, confirmees is not None)


def section(correspondances: list[croisement.Correspondance], liste_date: str | None) -> str:
    morceaux = [f"<h2>Fuites qui touchent tes comptes ({len(correspondances)})</h2>"]
    if liste_date is None:
        morceaux.append("<p>La liste publique des fuites n'a pas encore été téléchargée : <code>bouclier fuites"
                        " --mettre-a-jour</code>.</p>")  # fmt: skip
    elif not correspondances:
        morceaux.append("<p>Aucune fuite connue ne touche les services de ton inventaire.</p>")
    else:
        morceaux.append("<table><tr><th>Service</th><th>Quand</th><th>Données exposées</th><th>Que faire</th></tr>")
        for c in correspondances:
            donnees = ", ".join(traductions.traduire(list(c.fuite.donnees)))
            quand = c.fuite.date.strftime("%d/%m/%Y") if c.fuite.date else "date inconnue"
            confirme = "<br><b>ton adresse y figure</b>" if c.confirmee else ""
            morceaux.append(f"<tr><td><b>{escape(c.compte.nom)}</b><br><small>{escape(c.fuite.titre)}</small>"
                            f"{confirme}</td><td>{quand}</td><td>{escape(donnees)}</td>"
                            f"<td>{escape(c.que_faire)}</td></tr>")  # fmt: skip
        morceaux.append("</table>")
    morceaux.append(f"<p class=\"doux\">{escape(hibp.ATTRIBUTION)}"
                    + (f" Liste du {escape(liste_date)}." if liste_date else "") + "</p>")  # fmt: skip
    return "\n".join(morceaux)
