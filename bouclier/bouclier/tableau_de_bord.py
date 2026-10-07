"""Le tableau de bord local `Bouclier.html` : une page autonome (aucune ressource extérieure), jamais envoyée sur
iCloud. Chaque brique y ajoute sa partie ; une brique pas encore utilisée affiche comment commencer."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from html import escape
from pathlib import Path

from bouclier.db import Base

STYLE = """
:root { --fond: #fbfaf8; --texte: #1d1d1f; --doux: #6e6e73; --ligne: #e5e2dc; --carte: #ffffff;
        --rouge: #c62828; --orange: #d9730d; --jaune: #b8860b; --vert: #2e7d32; --lien: #0b57d0; }
@media (prefers-color-scheme: dark) {
  :root { --fond: #161618; --texte: #f2f2f2; --doux: #a1a1a6; --ligne: #333336; --carte: #1f1f22;
          --rouge: #ff6b6b; --orange: #ffa94d; --jaune: #ffd43b; --vert: #69db7c; --lien: #8ab4f8; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 64px; background: var(--fond); color: var(--texte);
       font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }
main { max-width: 980px; margin: 0 auto; }
h1 { font-size: 28px; margin: 0 0 4px; } h2 { margin-top: 40px; border-bottom: 1px solid var(--ligne); }
h3 { margin-top: 24px; color: var(--doux); font-size: 15px; text-transform: uppercase; letter-spacing: .04em; }
table { width: 100%; border-collapse: collapse; background: var(--carte); font-size: 14px; }
th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--ligne); vertical-align: top; }
th { color: var(--doux); font-weight: 600; } small, .doux { color: var(--doux); }
a { color: var(--lien); } code { background: var(--carte); border: 1px solid var(--ligne); padding: 1px 4px; }
.statut-a_supprimer { color: var(--orange); font-weight: 600; } .statut-supprime { color: var(--doux); }
.carte { background: var(--carte); border: 1px solid var(--ligne); border-radius: 10px; padding: 16px; }
@media (max-width: 700px) { table { display: block; overflow-x: auto; } }
"""

Section = Callable[[Base], str]


def _section_comptes(base: Base) -> str:
    from bouclier.comptes import inventaire, rapport

    return rapport.section(inventaire.lignes(base))


def _section_arnaques(base: Base) -> str:
    lignes = base.lignes("SELECT date, titre, source FROM analyses WHERE niveau IN ('arnaque', 'tres_suspect')"
                         " ORDER BY date DESC LIMIT 15")  # fmt: skip
    morceaux = [f"<h2>Arnaques repérées ({len(lignes)} récentes)</h2>"]
    if not lignes:
        morceaux.append("<p>Aucune pour l'instant. Pour vérifier un message : <code>bouclier verifier</code> ou le"
                        " raccourci « Arnaque ? » sur l'iPhone.</p>")  # fmt: skip
    else:
        morceaux.append("<table><tr><th>Quand</th><th>Verdict</th><th>D'où</th></tr>")
        for ligne in lignes:
            quand = time.strftime("%d/%m/%Y %H:%M", time.localtime(ligne["date"]))
            morceaux.append(
                f"<tr><td>{quand}</td><td>{escape(ligne['titre'])}</td><td>{escape(ligne['source'])}</td></tr>"
            )
        morceaux.append("</table>")
    return "\n".join(morceaux)


def _section_fuites(base: Base) -> str:
    from bouclier import config
    from bouclier.fuites import croisement, hibp, rapport

    liste = hibp.ListeFuites(config.chemins().caches)
    date = liste.date()
    quand = time.strftime("%d/%m/%Y", time.localtime(date)) if date else None
    correspondances = croisement.croiser(liste.fuites(), croisement.comptes_surveilles(base))
    return rapport.section(correspondances, quand)


def _section_urgence(base: Base) -> str:
    from bouclier import config
    from bouclier.urgence import service

    c = config.chemins()
    generee = base.lire_meta("fiche_generee_le")
    verifiee = base.lire_meta("sources_verifiees_le")
    morceaux = ["<h2>Fiche urgence</h2>"]
    if generee is None:
        morceaux.append("<p>Pas encore générée : <code>bouclier urgence editer</code> puis <code>bouclier urgence"
                        " generer</code>.</p>")  # fmt: skip
    else:
        quand = time.strftime("%d/%m/%Y", time.localtime(float(generee)))
        icloud = " — copiée sur iCloud." if (c.icloud / service.NOM_PDF).exists() else "."
        morceaux.append(
            f"<p>Générée le {quand} : <code>{escape(str(c.sorties / 'Fiche urgence.html'))}</code>{icloud}</p>"
        )
    if verifiee:
        morceaux.append(f"<p class=\"doux\">Numéros revérifiés sur les sites officiels le "
                        f"{time.strftime('%d/%m/%Y', time.localtime(float(verifiee)))}.</p>")  # fmt: skip
    return "\n".join(morceaux)


IMPORTANTS = {"google", "apple", "microsoft", "amazon", "paypal", "yahoo", "proton", "facebook", "instagram",
              "laposte", "ameli", "impots", "franceconnect"}  # fmt: skip


def hygiene(base: Base, maintenant: float | None = None) -> tuple[int, list[str]]:
    """Le score « Hygiène numérique » (0 à 100) et les 3 actions qui le feraient le plus monter."""
    from bouclier import config
    from bouclier.comptes import inventaire, regroupement
    from bouclier.fuites import croisement, hibp

    m = maintenant or time.time()
    retraits: list[tuple[int, str]] = []
    if base.lire_meta("inventaire_le") is None:
        retraits.append((10, "Lance l'inventaire de tes comptes : bouclier inventaire"))
    fuites = croisement.croiser(hibp.ListeFuites(config.chemins().caches).fuites(), croisement.comptes_surveilles(base))
    for c in fuites[:3]:
        quand = c.fuite.date.strftime("%m/%Y") if c.fuite.date else "date inconnue"
        retraits.append((14, f"Change le mot de passe de {c.compte.nom} (fuite de {quand}) et partout où tu l'as"
                             " réutilisé"))  # fmt: skip
    lignes = inventaire.lignes(base)
    a_supprimer = [x for x in lignes if x.statut == "a_supprimer"]
    if a_supprimer:
        texte = f"Supprime les {len(a_supprimer)} compte(s) marqués « à supprimer » (liens dans la liste ci-dessous)"
        retraits.append((min(10, 2 * len(a_supprimer)), texte))
    doubles = []
    for x in lignes:
        service = regroupement.service(x.id)
        actif = x.nature == "compte" and x.statut not in ("supprime", "a_supprimer")
        if actif and (x.id in IMPORTANTS or x.categorie == "banque") and service and service.double_auth:
            doubles.append(x.nom.split(" (")[0])
    if doubles:
        retraits.append((10, "Active la double authentification sur tes comptes importants : "
                             + ", ".join(sorted(set(doubles))[:4])))  # fmt: skip
    generee = base.lire_meta("fiche_generee_le")
    if generee is None:
        retraits.append((9, "Prépare ta fiche urgence : bouclier urgence editer, puis bouclier urgence"))
    elif m - float(generee) > 182 * 86400:
        retraits.append((5, "Relis et régénère ta fiche urgence : bouclier urgence editer"))
    if base.lire_meta("gmail_releve_le") is None:
        retraits.append((5, "Relie Gmail en lecture seule pour que les mails piégés soient repérés"
                            " (ACTIONS_HUMAINES.md)"))  # fmt: skip
    a_trier = [x for x in lignes if x.statut == "a_trier" and x.nature == "compte"]
    if len(a_trier) > 20:
        retraits.append((3, f"Trie tes {len(a_trier)} comptes : garde ou supprime ceux qui ne servent plus"))
    score = max(0, 100 - min(100, sum(r for r, _ in retraits)))
    actions = [texte for _, texte in sorted(retraits, key=lambda r: -r[0])[:3]]
    return score, actions


def _section_hygiene(base: Base) -> str:
    score, actions = hygiene(base)
    couleur = "var(--vert)" if score >= 80 else "var(--orange)" if score >= 50 else "var(--rouge)"
    morceaux = [f'<div class="carte"><h2 style="margin-top:0;border:0">Hygiène numérique : '
                f'<span style="color:{couleur}">{score}/100</span></h2>']  # fmt: skip
    if actions:
        morceaux.append("<p>Les 3 actions qui comptent le plus :</p><ol>")
        morceaux += [f"<li>{escape(a)}</li>" for a in actions]
        morceaux.append("</ol>")
    else:
        morceaux.append("<p>Rien d'urgent. Continue de vérifier les messages douteux avant d'agir.</p>")
    morceaux.append("</div>")
    return "\n".join(morceaux)


SECTIONS: list[Section] = [_section_hygiene, _section_arnaques, _section_fuites, _section_comptes, _section_urgence]


def construire(base: Base, sections: list[Section] | None = None) -> str:
    corps = "\n".join(s(base) for s in (sections or SECTIONS))
    maj = time.strftime("%d/%m/%Y à %H:%M")
    return (
        '<!doctype html>\n<html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Bouclier</title><style>{STYLE}</style></head><body><main>"
        f'<h1>🛡️ Bouclier</h1><p class="doux">Mis à jour le {maj}. Ce fichier reste sur ton Mac.</p>'
        f"{corps}</main></body></html>\n"
    )


def ecrire(base: Base, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(f".{chemin.name}.{threading.get_ident()}.tmp")  # un nom par fil du démon
    temporaire.write_text(construire(base), encoding="utf-8")
    os.chmod(temporaire, 0o600)
    os.replace(temporaire, chemin)
    return chemin
