"""Les unités : tout est rangé en g, ml ou pièces ; l'affichage passe en kg, l pour les grandes quantités.

- `convertir(q, de, vers, poids_piece)` : g ↔ kg, ml ↔ l, pièces ↔ g (avec le poids d'une pièce) ;
- `afficher(q, unite)` : « 1,2 kg », « 500 g », « 75 cl »… pour un humain, à la française ;
- `fraction(q)` : « ½ », « 1 ½ », « ¼ » pour les pièces.
"""

from __future__ import annotations

import math

FACTEURS = {"g": ("g", 1.0), "kg": ("g", 1000.0), "ml": ("ml", 1.0), "cl": ("ml", 10.0), "l": ("ml", 1000.0),
            "p": ("p", 1.0)}  # fmt: skip


class UniteIncompatible(ValueError):
    pass


def base(unite: str) -> tuple[str, float]:
    u = unite.strip().lower()
    if u in ("pièce", "pièces", "piece", "pieces", ""):
        u = "p"
    if u not in FACTEURS:
        raise UniteIncompatible(f"unité inconnue : {unite!r}")
    return FACTEURS[u]


def convertir(quantite: float, de: str, vers: str, poids_piece_g: float | None = None) -> float:
    """Convertit `quantite` de l'unité `de` vers l'unité `vers`. Lève UniteIncompatible (ml ↔ g, pièce sans poids)."""
    b1, f1 = base(de)
    b2, f2 = base(vers)
    q = quantite * f1
    if b1 != b2:
        if {b1, b2} == {"p", "g"} and poids_piece_g:
            q = q * poids_piece_g if b1 == "p" else q / poids_piece_g
        elif {b1, b2} == {"ml", "g"}:
            q = q  # 1 ml ≈ 1 g pour les liquides de cuisine (lait, crème, eau, coulis)
        else:
            raise UniteIncompatible(f"impossible de convertir {de} en {vers}")
    return q / f2


def _nombre(x: float, decimales: int = 1) -> str:
    texte = f"{x:.{decimales}f}"
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte.replace(".", ",")


def fraction(q: float) -> str:
    """0,5 → « ½ », 1,5 → « 1 ½ », 0,25 → « ¼ », 2 → « 2 »."""
    entier = math.floor(q + 1e-9)
    reste = q - entier
    symbole = ""
    for valeur, s in ((0.25, "¼"), (1 / 3, "⅓"), (0.5, "½"), (2 / 3, "⅔"), (0.75, "¾")):
        if abs(reste - valeur) < 0.02:
            symbole = s
            break
    if not symbole and reste > 0.02:
        return _nombre(q, 1)
    if entier == 0:
        return symbole or "0"
    return f"{entier} {symbole}".strip()


def afficher(quantite: float, unite: str) -> str:
    """Pour un humain : 1500 g → « 1,5 kg » ; 750 ml → « 75 cl » ; 2 p → « 2 »."""
    b, f = base(unite)
    q = quantite * f
    if b == "g":
        if q >= 1000:
            return f"{_nombre(q / 1000, 2)} kg"
        return f"{_nombre(round(q), 0) if q >= 10 else _nombre(q, 1)} g"
    if b == "ml":
        if q >= 1000:
            return f"{_nombre(q / 1000, 2)} l"
        if q >= 100 and round(q) % 10 == 0:
            return f"{_nombre(q / 10, 0)} cl"
        return f"{_nombre(round(q), 0) if q >= 10 else _nombre(q, 1)} ml"
    return fraction(q)
