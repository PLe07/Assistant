"""Fichiers et dossiers : ouvrir un dossier ou un alias, le dernier PDF, le dernier téléchargement, la dernière capture,
chercher avec Spotlight (résultats numérotés dans la bulle), puis « ouvre le 2 » ou « montre le 2 dans le Finder ».

Tout passe par `open` avec un chemin vérifié (dans ta maison, jamais un fichier qui s'exécute) ; la recherche passe
par `mdfind` (le texte cherché est un argument, jamais une commande).
"""

from __future__ import annotations

import re
from pathlib import Path

from voix.actions import apps, web
from voix.actions.base import CheminRefuse, Etat, Outils, Reponse, chemin_ouvrable, erreur, fait, info
from voix.nlu.catalogue import Objet

RESULTATS_MAX = 9
INCOMPLETS = (".crdownload", ".download", ".part", ".partial", ".tmp")
CAPTURE = re.compile(r"^(?:capture d.écran|screenshot|capture|enregistrement de l.écran)", re.IGNORECASE)
CACHES = ("/Library/", "/.Trash/", "/.", "/node_modules/")


def ouvrir_chemin(o: Outils, brut: str, nom: str, intention: str, dossier: bool | None = None) -> Reponse:
    try:
        chemin = chemin_ouvrable(brut, o.chemins.maison, dossier=dossier)
    except CheminRefuse as e:
        return erreur(f"Je n'ouvre pas {nom} : {e}.", intention)
    r = o.lancer("open", chemin)
    if not r.ok:
        return erreur(f"{nom} n'a pas pu s'ouvrir.", intention)
    return fait(f"{nom} ouvert", intention, chemin=chemin)


def ouvrir_dossier(o: Outils, objet: Objet) -> Reponse:
    return ouvrir_chemin(o, objet.cible, objet.nom, "dossier.ouvrir", dossier=True)


def ouvrir_alias(o: Outils, objet: Objet) -> Reponse:
    cible = objet.cible
    if cible.startswith("https://"):
        return web.ouvrir_adresse(o, cible, objet.nom, "alias.ouvrir")
    if cible.startswith("app:"):
        app = next((a for a in o.catalogue.du_genre("app") if a.nom.lower() == cible[4:].lower()), None)
        if app is None:
            return erreur(f"L'app de l'alias « {objet.nom} » est introuvable.", "alias.ouvrir")
        return apps.ouvrir(o, app)
    return ouvrir_chemin(o, cible, objet.nom, "alias.ouvrir")


def _fichiers(dossiers: list[Path], garder: re.Pattern[str] | None = None, extension: str | None = None) -> list[Path]:
    trouves: list[Path] = []
    for d in dossiers:
        try:
            for f in d.iterdir():
                if f.name.startswith(".") or f.name.endswith(INCOMPLETS) or not f.is_file():
                    continue
                if extension is not None and f.suffix.lower() != extension:
                    continue
                if garder is not None and not garder.match(f.name):
                    continue
                trouves.append(f)
        except OSError:
            continue

    def date(f: Path) -> float:
        try:
            return f.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(trouves, key=date, reverse=True)


def _dossier_captures(o: Outils) -> Path:
    r = o.lancer("defaults", "read", "com.apple.screencapture", "location")
    if r.ok and r.sortie.strip():
        brut = r.sortie.strip().replace("~", str(o.chemins.maison), 1)
        p = Path(brut)
        if p.is_absolute() and p.is_dir():
            return p
    return o.chemins.maison / "Desktop"


def dernier(o: Outils, intention: str) -> Reponse:
    m = o.chemins.maison
    if intention == "fichier.dernier_pdf":
        candidats = _fichiers([m / "Downloads", m / "Desktop", m / "Documents"], extension=".pdf")
        nom = "le dernier PDF"
    elif intention == "fichier.dernier_telecharge":
        candidats = _fichiers([m / "Downloads"])
        nom = "le dernier téléchargement"
    else:
        candidats = _fichiers([_dossier_captures(o)], garder=CAPTURE)
        nom = "la dernière capture"
    for f in candidats[:5]:  # le plus récent qu'on a le droit d'ouvrir
        try:
            chemin_ouvrable(str(f), m, dossier=False)
        except CheminRefuse:
            continue
        r = ouvrir_chemin(o, str(f), f.name, intention, dossier=False)
        return r
    return info(f"Je n'ai pas trouvé {nom}.", intention)


def chercher(o: Outils, etat: Etat, requete: str) -> Reponse:
    maison = str(o.chemins.maison)
    requete = requete.strip().lstrip("-").strip()  # jamais lu comme une option
    if not requete:
        return info("Que dois-je chercher ?", "fichier.chercher")
    r = o.lancer("mdfind", "-onlyin", maison, "-name", requete, delai_s=8)
    if not r.ok:
        return erreur("La recherche Spotlight n'a pas répondu.", "fichier.chercher")
    resultats: list[str] = []
    for ligne in r.sortie.splitlines():
        ligne = ligne.strip()
        if not ligne.startswith(maison) or any(c in ligne[len(maison) :] for c in CACHES):
            continue
        resultats.append(ligne)
        if len(resultats) == RESULTATS_MAX:
            break
    etat.resultats = resultats
    if not resultats:
        return info(f"Aucun fichier « {requete} ».", "fichier.chercher")
    liste = " ; ".join(f"{i}. {Path(p).name}" for i, p in enumerate(resultats, 1))
    return info(f"{len(resultats)} résultat{'s' if len(resultats) > 1 else ''} : {liste}", "fichier.chercher",
                resultats=[Path(p).name for p in resultats])  # fmt: skip


def resultat(o: Outils, etat: Etat, rang: int, reveler: bool) -> Reponse:
    intention = "fichier.reveler_resultat" if reveler else "fichier.ouvrir_resultat"
    if not etat.resultats:
        return info("Il n'y a pas de résultats à ouvrir : dis d'abord « cherche … ».", intention)
    index = len(etat.resultats) - 1 if rang == -1 else rang - 1
    if not 0 <= index < len(etat.resultats):
        return info(f"Il n'y a que {len(etat.resultats)} résultat(s).", intention)
    brut = etat.resultats[index]
    nom = Path(brut).name
    if not reveler:
        return ouvrir_chemin(o, brut, nom, intention)
    try:
        chemin = chemin_ouvrable(brut, o.chemins.maison)
    except CheminRefuse as e:
        return erreur(f"Je ne montre pas {nom} : {e}.", intention)
    r = o.lancer("open", "-R", chemin)
    return fait(f"{nom} dans le Finder", intention) if r.ok else erreur("Le Finder n'a pas répondu.", intention)
