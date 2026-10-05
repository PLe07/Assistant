"""Le rapport HTML local (`demarrage rapport`) : en français, clair ou sombre, sans rien charger d'Internet.

En haut : le résumé et ce que tu gagnerais. Ensuite : la courbe des ouvertures de session, le classement par
impact (une fiche par élément, avec la commande pour agir et celle pour annuler), les éléments de macOS (repliés),
le bonus zsh, et ce que le Nettoyeur a pu voir ou non.
"""

from __future__ import annotations

import html
import os
import time
from pathlib import Path, PurePosixPath
from typing import Any

from modules.demarrage.actions.desactiver import commandes_affichees
from modules.demarrage.analyse import Bilan, Element
from modules.demarrage.modele import SOURCES

JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
MOIS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
TYPES = {
    "agent_utilisateur": "Agent de ta session",
    "agent_global": "Agent pour tous les comptes",
    "daemon_global": "Service système (daemon)",
    "apple": "macOS",
    "agent_app": "Agent intégré à une app",
    "daemon_app": "Service intégré à une app",
    "ouverture_app": "Assistant d'ouverture d'une app",
    "ouverture": "Ouverture à la connexion",
    "launchd": "Chargé par launchd",
    "extension": "Extension système",
    "assistant_privilegie": "Assistant privilégié",
    "cron": "Tâche planifiée (cron)",
}


def e(texte: Any) -> str:
    return html.escape(str(texte), quote=True)


def nombre(x: float, decimales: int = 0) -> str:
    """À la française : virgule décimale, espace fine pour les milliers."""
    texte = f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return texte


def memoire(mo: float | None) -> str:
    if mo is None:
        return "—"
    return f"{nombre(mo / 1024, 1)} Go" if mo >= 1024 else f"{nombre(mo)} Mo"


def secondes(s: float | None) -> str:
    if s is None:
        return "—"
    if s >= 120:
        return f"{nombre(s / 60, 1)} min"
    return f"{nombre(s, 1 if s < 10 else 0)} s"


def date_courte(t: float) -> str:
    lt = time.localtime(t)
    return f"{JOURS[lt.tm_wday]} {lt.tm_mday}/{lt.tm_mon}"


def date_longue(t: float) -> str:
    lt = time.localtime(t)
    return f"{lt.tm_mday} {MOIS[lt.tm_mon - 1]} {lt.tm_year} à {lt.tm_hour:02d}:{lt.tm_min:02d}"


def il_y_a(t: float | None, maintenant: float) -> str:
    if t is None:
        return "jamais vue ou inconnue"
    jours = int((maintenant - t) // 86400)
    return "aujourd'hui" if jours <= 0 else "hier" if jours == 1 else f"il y a {jours} jours"


AUCUNE_SESSION = "Pas encore d'ouverture de session observée : la courbe commencera à ta prochaine connexion."
UNE_SESSION = "Une seule ouverture de session observée pour l'instant : la courbe apparaîtra à partir de la deuxième."
RIEN_D_AUTRE = '<p class="vide">Rien d\'autre que macOS ne se lance tout seul.</p>'


def calme(s: dict[str, Any]) -> str:
    return secondes(s.get("calme_s")) if s.get("calme_s") is not None else "pas calme en 5 min"


# --- la courbe des sessions ------------------------------------------------------------------------------------------


def _pas(maximum: float) -> float:
    for p in (5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600):
        if maximum / p <= 4:
            return p
    return 7200


def courbe(sessions: list[dict[str, Any]]) -> str:
    """Deux séries en secondes, un seul axe : démarrage → connexion, connexion → calme."""
    points = [s for s in sessions if s.get("connexion")]
    if len(points) < 2:
        if not points:
            return f'<p class="vide">{AUCUNE_SESSION}</p>'
        return f'<p class="vide">{UNE_SESSION}</p>'
    series = [
        ("demarrage", "Démarrage → connexion", [s.get("demarrage_s") for s in points]),
        ("calme", "Connexion → calme", [s.get("calme_s") for s in points]),
    ]
    valeurs = [v for _, _, vs in series for v in vs if v is not None]
    pas = _pas(max(valeurs) if valeurs else 60)
    haut = pas * max(1, -(-max(valeurs or [pas]) // pas))
    larg, haut_svg, g, d, h, b = 640, 240, 58, 84, 14, 30
    en_minutes = haut >= 120

    def graduer(v: float) -> str:  # une seule unité sur l'axe
        if en_minutes:
            return "0" if v == 0 else f"{nombre(v / 60, 0 if v % 60 == 0 else 1)} min"
        return f"{nombre(v)} s"

    x = lambda i: g + (larg - g - d) * (i / (len(points) - 1))  # noqa: E731
    y = lambda v: h + (haut_svg - h - b) * (1 - v / haut)  # noqa: E731
    parties = [
        f'<svg viewBox="0 0 {larg} {haut_svg}" class="courbe" role="img" aria-label="Temps d\'ouverture de session, '
        f'session par session">'
    ]
    graduation = 0.0
    while graduation <= haut + 1e-9:
        parties.append(
            f'<line class="grille" x1="{g}" x2="{larg - d}" y1="{y(graduation):.1f}" y2="{y(graduation):.1f}"/>'
        )
        texte = e(graduer(graduation))
        parties.append(f'<text class="axe" x="{g - 8}" y="{y(graduation) + 4:.1f}" text-anchor="end">{texte}</text>')
        graduation += pas
    etiquettes = {0, len(points) - 1} | ({(len(points) - 1) // 2} if len(points) > 4 else set())
    for i, s in enumerate(points):
        if i in etiquettes:
            jour = e(date_courte(s["connexion"]))
            parties.append(f'<text class="axe" x="{x(i):.1f}" y="{haut_svg - 8}" text-anchor="middle">{jour}</text>')
    fin_labels: list[tuple[float, str, str]] = []
    for cle, _, vs in series:
        morceaux: list[list[str]] = []
        courant: list[str] = []
        for i, v in enumerate(vs):
            if v is None:
                if courant:
                    morceaux.append(courant)
                courant = []
            else:
                courant.append(f"{x(i):.1f},{y(v):.1f}")
        if courant:
            morceaux.append(courant)
        for m in morceaux:
            if len(m) > 1:
                parties.append(f'<polyline class="serie s-{cle}" points="{" ".join(m)}"/>')
        for i, v in enumerate(vs):
            if v is not None:
                parties.append(f'<circle class="point s-{cle}" cx="{x(i):.1f}" cy="{y(v):.1f}" r="4"/>')
        derniere = next(((i, v) for i, v in reversed(list(enumerate(vs))) if v is not None), None)
        if derniere:
            fin_labels.append((y(derniere[1]), cle, secondes(derniere[1])))
    fin_labels.sort()
    for k in range(1, len(fin_labels)):  # deux étiquettes trop proches : on écarte la seconde
        if fin_labels[k][0] - fin_labels[k - 1][0] < 14:
            fin_labels[k] = (fin_labels[k - 1][0] + 14, fin_labels[k][1], fin_labels[k][2])
    for yy, _, texte in fin_labels:
        parties.append(f'<text class="valeur" x="{larg - d + 10}" y="{yy + 4:.1f}">{e(texte)}</text>')
    parties.append(f'<line class="repere" x1="0" x2="0" y1="{h}" y2="{haut_svg - b}" visibility="hidden"/>')
    largeur_zone = (larg - g - d) / (len(points) - 1)
    for i, s in enumerate(points):
        bulle = (
            f"{date_longue(s['connexion'])} · démarrage → connexion : {secondes(s.get('demarrage_s'))} · "
            f"connexion → calme : {calme(s)}"
        )
        parties.append(
            f'<rect class="zone" x="{x(i) - largeur_zone / 2:.1f}" y="{h}" width="{largeur_zone:.1f}" '
            f'height="{haut_svg - h - b}" data-x="{x(i):.1f}" data-bulle="{e(bulle)}" tabindex="0"/>'
        )
    parties.append("</svg>")
    legende = "".join(f'<span class="cle"><span class="trait s-{cle}"></span>{e(nom)}</span>' for cle, nom, _ in series)
    lignes = "".join(
        f"<tr><td>{e(date_longue(s['connexion']))}</td><td>{e(secondes(s.get('demarrage_s')))}</td>"
        f"<td>{e(calme(s))}</td></tr>"
        for s in points
    )
    tableau = (
        f'<details class="chiffres"><summary>Voir les chiffres</summary><table><thead><tr><th>Connexion</th>'
        f"<th>Démarrage → connexion</th><th>Connexion → calme</th></tr></thead><tbody>{lignes}</tbody>"
        "</table></details>"
    )
    cadre = f'<div class="cadre-courbe">{"".join(parties)}<div class="bulle" hidden></div></div>'
    return f'<div class="legende">{legende}</div>{cadre}{tableau}'


# --- les fiches -------------------------------------------------------------------------------------------------------


def _mesures(el: Element, maintenant: float) -> str:
    m = el.metriques
    lignes = [
        ("Processeur à l'ouverture", secondes(m.cpu_session_s) + (" sur 5 minutes" if m.cpu_session_s else "")),
        ("Processeur moyen", "—" if m.cpu_croisiere_pct is None else f"{nombre(m.cpu_croisiere_pct, 1)} % d'un cœur"),
        ("Mémoire", memoire(m.memoire_mo) if m.mesure else "—"),
        ("Énergie", "—" if m.energie is None else nombre(m.energie, 1)),
        ("Veille", "l'empêche" if "empêche la veille" in el.drapeaux else "ne l'empêche pas" if m.mesure else "—"),
    ]
    if el.fiche.app_parente:
        lignes.append(("Dernière ouverture de l'app", il_y_a(el.fiche.derniere_utilisation_app, maintenant)))
    return "".join(f"<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>" for a, b in lignes)


def _code(texte: str) -> str:
    return f'<pre class="code">{e(texte)}</pre>' if texte else ""


def fiche(el: Element, rang: int, maintenant: float, uid: int) -> str:
    f = el.fiche
    impact = f"{nombre(el.impact)}/100" + (" estimé" if el.impact_estime else "")
    editeur = el.editeur or "éditeur inconnu"
    type_ = TYPES.get(f.source, f.source)
    drapeaux = "".join(f'<span class="drapeau">{e(d)}</span>' for d in el.drapeaux)
    agir, annuler = commandes_affichees(el, uid)
    effet = el.connaissance.effet if el.connaissance else ""
    ou = [
        ("Identifiant", f.id),
        ("Label", f.label),
        ("Fichier", f.chemin_plist or "—"),
        ("Programme", f.programme or "—"),
        (
            "Quand",
            f.declencheurs.resume()
            if f.source not in ("ouverture", "ouverture_app", "extension")
            else "à l'ouverture de session",
        ),
        ("Emplacement", SOURCES.get(f.source, ("", f.source))[1]),
    ]
    if f.details.get("relances"):
        ou.append(
            ("Lancements", f"{f.details['relances']} (dernier code de sortie : {f.details.get('dernier_code', '—')})")
        )
    if el.premiere_vue:
        ou.append(("Vu pour la première fois", date_longue(el.premiere_vue)))
    details = "".join(f"<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>" for a, b in ou)
    if el.verdict.code == "apple":
        action = "<p>Fait partie de macOS : on n'y touche pas.</p>"
    elif not agir:
        action = f"<p>{e('Rien à faire.' if el.verdict.action == 'aucune' else '')}</p>"
    elif el.verdict.action == "verifier":
        action = f"<h4>Pour le vérifier</h4>{_code(agir)}" + (
            f"<h4>Pour annuler</h4>{_code(annuler)}" if annuler else ""
        )
    else:
        titre = "À taper toi-même" if el.verdict.action == "instructions" else "Pour agir"
        action = f"<h4>{titre}</h4>{_code(agir)}" + (f"<h4>Pour annuler</h4>{_code(annuler)}" if annuler else "")
        if effet:
            action += f'<p class="effet">Si tu le désactives : {e(effet)}</p>'
    largeur = max(0.0, min(100.0, el.impact))
    return f"""<article class="fiche v-{el.verdict.code}" id="f-{e(f.id)}">
  <div class="tete">
    <span class="rang">{rang}</span>
    <div class="titre"><h3>{e(el.nom)}</h3><p class="qui">{e(editeur)} · {e(type_)}</p></div>
    <span class="verdict">{el.verdict.emoji} {e(el.verdict.titre)}</span>
  </div>
  <div class="impact"><div class="jauge" role="meter" aria-valuemin="0" aria-valuemax="100"
    aria-valuenow="{el.impact:.0f}" aria-label="Impact"><span style="width:{largeur:.0f}%"></span></div>
    <span class="note">Impact {e(impact)}</span></div>
  <p class="role">{e(el.role)}</p>
  <p class="raison"><strong>Pourquoi :</strong> {e(el.verdict.raison)}.</p>
  {f'<p class="drapeaux">{drapeaux}</p>' if drapeaux else ""}
  <dl class="mesures">{_mesures(el, maintenant)}</dl>
  <details class="plus"><summary>Où il est, et comment agir</summary>
    <dl class="details">{details}</dl>{action}</details>
</article>"""


# --- la page ---------------------------------------------------------------------------------------------------------


def resume(bilan: Bilan, reglages: dict[str, Any]) -> tuple[str, str]:
    actifs, couteux, apple = bilan.actifs(), bilan.couteux(reglages), len(bilan.apple)
    mesure = any(el.metriques.mesure for el in bilan.elements)
    plusieurs = len(actifs) > 1
    s_, nt = ("s", "nt") if plusieurs else ("", "")
    phrase = f"{len(actifs)} élément{s_} se lance{nt} tout seul{s_}"
    phrase += f" (sans compter les {apple} de macOS)." if apple else "."
    if not mesure:
        phrase += (
            " Je n'ai pas encore mesuré ce qu'ils coûtent : lance « demarrage mesurer », ou attends ta "
            "prochaine ouverture de session si la surveillance est allumée."
        )
    elif couteux:
        mem = sum(el.metriques.memoire_mo or 0 for el in couteux)
        cpu = sum(el.metriques.cpu_session_s or 0 for el in couteux)
        veilles = sum(1 for el in couteux if "empêche la veille" in el.drapeaux)
        morceaux = [f"environ {memoire(mem)} de mémoire"]
        if cpu:
            morceaux.append(f"{secondes(cpu)} de processeur à chaque ouverture de session")
        if veilles:
            s_, nt = ("s", "nt") if veilles > 1 else ("", "")
            morceaux.append(f"{veilles} programme{s_} empêche{nt} ton Mac de se mettre en veille")
        liste = ", ".join(morceaux[:-1]) + (" et " if len(morceaux) > 1 else "") + morceaux[-1]
        phrase += f" {len(couteux)} te coûte{'nt' if len(couteux) > 1 else ''} vraiment : {liste}."
    else:
        phrase += " Aucun ne te coûte vraiment : ton démarrage est sain."
    g = bilan.gains
    if g.elements:
        pluriel = "s" if g.veilles > 1 else ""
        veilles_txt = f", et {g.veilles} mise{pluriel} en veille débloquée{pluriel}" if g.veilles else ""
        gain = (
            f"Si tu coupes les {len(g.elements)} éléments 💤 et 👻 : environ {memoire(g.memoire_mo)} de mémoire "
            f"libérée, {secondes(g.cpu_session_s)} de processeur en moins à chaque ouverture de session{veilles_txt}."
        )
    else:
        gain = "Rien à couper : aucun élément 💤 ni 👻."
    return phrase, gain


def construire(
    bilan: Bilan,
    reglages: dict[str, Any],
    sessions: list[dict[str, Any]],
    zsh: list[dict[str, Any]],
    uid: int,
    racine_assistant: str = "~/Assistant",
) -> str:
    maintenant = bilan.ts
    phrase, gain = resume(bilan, reglages)
    compte = {
        code: sum(1 for el in bilan.elements if el.verdict.code == code)
        for code in ("utile", "inutile", "orphelin", "inconnu", "apple")
    }
    puces = "".join(
        f'<span class="puce">{emoji} {compte[code]} {e(nom)}</span>'
        for code, emoji, nom in [
            ("inutile", "💤", "inutiles au démarrage"),
            ("orphelin", "👻", "orphelins"),
            ("inconnu", "⚠️", "à vérifier"),
            ("utile", "✅", "utiles"),
            ("apple", "🍎", "de macOS"),
        ]
    )
    classement = "".join(fiche(el, i, maintenant, uid) for i, el in enumerate(bilan.classement, start=1))
    apple = "".join(
        f'<li>{e(el.nom)} <span class="discret">({e(PurePosixPath(el.fiche.chemin_plist or el.fiche.label).name)})'
        "</span></li>"
        for el in bilan.apple
    )
    collecteurs = "".join(
        f"<li>{'✅' if c.etat == 'ok' else '⚠️'} <strong>{e(c.nom)}</strong> {e(c.etat)}"
        f'{" : " + e(c.detail) if c.detail else ""} <span class="discret">({c.nombre})</span></li>'
        for c in bilan.inventaire.collecteurs
    )
    dernier_zsh = zsh[-1] if zsh else None
    if dernier_zsh and dernier_zsh.get("mediane_ms") is not None:
        causes = "".join(
            f"<li>{e(c['cause'])} : {nombre(float(c['ms']))} ms</li>" for c in dernier_zsh.get("causes", [])
        )
        suspects = "".join(
            f"<li>{e(s['fichier'])}, ligne {s['ligne']} : {e(s['cause'])} — {e(s['conseil'])}</li>"
            for s in bilan.inventaire.shell.get("suspects", [])
        )
        verdict_zsh = "rapide" if dernier_zsh["mediane_ms"] <= reglages["zsh"]["seuil_ms"] else "lent"
        bloc_zsh = (
            f"<p>Un Terminal s'ouvre en <strong>{nombre(dernier_zsh['mediane_ms'])} ms</strong> (médiane de "
            f"{len(dernier_zsh.get('essais_ms', [])) or 5} essais) : c'est {verdict_zsh}.</p>"
            + (f"<h4>Ce qui le ralentit (mesuré par zprof)</h4><ul>{causes}</ul>" if causes else "")
            + (f"<h4>Ce que j'ai repéré dans tes fichiers zsh</h4><ul>{suspects}</ul>" if suspects else "")
            + '<p class="discret">Je ne modifie jamais tes fichiers zsh : à toi de choisir.</p>'
        )
    else:
        bloc_zsh = '<p class="vide">Pas encore mesuré.</p>'
    alias = f'alias demarrage="{racine_assistant}/.venv/bin/python {racine_assistant}/demarrage.py"'
    seuil, duree = nombre(reglages["calme"]["seuil_cpu_pct"]), reglages["calme"]["duree_s"]
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nettoyeur de démarrage</title>
<style>{STYLE}</style>
</head>
<body>
<main class="page">
<header class="entete">
  <div><p class="surtitre">Nettoyeur de démarrage · {e(date_longue(maintenant))}</p>
  <h1>Ce qui se lance tout seul sur ton Mac</h1></div>
  <button type="button" class="theme" aria-label="Changer de thème" title="Clair / sombre">🌓</button>
</header>
<section class="resume">
  <p class="phrase">{e(phrase)}</p>
  <p class="gain">{e(gain)}</p>
  <p class="puces">{puces}</p>
  <p class="discret">Rien n'est désactivé sans ta commande, et tout se défait.
  Les commandes « demarrage … » supposent l'alias <code>{e(alias)}</code> (à ajouter une fois à ton ~/.zshrc).</p>
</section>
<section><h2>Ouverture de session</h2>
  <p class="discret">« Calme » : le moment où le processeur reste sous {seuil} % pendant {duree} secondes.
  Regarde la courbe baisser après tes choix.</p>
  {courbe(sessions)}
</section>
<section><h2>Classement par impact</h2>{classement or RIEN_D_AUTRE}</section>
<section><h2>🍎 macOS ({len(bilan.apple)})</h2>
  <details><summary>Voir les éléments de macOS (on n'y touche jamais)</summary>
  <ul class="apple">{apple}</ul></details></section>
<section><h2>Bonus : l'ouverture du Terminal</h2>{bloc_zsh}</section>
<section><h2>Ce que j'ai pu voir</h2><ul class="collecteurs">{collecteurs}</ul></section>
<footer class="discret">Fait sur ton Mac, sans Internet ni IA.
Données : {e(racine_assistant)}/donnees/demarrage.</footer>
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def ecrire(chemin: Path, contenu: str) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(contenu, encoding="utf-8")
    os.chmod(temporaire, 0o600)
    os.replace(temporaire, chemin)
    return chemin


STYLE = """
:root{color-scheme:light;--fond:#f9f9f7;--surface:#fcfcfb;--encre:#0b0b0b;--encre-2:#52514e;--discret:#898781;
--grille:#e1e0d9;--axe:#c3c2b7;--bord:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--jauge:#cde2fb;--code:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--fond:#0d0d0d;
--surface:#1a1a19;
--encre:#fff;--encre-2:#c3c2b7;--grille:#2c2c2a;--axe:#383835;--bord:rgba(255,255,255,.10);--s1:#3987e5;
--s2:#d95926;
--jauge:#184f95;--code:#262624}}
:root[data-theme="dark"]{color-scheme:dark;--fond:#0d0d0d;--surface:#1a1a19;--encre:#fff;--encre-2:#c3c2b7;
--grille:#2c2c2a;--axe:#383835;--bord:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--jauge:#184f95;
--code:#262624}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--encre);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.page{max-width:960px;margin:0 auto;padding:24px 16px 48px}
.entete{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
h1{font-size:1.8rem;line-height:1.2;margin:.2rem 0 1rem}
h2{font-size:1.25rem;margin:2.2rem 0 .8rem}
h3{font-size:1.05rem;margin:0}
h4{font-size:.9rem;margin:1rem 0 .3rem;color:var(--encre-2)}
.surtitre,.discret,.qui{color:var(--encre-2);font-size:.9rem;margin:0}
.theme{border:1px solid var(--bord);background:var(--surface);color:var(--encre);border-radius:8px;font-size:1.1rem;
width:40px;height:40px;cursor:pointer;line-height:1}
section{background:var(--surface);border:1px solid var(--bord);border-radius:12px;padding:16px 20px;margin-top:16px}
section h2:first-child{margin-top:0}
.resume .phrase{font-size:1.2rem;font-weight:600;margin:0 0 .6rem}
.resume .gain{margin:0 0 .8rem}
.puces{display:flex;flex-wrap:wrap;gap:8px}
.puce,.drapeau{border:1px solid var(--bord);border-radius:999px;padding:2px 10px;font-size:.85rem;
white-space:nowrap}
code,.code{font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--code);border-radius:6px}
code{padding:1px 4px;overflow-wrap:anywhere}
.code{padding:10px 12px;margin:.3rem 0;white-space:pre-wrap;overflow-wrap:anywhere}
.fiche{border-top:1px solid var(--bord);padding:16px 0}
.fiche:first-child{border-top:0;padding-top:4px}
.tete{display:flex;align-items:flex-start;gap:12px}
.rang{font-variant-numeric:tabular-nums;color:var(--discret);min-width:1.6rem;font-weight:600}
.titre{flex:1;min-width:0}
.titre h3{overflow-wrap:anywhere}
.verdict{white-space:nowrap;font-size:.9rem;font-weight:600}
.impact{display:flex;align-items:center;gap:10px;margin:.6rem 0 0 2.4rem}
.jauge{flex:0 1 220px;height:8px;background:var(--jauge);border-radius:4px;overflow:hidden}
.jauge span{display:block;height:100%;background:var(--s1);border-radius:4px}
.note{font-size:.85rem;color:var(--encre-2);white-space:nowrap}
.role,.raison,.drapeaux,.mesures,.plus{margin-left:2.4rem}
.role{margin-top:.5rem;margin-bottom:.2rem}
.raison{margin-top:.2rem;margin-bottom:.2rem;color:var(--encre-2)}
.drapeaux{display:flex;flex-wrap:wrap;gap:6px;margin-top:.4rem;margin-bottom:.4rem}
.mesures,.details{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px 16px;
margin-top:.6rem;margin-bottom:.4rem}
.details{grid-template-columns:1fr}
dl div{min-width:0} dt{font-size:.8rem;color:var(--encre-2)} dd{margin:0;overflow-wrap:anywhere}
p,li,h1,h3{overflow-wrap:anywhere}
.details div{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:8px}
summary{cursor:pointer;color:var(--encre-2);font-size:.9rem}
.effet{font-size:.9rem;color:var(--encre-2)}
.legende{display:flex;flex-wrap:wrap;gap:16px;font-size:.9rem;margin:.4rem 0}
.cle{display:inline-flex;align-items:center;gap:6px}
.trait{display:inline-block;width:16px;height:2px;border-radius:1px}
.trait.s-demarrage{background:var(--s1)} .trait.s-calme{background:var(--s2)}
.cadre-courbe{position:relative}
.courbe{width:100%;height:auto;display:block}
.grille{stroke:var(--grille);stroke-width:1}
.axe{fill:var(--discret);font-size:11px;font-variant-numeric:tabular-nums}
.valeur{fill:var(--encre);font-size:12px;font-weight:600}
.serie{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.serie.s-demarrage{stroke:var(--s1)} .serie.s-calme{stroke:var(--s2)}
.point{stroke:var(--surface);stroke-width:2}
.point.s-demarrage{fill:var(--s1)} .point.s-calme{fill:var(--s2)}
.zone{fill:transparent;outline:none}
.repere{stroke:var(--axe);stroke-width:1}
.bulle{position:absolute;top:0;transform:translateX(-50%);background:var(--surface);color:var(--encre);
border:1px solid var(--bord);border-radius:8px;padding:6px 10px;font-size:.8rem;max-width:280px;pointer-events:none;
box-shadow:0 4px 16px rgba(0,0,0,.15)}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin-top:.5rem}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--bord)} td{font-variant-numeric:tabular-nums}
.apple{columns:2 260px;font-size:.9rem}
.collecteurs{list-style:none;padding:0;margin:0} .collecteurs li{margin:.2rem 0}
.vide{color:var(--encre-2)}
footer{margin-top:24px;text-align:center}
@media (max-width:560px){.verdict{white-space:normal;text-align:right;max-width:40%}
.impact,.role,.raison,.drapeaux,.mesures,.plus{margin-left:0}.details div{grid-template-columns:1fr;gap:0}}"""

SCRIPT = """
(function(){
  var racine=document.documentElement, bouton=document.querySelector('.theme');
  try{var choisi=localStorage.getItem('demarrage-theme');
    if(choisi){racine.setAttribute('data-theme',choisi);}}catch(e){}
  bouton.addEventListener('click',function(){
    var theme=racine.getAttribute('data-theme');
    var sombre=theme==='dark'||(!theme&&matchMedia('(prefers-color-scheme: dark)').matches);
    var nouveau=sombre?'light':'dark'; racine.setAttribute('data-theme',nouveau);
    try{localStorage.setItem('demarrage-theme',nouveau);}catch(e){}
  });
  document.querySelectorAll('.cadre-courbe').forEach(function(cadre){
    var svg=cadre.querySelector('svg'), bulle=cadre.querySelector('.bulle');
    var repere=svg.querySelector('.repere');
    function montrer(zone){
      var x=parseFloat(zone.getAttribute('data-x')); repere.setAttribute('x1',x); repere.setAttribute('x2',x);
      repere.setAttribute('visibility','visible');
      bulle.textContent=zone.getAttribute('data-bulle'); bulle.hidden=false;
      bulle.style.left=(x/svg.viewBox.baseVal.width*svg.getBoundingClientRect().width)+'px';
    }
    function cacher(){repere.setAttribute('visibility','hidden'); bulle.hidden=true;}
    svg.querySelectorAll('.zone').forEach(function(z){
      z.addEventListener('mouseenter',function(){montrer(z);}); z.addEventListener('focus',function(){montrer(z);});
      z.addEventListener('mouseleave',cacher); z.addEventListener('blur',cacher);
    });
  });
})();
"""
