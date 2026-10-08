"""Les graphiques de la page, dessinés en SVG (aucune bibliothèque, aucune ressource extérieure).

Un graphique = une seule mesure, un seul axe : barres fines (bout arrondi, posées sur la ligne de base, 2 px d'écart)
pour une part ou un compte par jour, courbe de 2 px pour une moyenne. Grille discrète, quelques étiquettes seulement.
Chaque colonne porte une infobulle (`<title>`, au survol), et chaque graphique a son tableau de chiffres
(« Voir les chiffres ») : la couleur ne porte jamais seule l'information. Les couleurs viennent de la feuille de style
(clair et sombre).
"""

from __future__ import annotations

import html
import itertools
from collections.abc import Callable

LARGEUR = 400.0
HAUTEUR = 190.0
GAUCHE = 58.0
DROITE = 8.0
HAUT = 12.0
BAS = 30.0
ECART = 2.0
BARRE_MAX = 18.0
_compteur = itertools.count(1)


def _e(x: object) -> str:
    return html.escape(str(x), quote=True)


def _nombre(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _graduation(maximum: float) -> float:
    """Un haut d'axe « rond » au-dessus du maximum."""
    if maximum <= 0:
        return 1.0
    for pas in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10_000):
        if maximum <= pas:
            return float(pas)
    return float(int(maximum) + 1)


def _barre(x: float, y: float, largeur: float, base: float) -> str:
    """Une barre au bout arrondi (4 px au plus), posée sur la ligne de base."""
    hauteur = base - y
    r = min(4.0, largeur / 2, hauteur)
    return (
        f"M{x:.1f},{base:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}H{x + largeur - r:.1f}"
        f"Q{x + largeur:.1f},{y:.1f} {x + largeur:.1f},{y + r:.1f}V{base:.1f}Z"
    )


def graphique(
    titre: str,
    etiquettes: list[str],
    valeurs: list[float | None],
    forme: str = "barres",
    maximum: float | None = None,
    format_valeur: Callable[[float], str] = _nombre,
    unite_axe: str = "",
) -> str:
    """Le SVG et son tableau. `maximum` fixe le haut de l'axe (100 pour une part), sinon il suit les données."""
    n = len(valeurs)
    ident = f"g{next(_compteur)}"
    connues = [v for v in valeurs if v is not None]
    haut_axe = maximum if maximum is not None else _graduation(max(connues, default=0.0))
    largeur_trace = LARGEUR - GAUCHE - DROITE
    base = HAUTEUR - BAS
    hauteur_trace = base - HAUT
    pas = largeur_trace / max(n, 1)

    def y_de(v: float) -> float:
        return base - max(0.0, min(v, haut_axe)) / haut_axe * hauteur_trace

    morceaux: list[str] = []
    for fraction in (0.0, 0.5, 1.0):
        y = base - fraction * hauteur_trace
        valeur = haut_axe * fraction
        morceaux.append(f'<line class="grille" x1="{GAUCHE}" x2="{LARGEUR - DROITE}" y1="{y:.1f}" y2="{y:.1f}"/>')
        morceaux.append(
            f'<text class="axe" x="{GAUCHE - 6}" y="{y + 4:.1f}" text-anchor="end">'
            f"{_e(_nombre(valeur) + unite_axe)}</text>"
        )
    # Quelques étiquettes de jours : la première, la dernière, et une au milieu.
    for i in sorted({0, n // 2, n - 1} if n > 2 else set(range(n))):
        x = GAUCHE + pas * i + pas / 2
        morceaux.append(
            f'<text class="axe" x="{x:.1f}" y="{HAUTEUR - 10}" text-anchor="middle">{_e(etiquettes[i])}</text>'
        )
    if forme == "barres":
        largeur_barre = max(1.0, min(pas - ECART, BARRE_MAX))  # des barres fines, centrées dans leur colonne
        for i, v in enumerate(valeurs):
            if v is None or v <= 0:
                continue
            x = GAUCHE + pas * i + (pas - largeur_barre) / 2
            morceaux.append(f'<path class="serie" d="{_barre(x, y_de(v), largeur_barre, base)}"/>')
    else:
        segment: list[str] = []
        segments: list[list[str]] = []
        for i, v in enumerate(valeurs):
            if v is None:
                if segment:
                    segments.append(segment)
                segment = []
                continue
            segment.append(f"{GAUCHE + pas * i + pas / 2:.1f},{y_de(v):.1f}")
        if segment:
            segments.append(segment)
        for s in segments:
            if len(s) > 1:
                morceaux.append(f'<polyline class="ligne" points="{" ".join(s)}"/>')
        if n <= 10:
            for i, v in enumerate(valeurs):
                if v is not None:
                    cx, cy = GAUCHE + pas * i + pas / 2, y_de(v)
                    morceaux.append(f'<circle class="point" cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>')
    # Zones de survol plus grandes que les marques, chacune avec son infobulle.
    for i, v in enumerate(valeurs):
        texte = "pas observé" if v is None else format_valeur(v)
        x = GAUCHE + pas * i
        morceaux.append(
            f'<rect class="survol" x="{x:.1f}" y="{HAUT}" width="{pas:.1f}" height="{hauteur_trace:.1f}">'
            f"<title>{_e(etiquettes[i])} : {_e(texte)}</title></rect>"
        )
    resume = (
        f"{len(connues)} jour{'s' if len(connues) > 1 else ''} observé{'s' if len(connues) > 1 else ''} sur {n}"
        + (f", de {format_valeur(min(connues))} à {format_valeur(max(connues))}" if connues else "")
    )
    lignes = "".join(
        f"<tr><th scope='row'>{_e(e)}</th><td>{_e('pas observé' if v is None else format_valeur(v))}</td></tr>"
        for e, v in zip(etiquettes, valeurs, strict=True)
    )
    return (
        f'<figure class="graphique"><figcaption id="{ident}-t">{_e(titre)}</figcaption>'
        f'<svg viewBox="0 0 {LARGEUR:.0f} {HAUTEUR:.0f}" role="img" aria-labelledby="{ident}-t {ident}-d" '
        f'preserveAspectRatio="xMidYMid meet"><desc id="{ident}-d">{_e(resume)}</desc>{"".join(morceaux)}</svg>'
        f"<details><summary>Voir les chiffres</summary><table><thead><tr><th scope='col'>Jour</th>"
        f"<th scope='col'>{_e(titre)}</th></tr></thead><tbody>{lignes}</tbody></table></details></figure>"
    )


def jauge(valeur: float | None, maximum: float | None, libelle: str) -> str:
    """La petite barre « crédits du mois sur le plafond » (SVG : aucune feuille de style en ligne)."""
    if valeur is None or not maximum:
        return ""
    part = max(0.0, min(1.0, valeur / maximum))
    classe = "jauge-rouge" if valeur >= maximum else ("jauge-jaune" if part >= 0.8 else "jauge-ok")
    return (
        f'<svg class="jauge" viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label="{_e(libelle)}">'
        f'<rect class="jauge-fond" x="0" y="0" width="100" height="8" rx="4"/>'
        f'<rect class="{classe}" x="0" y="0" width="{part * 100:.1f}" height="8" rx="4"/></svg>'
    )
