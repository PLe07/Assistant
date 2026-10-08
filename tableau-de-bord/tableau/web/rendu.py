"""Le HTML de la page : une coquille (`templates/base.html`) et des fragments, tous dessinés ici, côté serveur.

La mise à jour en direct recharge seulement le fragment de la page ouverte (même code, même rendu). Tout texte venu
des modules est échappé (et déjà caviardé par `vues.py`). Les liens portent le jeton ; aucun lien ne sort du Mac.
"""

from __future__ import annotations

import html
from functools import cache
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import quote, urlencode

from tableau import textes
from tableau.web import graphiques

DOSSIER = Path(__file__).resolve().parent
ONGLETS = [("/", "Accueil"), ("/credits", "Crédits"), ("/ressources", "Ressources"), ("/integrite", "Intégrité"),
           ("/journal", "Journal")]  # fmt: skip


def _e(x: Any) -> str:
    return html.escape("" if x is None else str(x), quote=True)


@cache
def _gabarit() -> Template:
    return Template((DOSSIER / "templates" / "base.html").read_text(encoding="utf-8"))


def lien(chemin: str, jeton: str, **params: Any) -> str:
    valeurs = {"t": jeton, **{k: v for k, v in params.items() if v is not None}}
    return f"{chemin}?{urlencode(valeurs, quote_via=quote)}"


def page(titre: str, contenu: str, jeton: str, fragment: str, actif: str) -> str:
    courant = ' aria-current="page"'
    onglets = "".join(
        f'<li><a href="{_e(lien(chemin, jeton))}"{courant if chemin == actif else ""}>{_e(nom)}</a></li>'
        for chemin, nom in ONGLETS
    )
    return _gabarit().substitute(
        titre=_e(titre),
        css=_e(lien("/static/app.css", jeton)),
        js=_e(lien("/static/app.js", jeton)),
        accueil=_e(lien("/", jeton)),
        onglets=onglets,
        fragment=_e(fragment),
        contenu=contenu,
    )


def erreur(code: int, message: str) -> str:
    """Une page d'erreur minimale, sans lien ni ressource (on n'a peut-être pas le jeton)."""
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Tableau de bord</title></head>"
        f"<body><h1>{code}</h1><p>{_e(message)}</p></body></html>"
    )


# --- morceaux communs ---------------------------------------------------------------------------------------------


def _pastille(c: dict[str, Any]) -> str:
    return (
        f'<span class="pastille p-{_e(c["pastille"])}"><span aria-hidden="true">{_e(c["pastille_emoji"])}</span> '
        f"{_e(c['pastille_libelle'])}</span>"
    )


def _mesures(c: dict[str, Any]) -> str:
    lignes: list[tuple[str, str]] = []
    if c["derniere_activite"]:
        lignes.append(("Dernière activité", _e(c["derniere_activite"])))
    if c["erreurs_24h"] is not None:
        lignes.append(("Erreurs sur 24 h", _e(c["erreurs_24h"])))
    if c["cpu_pct"] is not None:
        lignes.append(("Processeur", _e(textes.pourcent(c["cpu_pct"], 1))))
    if c["rss_mo"] is not None:
        lignes.append(("Mémoire", _e(textes.mo(c["rss_mo"]))))
    if c["credits_mois"] is not None:
        montant = textes.dollars(c["credits_mois"])
        if c["plafond_usd"]:
            montant += f" sur {textes.dollars(c['plafond_usd'])}"
        if c["credits_estimes"]:
            montant += " (estimé)"
        libelle = f"Crédits du mois : {montant}"
        lignes.append(("Crédits du mois", _e(montant) + graphiques.jauge(c["credits_mois"], c["plafond_usd"], libelle)))
    if c["prochaine"]:
        lignes.append(("Prochaine tâche", _e(c["prochaine"])))
    return "".join(f"<div><dt>{t}</dt><dd>{v}</dd></div>" for t, v in lignes)


def _carte(c: dict[str, Any], jeton: str) -> str:
    return (
        f'<li class="carte p-{_e(c["pastille"])}" data-module="{_e(c["id"])}" data-pastille="{_e(c["pastille"])}">'
        f'<a class="carte-lien" href="{_e(lien("/module/" + quote(c["id"]), jeton))}">'
        f'<span class="carte-tete"><span class="emoji" aria-hidden="true">{_e(c["emoji"])}</span>'
        f'<span class="carte-nom">{_e(c["nom"])}</span>{_pastille(c)}</span>'
        f'<span class="phrase">{_e(c["phrase"])}</span></a>'
        f'<dl class="mesures">{_mesures(c)}</dl></li>'
    )


def _bouton(texte: str, action: str, confirmer: str = "", corps: str = "", classe: str = "bouton") -> str:
    attributs = f' data-action="{_e(action)}"'
    if confirmer:
        attributs += f' data-confirmer="{_e(confirmer)}"'
    if corps:
        attributs += f" data-corps='{_e(corps)}'"
    return f'<button type="button" class="{classe}"{attributs}>{_e(texte)}</button>'


# --- fragments ----------------------------------------------------------------------------------------------------


def fragment_accueil(d: dict[str, Any], jeton: str) -> str:
    b = d["bandeau"]
    retenue = f'<p class="retenue">Notifications : {_e(b["retenue"])}</p>' if b["retenue"] else ""
    sourdine = (
        _bouton("Lever la sourdine", "/action/sourdine", corps='{"duree": "fin"}', classe="bouton-discret")
        if b["retenue"] and b["retenue"].startswith("en sourdine")
        else _bouton("Mettre les alertes en sourdine 1 h", "/action/sourdine", corps='{"duree": "1h"}',
                     classe="bouton-discret")
    )  # fmt: skip
    cartes = "".join(_carte(c, jeton) for c in d["cartes"])
    vide = "" if d["cartes"] else "<p>Aucun module observé pour l'instant.</p>"
    return (
        f'<section class="bandeau b-{_e(b["niveau"])}" aria-labelledby="titre-bandeau">'
        f'<h1 id="titre-bandeau">{_e(b["texte"])}</h1>{retenue}{sourdine}</section>'
        f'<h2 class="masque">Modules</h2><ul class="cartes">{cartes}</ul>{vide}'
    )


def fragment_module(d: dict[str, Any], jeton: str) -> str:
    c = d["carte"]
    morceaux = [
        f'<p class="retour"><a href="{_e(lien("/", jeton))}">← Tous les modules</a></p>',
        f'<h1><span aria-hidden="true">{_e(c["emoji"])}</span> {_e(c["nom"])} {_pastille(c)}</h1>',
        f'<p class="phrase-grande">{_e(c["phrase"])}</p><dl class="mesures">{_mesures(c)}</dl>',
    ]
    if d["problemes"]:
        lignes = "".join(f"<li>{_e(p['message'])}</li>" for p in d["problemes"])
        morceaux.append(f"<section><h2>À regarder</h2><ul>{lignes}</ul></section>")
    actions = []
    if d["diagnostic"]:
        actions.append(_bouton("Lancer le diagnostic", f"/action/diagnostic/{quote(c['id'])}",
                               confirmer=f"Lancer maintenant la commande de diagnostic de {c['nom']} ?"))  # fmt: skip
    if d["aide"]:
        actions.append(f'<p class="doux">Dans le Terminal : <code>{_e(d["aide"])}</code></p>')
    if actions:
        morceaux.append(f"<section><h2>Diagnostic</h2>{''.join(actions)}</section>")
    # Historique : 7 ou 30 jours.
    jours = d["jours"]
    autre = 30 if jours == 7 else 7
    s = d["series"]
    etiquettes = [p["etiquette"] for p in s]
    morceaux.append(
        f"<section><h2>Historique sur {jours} jours</h2>"
        f'<p><a href="{_e(lien("/module/" + quote(c["id"]), jeton, jours=autre))}">Voir {autre} jours</a></p>'
        '<div class="graphiques">'
        + graphiques.graphique("Temps en bonne santé (%)", etiquettes, [p["part_vert"] for p in s], "barres", 100.0,
                               lambda v: textes.pourcent(v), " %")
        + graphiques.graphique("Erreurs par jour", etiquettes, [p["erreurs"] for p in s], "barres",
                               format_valeur=lambda v: str(int(v)))
        + graphiques.graphique("Processeur moyen (%)", etiquettes, [p["cpu_moy"] for p in s], "ligne",
                               format_valeur=lambda v: textes.pourcent(v, 1))
        + graphiques.graphique("Mémoire moyenne (Mo)", etiquettes, [p["rss_moy"] for p in s], "ligne",
                               format_valeur=lambda v: textes.mo(v))
        + "</div></section>"
    )  # fmt: skip
    if d["attentes"] or d["historique_attentes"]:
        actuelles = "".join(
            f"<li><span class='statut s-{_e(a['statut'])}'>{_e(STATUTS.get(a['statut'], a['statut']))}</span> "
            f"{_e(a['libelle'])} : {_e(a['detail'])}</li>"
            for a in d["attentes"]
        )
        passees = "".join(
            f"<tr><td>{_e(h['quand'])}</td><td>{_e(h['attente'])}</td>"
            f"<td><span class='statut s-{_e(h['statut'])}'>{_e(STATUTS.get(h['statut'], h['statut']))}</span></td></tr>"
            for h in d["historique_attentes"]
        )
        tableau = (
            "<table><thead><tr><th scope='col'>Quand</th><th scope='col'>Attente</th><th scope='col'>Résultat</th>"
            f"</tr></thead><tbody>{passees}</tbody></table>"
            if passees
            else ""
        )
        morceaux.append(f"<section><h2>A-t-il fait son travail ?</h2><ul>{actuelles}</ul>{tableau}</section>")
    if d["files"]:
        lignes = "".join(
            f"<li>{_e(f['nom'])} : {_e(textes.pluriel(f['n'], 'document'))}"
            + (f", le plus ancien depuis {_e(textes.duree(f['plus_vieux_s']))}" if f["n"] else "")
            + "</li>"
            for f in d["files"]
        )
        morceaux.append(f"<section><h2>Files d'attente</h2><ul>{lignes}</ul></section>")
    if d["erreurs"]:
        lignes = "".join(
            f"<li><span class='doux'>{_e(e['quand'])}</span> {_e(e['message'])}</li>" for e in d["erreurs"]
        )
        morceaux.append(
            f"<section><h2>Derniers messages d'erreur (caviardés)</h2><ul class='erreurs'>{lignes}</ul></section>"
        )
    morceaux.append(_integrite_module(c, d, jeton))
    return "".join(morceaux)


STATUTS = {"tenue": "✓ fait", "manquee": "✗ manqué", "en_attente": "… en attente", "inactive": "– éteint"}


def _integrite_module(c: dict[str, Any], d: dict[str, Any], jeton: str) -> str:
    integ = d["integrite"]
    if integ is None:
        return "<section><h2>Intégrité du code</h2><p>Pas encore de référence.</p></section>"
    if not integ["ecarts"]:
        return "<section><h2>Intégrité du code</h2><p class='ok'>✓ Identique à la référence.</p></section>"
    lignes = "".join(f"<li>{_e(e.get('chemin'))} : {_e(e.get('genre'))}</li>" for e in integ["ecarts"][:50])
    combien = textes.pluriel(len(integ["ecarts"]), "fichier changé", "fichiers changés")
    return (
        f"<section><h2>Intégrité du code</h2><p>⚠️ {_e(combien)} depuis la référence.</p><ul>{lignes}</ul>"
        + _bouton("C'était moi, nouvelle référence", f"/action/reference/{quote(c['id'])}",
                  confirmer=f"Le code actuel de {c['nom']} deviendra la référence. Continuer ?")
        + " "
        + _bouton("Pas normal", f"/action/pas-normal/{quote(c['id'])}", classe="bouton-discret")
        + "</section>"
    )  # fmt: skip


def fragment_credits(d: dict[str, Any], jeton: str) -> str:
    projection = textes.dollars(d["projection_usd"]) if d["projection_usd"] is not None else "trop tôt pour le dire"
    plafonds = f" sur {textes.dollars(d['plafonds_usd'])} de plafonds" if d["plafonds_usd"] else ""
    reel = (
        f"<p>Coût réel de l'organisation (rapport officiel) : <b>{_e(textes.dollars(d['reel_usd']))}</b></p>"
        if d["reel_usd"] is not None
        else "<p class='doux'>Coût réel : non relevé (option éteinte, voir ACTIONS_HUMAINES.md).</p>"
        if not d["api_admin"]
        else "<p class='doux'>Coût réel : pas encore relevé.</p>"
    )
    precedent = (
        f"<p class='doux'>Mois précédent : {_e(textes.dollars(d['mois_precedent_usd']))}</p>"
        if d["mois_precedent_usd"] is not None
        else ""
    )
    lignes = "".join(_ligne_credits(m) for m in d["modules"])
    abonnement = (
        f"<p class='doux'>L'assistant passe par ton abonnement : son usage vaudrait "
        f"{_e(textes.dollars(d['abonnement_equivalent_usd']))} au tarif de l'API (non facturé).</p>"
        if d["abonnement_equivalent_usd"]
        else ""
    )
    return (
        f"<h1>Crédits Claude · {_e(d['mois'])}</h1>"
        f"<p class='chiffre'>{_e(textes.dollars(d['total_usd']))}<span class='doux'>{_e(plafonds)}</span></p>"
        f"<p>Projection à la fin du mois : <b>{_e(projection)}</b></p>{reel}{precedent}{abonnement}"
        "<table><thead><tr><th scope='col'>Module</th><th scope='col'>Ce mois-ci</th><th scope='col'>Plafond</th>"
        f"<th scope='col'>Projection</th></tr></thead><tbody>{lignes}</tbody></table>"
    )


def _ligne_credits(m: dict[str, Any]) -> str:
    estime = " (estimé)" if m["source"] == "estimation" else ""
    plafond = textes.dollars(m["plafond_usd"]) if m["plafond_usd"] else "—"
    jauge = ""
    if m["plafond_usd"]:
        jauge = graphiques.jauge(
            m["mois_usd"], m["plafond_usd"], f"{m['nom']} : {textes.pourcent(m['pct'])} du plafond"
        )
    projection = textes.dollars(m["projection_usd"]) if m["projection_usd"] is not None else "—"
    return (
        f"<tr><th scope='row'><span aria-hidden='true'>{_e(m['emoji'])}</span> {_e(m['nom'])}</th>"
        f"<td>{_e(textes.dollars(m['mois_usd']))}{estime}</td><td>{_e(plafond)}{jauge}</td>"
        f"<td>{_e(projection)}</td></tr>"
    )


def fragment_ressources(d: dict[str, Any], jeton: str) -> str:
    parts = []
    if d["part_cpu_mac"] is not None:
        parts.append(f"{textes.pourcent(d['part_cpu_mac'], 1)} de la charge du processeur du Mac")
    if d["part_memoire_mac"] is not None:
        parts.append(f"{textes.pourcent(d['part_memoire_mac'], 1)} de sa mémoire")
    lignes = "".join(
        f"<tr><th scope='row'><span aria-hidden='true'>{_e(m['emoji'])}</span> {_e(m['nom'])}</th>"
        f"<td>{_e(textes.pourcent(m['cpu_pct'], 1))}</td><td>{_e(textes.mo(m['rss_mo']))}</td></tr>"
        for m in d["modules"]
    )
    return (
        "<h1>Ressources</h1><h2 class='question'>Mon assistant me coûte-t-il de la batterie ?</h2>"
        f"<p class='phrase-grande'>{_e(d['phrase'])}</p>"
        + (f"<p class='doux'>Soit {_e(', '.join(parts))}.</p>" if parts else "")
        + "<table><thead><tr><th scope='col'>Module</th><th scope='col'>Processeur (moyenne 24 h)</th>"
        f"<th scope='col'>Mémoire</th></tr></thead><tbody>{lignes}</tbody></table>"
    )


def fragment_integrite(lignes: list[dict[str, Any]], jeton: str) -> str:
    morceaux = ["<h1>Intégrité du code</h1><p class='doux'>Le tableau de bord ne restaure jamais rien.</p>"]
    for m in lignes:
        statut = {"conforme": "✓ conforme", "changé": "⚠️ changé"}.get(m["statut"], m["statut"])
        details = f"Référence prise {m['reference']}" if m["reference"] else ""
        if m["controle"]:
            details += f" · contrôlé {m['controle']}"
        corps = ""
        if m["ecarts"]:
            fichiers = "".join(f"<li>{_e(e.get('chemin'))} : {_e(e.get('genre'))}</li>" for e in m["ecarts"][:20])
            corps = (
                f"<ul>{fichiers}</ul>"
                + _bouton("C'était moi, nouvelle référence", f"/action/reference/{quote(m['id'])}",
                          confirmer=f"Le code actuel de {m['nom']} deviendra la référence. Continuer ?")
                + " "
                + _bouton("Pas normal", f"/action/pas-normal/{quote(m['id'])}", classe="bouton-discret")
            )  # fmt: skip
        morceaux.append(
            f"<section class='ligne-integrite' data-module='{_e(m['id'])}'>"
            f"<h2><span aria-hidden='true'>{_e(m['emoji'])}</span> {_e(m['nom'])} : {_e(statut)}</h2>"
            f"<p class='doux'>{_e(details)}</p>{corps}</section>"
        )
    return "".join(morceaux)


def fragment_journal(evenements: list[dict[str, Any]], modules: list[tuple[str, str]], choisi: str | None,
                     jeton: str) -> str:  # fmt: skip
    marque = ' aria-current="true"'
    filtres = [f'<li><a href="{_e(lien("/journal", jeton))}"{"" if choisi else marque}>Tous</a></li>']
    for ident, nom in modules:
        courant = marque if ident == choisi else ""
        filtres.append(f'<li><a href="{_e(lien("/journal", jeton, module=ident))}"{courant}>{_e(nom)}</a></li>')
    lignes = "".join(
        f"<li class='g-{_e(e['gravite'])}'><span class='doux'>{_e(e['quand'])}</span> "
        f"<b>{_e(e['nom'])}</b> {_e(e['message'])}</li>"
        for e in evenements
    )
    return (
        "<h1>Journal</h1><nav aria-label='Filtrer par module'><ul class='filtres'>" + "".join(filtres) + "</ul></nav>"
        + (f"<ul class='journal'>{lignes}</ul>" if lignes else "<p>Rien de notable sur les 7 derniers jours.</p>")
    )  # fmt: skip
