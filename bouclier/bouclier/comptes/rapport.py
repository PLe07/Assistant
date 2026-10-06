"""La partie « Tes comptes » du tableau de bord local `Bouclier.html` (jamais envoyé sur iCloud : il est sensible)."""

from __future__ import annotations

from collections import defaultdict
from html import escape

from bouclier.comptes.inventaire import Ligne

NATURES = {"compte": "compte probable", "abonnement": "simple abonnement"}
STATUTS = {"a_trier": "à trier", "a_garder": "à garder", "a_supprimer": "à supprimer", "supprime": "supprimé"}
SIGNAUX = {"creation": "inscription", "verification": "vérification d'adresse", "reinitialisation": "mot de passe",
           "connexion": "connexion", "commande": "commande"}  # fmt: skip


def _lien(url: str | None, texte: str) -> str:
    if not url or not url.startswith("https://"):
        return ""
    return f'<a href="{escape(url, quote=True)}" rel="noopener noreferrer">{escape(texte)}</a>'


def _double_auth(ligne: Ligne) -> str:
    s = ligne.service
    if s is None or s.double_auth is None:
        return "inconnue"
    if not s.double_auth:
        return "non proposée"
    lien = _lien(s.doc_double_auth, "l'activer")
    return f"disponible ({lien})" if lien else "disponible"


def _suppression(ligne: Ligne) -> str:
    s = ligne.service
    if s is not None and s.difficulte == "impossible":
        return escape(s.aide or "ne se supprime pas")
    if s is None or not s.suppression:
        if ligne.categorie == "banque":
            return "fermeture : demande-la à ta banque (espace client ou courrier)"
        return "cherche « supprimer mon compte » dans ses réglages"
    difficulte = f" ({escape(s.difficulte)})" if s.difficulte else ""
    return _lien(s.suppression, "page de suppression") + difficulte


def section(lignes: list[Ligne]) -> str:
    comptes = [ligne for ligne in lignes if ligne.nature == "compte"]
    abonnements = [ligne for ligne in lignes if ligne.nature == "abonnement"]
    par_categorie: dict[str, list[Ligne]] = defaultdict(list)
    for ligne in comptes:
        par_categorie[ligne.categorie].append(ligne)
    morceaux = [f"<h2>Tes comptes en ligne ({len(comptes)})</h2>"]
    if not lignes:
        morceaux.append("<p>Pas encore d'inventaire : lance <code>bouclier inventaire</code>.</p>")
        return "\n".join(morceaux)
    morceaux.append(
        "<p>Retrouvés sans lire tes mails (seulement l'expéditeur, le sujet et la date) et dans tes navigateurs"
        " (seulement le site et l'identifiant). Aucune action automatique : c'est toi qui décides, avec"
        " <code>bouclier compte &lt;service&gt; garder|supprimer|supprime</code>.</p>"
    )
    for categorie in sorted(par_categorie):
        morceaux.append(f"<h3>{escape(categorie.capitalize())}</h3>")
        morceaux.append("<table><tr><th>Service</th><th>Indices</th><th>Dernière activité</th>"
                        "<th>Double authentification</th><th>Supprimer</th><th>Statut</th></tr>")  # fmt: skip
        for ligne in sorted(par_categorie[categorie], key=lambda x: x.nom.lower()):
            indices = [SIGNAUX[s] for s in ligne.signaux if s in SIGNAUX]
            if "navigateur" in ligne.sources:
                indices.append("identifiant enregistré")
            morceaux.append(
                f"<tr><td><b>{escape(ligne.nom)}</b><br><small>{escape(ligne.id)}</small></td>"
                f"<td>{escape(', '.join(indices))}</td><td>{escape(ligne.derniere_activite or '—')}</td>"
                f"<td>{_double_auth(ligne)}</td><td>{_suppression(ligne)}</td>"
                f'<td class="statut-{escape(ligne.statut)}">{escape(STATUTS.get(ligne.statut, ligne.statut))}</td></tr>'
            )
        morceaux.append("</table>")
    if abonnements:
        noms = ", ".join(escape(a.nom) for a in sorted(abonnements, key=lambda x: x.nom.lower()))
        morceaux.append(f"<h3>Simples abonnements ({len(abonnements)})</h3><p>{noms}</p>")
    return "\n".join(morceaux)
