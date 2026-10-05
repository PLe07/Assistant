"""Les descriptions faites sur place, sans Claude (budget atteint, Claude indisponible, ou Claude coupé).

Plus simples que celles de Claude, mais utiles : une phrase en français, et pour les corvées de fichiers, de
commandes et d'ouvertures d'applis, un vrai script prêt à vérifier. Les scripts n'utilisent que des commandes de
base de macOS (mv, sips, open), restent dans ton dossier personnel et passent les mêmes contrôles que ceux de Claude.
"""

from __future__ import annotations

import re
from typing import Any

_FMOVE = re.compile(r"^fmove:(?P<de>[^→]+)→(?P<vers>.+?) \[(?P<ext>[^,\]]*), (?P<motif>.*)\]$")
_FREN = re.compile(r"^fren:(?P<dossier>.+?) \[(?P<ext>[^,\]]*), (?P<avant>.*?)→(?P<apres>.*)\]$")
_FCONV = re.compile(r"^fconv:(?P<dossier>.+?) \[(?P<de>[^→\]]*)→(?P<vers>[^,\]]*), (?P<motif>.*)\]$")
_FICHIER = re.compile(r"^(?P<kind>fdel|fcreate):(?P<dossier>.+?) \[(?P<ext>[^,\]]*), (?P<motif>.*)\]$")
_VARIABLE = re.compile(r"'\*'|\"\*\"")  # un texte entre guillemets, remplacé par « * » à la normalisation
_SIPS = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "heic": "heic", "tif": "tiff", "tiff": "tiff", "gif": "gif"}


def _sorte(token: str) -> str:
    return token.split(":", 1)[0]


def _nom(motif: str, ext: str) -> str:
    return f"{motif}.{ext}" if ext else motif


def etape(token: str) -> str:
    """Une étape en français : « fmove:Downloads→Documents [pdf, Facture_*] » → « ranger … »."""
    sorte, _, reste = token.partition(":")
    if sorte == "app":
        return f"ouvrir {reste}"
    if sorte == "url":
        return f"aller sur {reste}"
    if sorte == "fen":
        appli, _, titre = reste.partition(":")
        return f"passer à la fenêtre « {titre} » de {appli}"
    if sorte == "clip":
        de, _, vers = reste.partition("→")
        return f"copier dans {de} pour coller dans {vers}"
    if sorte == "cmd":
        return f"taper « {reste} » dans le terminal"
    if m := _FMOVE.match(token):
        fichiers = _nom(m["motif"], m["ext"])
        return f"déplacer les fichiers « {fichiers} » de {_lisible(m['de'])} vers {_lisible(m['vers'])}"
    if m := _FREN.match(token):
        return (
            f"renommer « {_nom(m['avant'], m['ext'])} » en « {_nom(m['apres'], m['ext'])} » "
            f"dans {_lisible(m['dossier'])}"
        )
    if m := _FCONV.match(token):
        return f"convertir les fichiers .{m['de']} en .{m['vers']} dans {_lisible(m['dossier'])}"
    if m := _FICHIER.match(token):
        verbe = "supprimer" if m["kind"] == "fdel" else "recevoir"
        return f"{verbe} les fichiers « {_nom(m['motif'], m['ext'])} » dans {_lisible(m['dossier'])}"
    return token


def _lisible(lieu: str) -> str:
    return "ton dossier personnel" if lieu == "~" else (lieu if lieu.startswith("/") else f"~/{lieu}")


def quand(c: dict[str, Any]) -> str:
    d = c.get("details") or {}
    texte = f"environ {round(c['frequence_mois'])} fois par mois"
    if d.get("jour_semaine"):
        texte += f", le {d['jour_semaine']}"
    if d.get("creneau"):
        texte += f" vers {d['creneau']}"
    return texte


# --- les scripts -------------------------------------------------------------------------------------------------


def _q(texte: str) -> str:
    """Entre apostrophes pour zsh, même s'il y en a dedans."""
    return "'" + texte.replace("'", "'\\''") + "'"


def _motif_shell(motif: str, ext: str) -> str:
    """« Facture_* » + pdf → 'Facture_'*'.pdf' : les parties fixes entre apostrophes, les « * » libres."""
    parties = [_q(p) if p else "" for p in motif.split("*")]
    return "*".join(parties) + (_q(f".{ext}") if ext else "")


def dossier_reel(lieu: str) -> str | None:
    """« Documents/Factures » → « $HOME/Documents/Factures » ; None si le dossier exact n'est pas connu."""
    if "*" in lieu or "[" in lieu:
        return None
    if lieu == "~":
        return "$HOME"
    if lieu.startswith("/"):
        return _q(lieu)
    return '"$HOME"/' + _q(lieu)


def _entete(titre: str) -> list[str]:
    return [
        "#!/bin/zsh",
        f"# {titre}",
        "# Proposé par le détecteur de corvées : lis-le avant de l'installer.",
        "setopt null_glob 2>/dev/null || true  # aucun fichier : la boucle ne fait rien",
        "",
    ]


def script_rangement(tokens: list[str]) -> str | None:
    """Un renommage (facultatif) puis un déplacement, d'après les étapes ; None si ce n'est pas faisable sûrement."""
    renommage = next((m for t in tokens if (m := _FREN.match(t))), None)
    deplacement = next((m for t in tokens if (m := _FMOVE.match(t))), None)
    if deplacement is None:
        return None
    de, vers = dossier_reel(deplacement["de"]), dossier_reel(deplacement["vers"])
    if de is None or vers is None:
        return None
    lignes = _entete(f"Range les fichiers « {_nom(deplacement['motif'], deplacement['ext'])} ».")
    lignes += [f"de={de}", f"vers={vers}", 'mkdir -p "$vers"']
    if renommage is not None:
        avant, apres = renommage["avant"], renommage["apres"]
        if avant.count("*") != 1 or apres.count("*") != 1 or dossier_reel(renommage["dossier"]) != de:
            return None
        a1, a2 = avant.split("*")
        b1, b2 = apres.split("*")
        ext = renommage["ext"]
        point = f".{ext}" if ext else ""
        lignes += [
            f"a1={_q(a1)}; a2={_q(a2)}; b1={_q(b1)}; b2={_q(b2)}; point={_q(point)}",
            f'for f in "$de"/{_motif_shell(avant, ext)}; do',
            '  [ -e "$f" ] || continue',
            '  nom="${f##*/}"; nom="${nom%"$point"}"',
            '  milieu="${nom#"$a1"}"; milieu="${milieu%"$a2"}"',
            '  nouveau="$de/$b1$milieu$b2$point"',
            '  [ -e "$nouveau" ] || mv -n "$f" "$nouveau"',
            "done",
        ]
    lignes += [
        f'for f in "$de"/{_motif_shell(deplacement["motif"], deplacement["ext"])}; do',
        '  [ -e "$f" ] || continue',
        '  [ -e "$vers/${f##*/}" ] || mv -n "$f" "$vers/"',
        "done",
    ]
    return "\n".join(lignes) + "\n"


def script_conversion(token: str) -> str | None:
    m = _FCONV.match(token)
    if m is None or m["vers"] not in _SIPS or m["de"] not in _SIPS:
        return None
    dossier = dossier_reel(m["dossier"])
    if dossier is None:
        return None
    lignes = _entete(f"Convertit les fichiers .{m['de']} en .{m['vers']} (l'original est gardé).")
    lignes += [
        f"dossier={dossier}",
        f'for f in "$dossier"/{_motif_shell(m["motif"], m["de"])}; do',
        '  [ -e "$f" ] || continue',
        f'  sortie="${{f%.*}}.{m["vers"]}"',
        f'  [ -e "$sortie" ] || sips -s format {_SIPS[m["vers"]]} "$f" --out "$sortie" >/dev/null',
        "done",
    ]
    return "\n".join(lignes) + "\n"


def script_ouverture(tokens: list[str], titre: str) -> str | None:
    lignes = []
    for t in tokens:
        sorte, _, reste = t.partition(":")
        if sorte == "app":
            lignes.append(f"open -a {_q(reste)}")
        elif sorte == "url" and "[" not in reste and "*" not in reste:
            lignes.append(f"open {_q('https://' + reste)}")
    if not lignes:
        return None
    return "\n".join(_entete(titre) + lignes) + "\n"


def alias(commandes: list[str], id_: str) -> str | None:
    """Un alias pour une ligne fixe ; une fonction si seuls des textes entre guillemets changent
    (« git commit -m '*' » → corvee_x "mon message")."""
    ligne = " && ".join(commandes)
    if "[" in ligne or "\n" in ligne:
        return None
    if "*" not in ligne:
        return f"alias corvee_{id_}={_q(ligne)}\n"
    variables = _VARIABLE.findall(ligne)
    if ligne.count("*") != len(variables):
        return None  # une partie variable hors guillemets : on ne devine pas
    n = 0

    def argument(_: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return f'"${n}"'

    corps = _VARIABLE.sub(argument, ligne)
    return f"corvee_{id_}() {{ {corps}; }}\n"


def titre(c: dict[str, Any]) -> str:
    """Un titre court (60 caractères au plus, coupé entre deux mots)."""
    tokens = c["tokens"]
    premier = tokens[0]
    sorte, _, reste = premier.partition(":")
    details = c.get("details") or {}
    if m := _FMOVE.match(premier):
        t = f"Ranger les « {_nom(m['motif'], m['ext'])} » dans {_lisible(m['vers'])}"
    elif m := _FREN.match(premier):
        t = f"Renommer les « {_nom(m['avant'], m['ext'])} »"
    elif m := _FCONV.match(premier):
        t = f"Convertir les .{m['de']} en .{m['vers']}"
    elif sorte == "cmd":
        t = f"Commande « {' && '.join(x[4:] for x in tokens if x.startswith('cmd:'))} »"
    elif sorte == "clip":
        de, _, vers = reste.partition("→")
        t = f"Copier de {de} vers {vers}"
    elif sorte in ("app", "url"):
        noms = [t.partition(":")[2] for t in tokens if t.startswith(("app:", "url:"))]
        t = "Ouvrir " + ", ".join(noms[:3]) + ("…" if len(noms) > 3 else "")
        if details.get("creneau"):
            t = f"{t} à {details['creneau']}"
    else:
        t = etape(premier)[:1].upper() + etape(premier)[1:]
    if len(t) <= 60:
        return t
    return t[:59].rsplit(" ", 1)[0] + "…"


# --- la description complète -------------------------------------------------------------------------------------


def locale(c: dict[str, Any]) -> dict[str, Any]:
    """Une description au même format que celle de Claude."""
    tokens: list[str] = list(c["tokens"])
    sortes = {_sorte(t) for t in tokens}
    details = c.get("details") or {}
    etapes = [etape(t) for t in tokens]
    court = titre(c)
    script: str | None = None
    type_, explication, pas, risques = "autre", "", [], "Aucun : rien n'est fait sans toi."

    if sortes & {"fmove", "fren"} and (script := script_rangement(tokens)):
        type_ = "tache_launchd"
        explication = "Une petite tâche range les fichiers dès qu'ils arrivent dans le dossier de départ."
        pas = ["Lis le script ci-dessous.", f"Installe-le : python corvees.py accept {c['id']} --installer"]
        risques = "Un fichier du même nom déjà rangé n'est jamais écrasé (il reste où il est)."
        if ".Trash" in script:
            risques = "Les fichiers vont à la Corbeille : récupérables tant que tu ne l'as pas vidée."
    elif "fconv" in sortes and (script := script_conversion(next(t for t in tokens if t.startswith("fconv:")))):
        type_ = "tache_launchd"
        explication = "Une petite tâche convertit les nouveaux fichiers avec « sips », l'outil d'images de macOS."
        pas = ["Lis le script ci-dessous.", f"Installe-le : python corvees.py accept {c['id']} --installer"]
        risques = "L'original est gardé ; une conversion déjà faite n'est jamais refaite."
    elif sortes == {"cmd"} and (script := alias([t[4:] for t in tokens], c["id"])):
        type_ = "alias_zsh"
        explication = "Un raccourci de terminal : un seul mot pour toute la suite de commandes."
        if "()" in script:
            explication += " Ce qui change à chaque fois (entre guillemets) se donne après le mot."
        pas = [
            f"Installe-le : python corvees.py accept {c['id']} --installer",
            "Ouvre un nouveau terminal, puis tape corvee_" + c["id"] + " (tu peux le renommer dans alias.zsh).",
        ]
    elif sortes <= {"app", "url", "fen", "copie"} and (script := script_ouverture(tokens, court)):
        if details.get("creneau"):
            type_ = "tache_launchd"
            jour = details.get("jour_semaine") or "jour"
            explication = f"Une tâche ouvre tout ça pour toi, chaque {jour} à {details['creneau']}."
            pas = ["Lis le script ci-dessous.", f"Installe-le : python corvees.py accept {c['id']} --installer"]
        else:
            type_ = "app_raccourcis"
            explication = (
                "Crée un raccourci dans l'app Raccourcis avec une action « Ouvrir l'app » ou « Ouvrir les URL » "
                "par étape ; le script ci-dessous fait la même chose depuis le terminal."
            )
            pas = ["Ouvre l'app Raccourcis, puis « + ».", "Ajoute une action par étape.", "Donne-lui un nom court."]
    elif sortes & {"fmove", "fren", "fconv"}:
        type_ = "regle_dossier"
        explication = (
            "Une règle de dossier (Hazel, ou une action de dossier du Finder) peut faire ces étapes dès qu'un "
            "fichier arrive ; les noms varient trop pour un script sûr fait sans Claude."
        )
    elif "clip" in sortes:
        explication = (
            "Si c'est toujours le même genre d'information, un raccourci (app Raccourcis) peut la reprendre "
            "et l'ajouter à l'autre appli ; sinon, un historique du presse-papiers t'évite les allers-retours."
        )
    elif "fdel" in sortes:
        type_ = "regle_dossier"
        explication = "Une règle de dossier (Hazel, ou une action de dossier du Finder) peut faire le ménage pour toi."
        risques = "Une suppression automatique est risquée : préfère la Corbeille, et vérifie le motif."
    else:
        explication = "Pas de solution toute faite : regarde si l'app Raccourcis peut enchaîner ces étapes."

    return {
        "id": c["id"],
        "titre_court": court,
        "description_fr": f"Tu fais ceci {quand(c)} : {', puis '.join(etapes)}."[:600],
        "pourquoi_corvee": (
            f"{c['occurrences']} fois sur {c['jours_distincts']} jours, toujours les mêmes étapes : "
            f"environ {c['minutes_mois']:.0f} min par mois."
        ),
        "solution": {
            "type": type_,
            "explication": explication,
            "script": script or "",
            "installation_pas_a_pas": pas,
            "risques": risques,
        },
        "gain_minutes_mois": round(float(c["minutes_mois"]) * (0.9 if script else 0.5), 1),
        "difficulte": "facile" if type_ in ("tache_launchd", "alias_zsh") else "moyen",
        "confiance": 0.6 if script else 0.3,
    }
