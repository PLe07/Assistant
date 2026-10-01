"""Ce qui ne doit jamais être regardé, et ce qui ne doit jamais partir chez Claude."""

import re
import unicodedata


def _simple(texte: str) -> str:
    """Minuscules, sans accents, apostrophes droites : « Crédit Agricole » = « credit agricole »."""
    texte = unicodedata.normalize("NFKD", texte.replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texte.lower()).strip()


def exclue(fenetre: dict, applis: list[str], titres: list[str]) -> str | None:
    """La raison pour laquelle cette fenêtre ne doit pas être capturée, ou None."""
    appli, bundle = _simple(fenetre.get("appli", "")), _simple(fenetre.get("bundle", ""))
    for a in applis:
        a = _simple(a)
        if a and (a == appli or a == bundle or appli.startswith(a)):
            return f"appli exclue ({fenetre.get('appli', '')})"
    titre = _simple(fenetre.get("titre", ""))
    for t in titres:
        t = _simple(t)
        if t and re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", titre):
            return "site ou fenêtre exclus (titre)"
    return None


# Masqués avant tout envoi à Claude : ce sont des données qu'il n'a jamais besoin de voir.
_MASQUES = [
    (re.compile(r"\bsk-ant-[\w-]+"), "[clé masquée]"),
    (re.compile(r"(?i)\b(mot de passe|password|passwd|mdp|token|jeton|secret|api[ _-]?key|clé api)(\s*[:=]\s*)\S+"),
     r"\1\2[masqué]"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b"), "[IBAN masqué]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[e-mail masqué]"),
    (re.compile(r"(?:\+33[\s.-]?|\b0)[1-9](?:[\s.-]?\d{2}){4}\b"), "[téléphone masqué]"),
    (re.compile(r"\b\d(?:[ .-]?\d){8,}\b"), "[numéro masqué]"),  # carte, sécu, n° fiscal, compte…
    (re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b"), "[clé masquée]"),
]


def masquer(texte: str) -> str:
    for motif, remplacement in _MASQUES:
        texte = motif.sub(remplacement, texte)
    return texte


def extrait(fenetre: dict, lignes: list[str], autour: list[int] | None = None, maximum: int = 1500) -> str:
    """Le texte envoyé à Claude : l'appli, le titre, et les lignes utiles (masquées).
    autour : numéros des lignes qui ont déclenché ; on garde 3 lignes de contexte de chaque côté."""
    if autour:
        garder = sorted({j for i in autour for j in range(max(0, i - 3), min(len(lignes), i + 4))})
        choisies = [lignes[j] for j in garder]
    else:
        choisies = lignes
    corps = masquer("\n".join(choisies))[:maximum]
    entete = f"Application : {fenetre.get('appli', '?')}\nFenêtre : {masquer(fenetre.get('titre', ''))[:120]}"
    return f"{entete}\n---\n{corps}"
