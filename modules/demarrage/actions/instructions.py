"""Les instructions à recopier soi-même, pour ce que le Nettoyeur ne fait jamais à ta place : les éléments globaux
(/Library, assistants privilégiés, daemons), les extensions système, la crontab, et la vérification d'un inconnu.

Ce module ne lance RIEN : il fabrique du texte. C'est le seul endroit du Nettoyeur où le mot « sudo » a le droit
d'apparaître (vérifié par tests/demarrage/securite/test_code.py), dans des commandes que tu tapes toi-même, en
connaissance de cause.
"""

from __future__ import annotations

import shlex
import time

REGLAGES_OUVERTURE = "Réglages Système → Général → Ouverture et extensions (« Ouverture » sur les macOS plus anciens)"


def _ligne(*args: str) -> str:
    return shlex.join(args)


def agent_global(label: str, uid: int, chemin_plist: str | None) -> tuple[str, str]:
    """(désactiver, annuler) pour un agent de /Library/LaunchAgents : dans ta session, sans administrateur."""
    cible = f"gui/{uid}/{label}"
    faire = "\n".join([_ligne("launchctl", "disable", cible), _ligne("launchctl", "bootout", cible)])
    defaire = [_ligne("launchctl", "enable", cible)]
    if chemin_plist:
        defaire.append(_ligne("launchctl", "bootstrap", f"gui/{uid}", chemin_plist))
    return faire, "\n".join(defaire)


def daemon(label: str, chemin_plist: str | None) -> tuple[str, str]:
    """(désactiver, annuler) pour un daemon système : droits d'administrateur, à taper toi-même."""
    cible = f"system/{label}"
    faire = "\n".join([_ligne("sudo", "launchctl", "disable", cible), _ligne("sudo", "launchctl", "bootout", cible)])
    defaire = [_ligne("sudo", "launchctl", "enable", cible)]
    if chemin_plist:
        defaire.append(_ligne("sudo", "launchctl", "bootstrap", "system", chemin_plist))
    return faire, "\n".join(defaire)


def assistant_privilegie(chemin: str, lance_par: str | None) -> tuple[str, str]:
    if lance_par:
        return (f"Il est lancé par le daemon « {lance_par} » : c'est lui qu'il faut désactiver (voir sa fiche).", "")
    nom = shlex.quote(chemin.rsplit("/", 1)[-1])
    return (
        "Plus rien ne le lance au démarrage. Pour le retirer (administrateur), il part dans ta corbeille :\n"
        f"sudo mv {shlex.quote(chemin)} ~/.Trash/",
        f"sudo mv ~/.Trash/{nom} {shlex.quote(chemin)}",
    )


def extension(nom: str) -> tuple[str, str]:
    return (
        f"{REGLAGES_OUVERTURE} → « Extensions » : décoche « {nom} ». Ou désinstalle l'app qui l'a installée.",
        f"Même endroit : recoche « {nom} ».",
    )


def ouverture(nom: str) -> tuple[str, str]:
    return (
        f"{REGLAGES_OUVERTURE} → « Ouvrir à la connexion » : sélectionne « {nom} », puis « − ».",
        f"Même endroit : « + », puis choisis l'app « {nom} ».",
    )


def cron(horaire: str) -> tuple[str, str]:
    return (
        f"Tape « crontab -e », puis ajoute un # au début de la ligne qui commence par « {horaire} », et enregistre.",
        "« crontab -e », puis retire le # que tu avais ajouté.",
    )


def verifier(nom: str, editeur: str | None, chemin_plist: str | None, programme: str | None,
             premiere_vue: float | None, raison: str) -> str:  # fmt: skip
    """Pour un élément inconnu : jamais « supprime-le », seulement de quoi le reconnaître."""
    lignes = [
        f"⚠️ À vérifier : {raison}.",
        f"   Éditeur : {editeur or 'inconnu'}",
        f"   Fichier de lancement : {chemin_plist or '—'}",
        f"   Programme : {programme or '—'}",
    ]
    if premiere_vue:
        lignes.append(
            f"   Vu pour la première fois : {time.strftime('%d/%m/%Y à %H:%M', time.localtime(premiere_vue))}"
        )
    if chemin_plist:
        lignes.append(f"   Pour voir son contenu : {_ligne('plutil', '-p', chemin_plist)}")
    if programme:
        lignes.append(f"   Pour voir sa signature : {_ligne('codesign', '-dv', '--verbose=2', programme)}")
    lignes.append("   Si tu ne le reconnais pas, cherche son nom avant d'agir. Ne le supprime pas à l'aveugle.")
    return "\n".join(lignes)
