"""Les propositions : un dossier par corvée (README, script), le contrôle des scripts, l'installation sur demande.

Aucun script n'est jamais lancé par le détecteur. « accept ID --installer » installe seulement deux sortes de
solutions, et seulement si le script a passé le contrôle :
- alias_zsh : la ligne est ajoutée à donnees/corvees/alias.zsh (ton ~/.zshrc n'est jamais touché : tu y ajoutes
  toi-même, une fois, « source …/alias.zsh ») ;
- tache_launchd : une tâche « com.assistant.corvee.<id> » dans ~/Library/LaunchAgents, qui lance le script à l'heure
  habituelle ou dès qu'un fichier arrive dans le dossier de départ.
Avant toute modification, une sauvegarde ; « desinstaller ID » défait tout.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from modules.corvees import config
from modules.corvees.descriptions import dossier_reel

INSTALLABLES = ("alias_zsh", "tache_launchd")
AVEC_SCRIPT = ("script_shell", "tache_launchd", "alias_zsh")
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_PERMIS = ("$HOME", "${HOME}", "~", "/dev/null", "/dev/stdout", "/dev/stderr", "/tmp/", "/private/tmp/", "$TMPDIR")

# (motif, explication) : ce qu'un script proposé ne doit jamais faire.
DANGERS = [
    (re.compile(r"\bsudo\b|\bdoas\b"), "demande les droits d'administrateur (sudo)"),
    (re.compile(r"with\s+administrator\s+privileges", re.I), "demande les droits d'administrateur (osascript)"),
    (
        re.compile(r"\b(curl|wget)\b[^\n|;]*\|\s*(sudo\s+)?(ba|z|da|k)?sh\b"),
        "exécute un script téléchargé (curl | sh)",
    ),
    (
        re.compile(r"\b(ba|z|da)?sh\s+(-c\s+)?[\"']?(<\(|\$\()\s*(curl|wget)\b|\beval\s+[\"']?\$\(\s*(curl|wget)"),
        "exécute un script téléchargé",
    ),
    (
        re.compile(
            r"\b(mkfs\w*|diskutil\s+(\w*erase\w*|partition\w*|zero\w*|apfs\s+delete\w*)|csrutil|spctl|nvram|fdesetup)\b"
        ),
        "touche au système",
    ),
    (re.compile(r"\bdd\s+if="), "écrit directement sur un disque (dd)"),
    (re.compile(r"\b(shutdown|reboot|halt)\b"), "éteint ou redémarre le Mac"),
    (re.compile(r"\bsecurity\s+(find|dump|delete|export)"), "lit ou efface le trousseau (mots de passe)"),
    (re.compile(r"/Library/LaunchDaemons|/System/|launchctl\s+\w+\s+system"), "touche aux services du système"),
    (re.compile(r"chmod\s+(-R\s+)?[0-7]?777"), "ouvre des fichiers à tout le monde (chmod 777)"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"), "bloque le Mac (fork bomb)"),
]
_ALIAS = re.compile(r"^alias [A-Za-z0-9_.-]+=")
_FONCTION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\(\) \{ .+; \}$")
_RM = re.compile(r"(?:^|[;&|(\s])rm\s+([^;&|\n]*)", re.M)
_REDIRECTION = re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*[\"']?(/[^\s\"';|&)]*)")
_COMMANDE_ECRIT = re.compile(
    r"(?:^|[;&|(]\s*|\s)(cp|mv|ln|rsync|install|mkdir|touch|chmod|chown|rm)\s+([^;&|\n]*)", re.M
)


# --- le contrôle ------------------------------------------------------------------------------------------------


def _sans_commentaires(script: str) -> str:
    lignes = []
    for ligne in script.splitlines():
        if ligne.lstrip().startswith("#"):
            continue
        lignes.append(re.sub(r"\s#\s.*$", "", ligne))
    return "\n".join(lignes)


def _permis(chemin: str) -> bool:
    return chemin.startswith(_PERMIS) or chemin in ("/tmp", "/dev/null")


def _rm_recursif_force(arguments: str) -> bool:
    options = "".join(a[1:] for a in arguments.split() if a.startswith("-") and not a.startswith("--"))
    longues = arguments.split()
    recursif = "r" in options or "R" in options or "--recursive" in longues
    force = "f" in options or "--force" in longues
    return recursif and force


def dangers(script: str) -> list[str]:
    """Ce que le script fait de risqué (vide : rien de repéré). Ne remplace pas une lecture attentive."""
    texte = _sans_commentaires(script)
    problemes = [explication for motif, explication in DANGERS if motif.search(texte)]
    if any(_rm_recursif_force(m.group(1)) for m in _RM.finditer(texte)):
        problemes.append("efface des dossiers entiers sans confirmation (rm -rf)")
    hors = [m.group(1) for m in _REDIRECTION.finditer(texte) if not _permis(m.group(1))]
    for m in _COMMANDE_ECRIT.finditer(texte):
        arguments = [a.strip("\"'") for a in m.group(2).split() if not a.startswith("-")]
        if not arguments:
            continue
        cibles = arguments[-1:] if m.group(1) in ("cp", "mv", "ln", "rsync", "install") else arguments
        hors += [a for a in cibles if a.startswith("/") and not _permis(a)]
    if hors:
        problemes.append(f"écrit hors de ton dossier personnel ({', '.join(sorted(set(hors))[:3])})")
    return problemes


def _lancer_controle(commande: list[str], script: str) -> str | None:
    """Le message d'erreur du contrôleur (None : rien à redire)."""
    try:
        proc = subprocess.run(commande, input=script, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"{commande[0]} n'a pas pu tourner ({e})"
    if proc.returncode == 0:
        return None
    sortie = (proc.stderr or proc.stdout).strip().splitlines()
    return sortie[0][:200] if sortie else f"code {proc.returncode}"


def verifier(script: str, type_: str, trouver: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    """Contrôle statique : syntaxe (zsh -n, ou bash -n), shellcheck s'il est là, et la liste des dangers."""
    if not script.strip():
        return {"ok": True, "statut": "pas de script", "problemes": [], "controles": []}
    problemes = dangers(script)
    controles = []
    if type_ == "alias_zsh":
        for ligne in _sans_commentaires(script).splitlines():
            ligne = ligne.strip()
            if ligne and not (_ALIAS.match(ligne) or _FONCTION.match(ligne)):
                problemes.append(f"ligne qui n'est ni un alias ni une fonction d'une ligne : {ligne[:60]}")
    coquille = trouver("zsh") or trouver("bash")
    if coquille:
        nom = Path(coquille).name
        controles.append(f"{nom} -n")
        if erreur := _lancer_controle([coquille, "-n"], script):
            problemes.append(f"erreur de syntaxe ({nom} -n) : {erreur}")
    if (shellcheck := trouver("shellcheck")) and type_ != "alias_zsh":
        controles.append("shellcheck")
        if erreur := _lancer_controle([shellcheck, "-s", "bash", "-S", "error", "-"], script):
            problemes.append(f"shellcheck : {erreur}")
    return {
        "ok": not problemes,
        "statut": "✅ contrôlé" if not problemes else "⚠️ à vérifier",
        "problemes": problemes,
        "controles": controles,
    }


# --- les dossiers de propositions -------------------------------------------------------------------------------


def racine(reglages: dict[str, Any]) -> Path:
    return config.dossier_donnees(reglages) / "propositions"


def _ecrire(chemin: Path, contenu: str, mode: int = 0o600) -> None:
    chemin.write_text(contenu, encoding="utf-8")
    os.chmod(chemin, mode)


def nom_script(type_: str) -> str:
    return "alias.zsh" if type_ == "alias_zsh" else "script.sh"


def readme(c: dict[str, Any], d: dict[str, Any], verification: dict[str, Any]) -> str:
    s = d["solution"]
    lignes = [
        f"# {d['titre_court']}",
        "",
        d["description_fr"],
        "",
        f"**Pourquoi c'est une corvée :** {d['pourquoi_corvee']}",
        "",
        f"**Gain estimé :** {d['gain_minutes_mois']:.0f} min par mois · difficulté : {d['difficulte']}"
        f" · confiance : {round(float(d['confiance']) * 100)} %"
        f" · décrite par : {'Claude' if d.get('source') == 'claude' else 'le détecteur (sans Claude)'}",
        "",
        f"## La solution ({s['type']})",
        "",
        s["explication"],
        "",
    ]
    if s["installation_pas_a_pas"]:
        lignes += ["## Pas à pas", ""] + [f"{i}. {p}" for i, p in enumerate(s["installation_pas_a_pas"], 1)] + [""]
    if s["script"].strip():
        lignes += [
            f"## Le script ({nom_script(s['type'])}) : {verification['statut']}",
            "",
            "Il n'est jamais lancé tout seul.",
        ]
        if verification["problemes"]:
            lignes += ["", "À vérifier avant toute chose :"] + [f"- {p}" for p in verification["problemes"]]
        lignes += ["", "```zsh", s["script"].rstrip(), "```", ""]
    lignes += [f"**Risques :** {s['risques']}", "", f"Identifiant : {c['id']}", ""]
    return "\n".join(lignes)


def ecrire(reglages: dict[str, Any], c: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    """Écrit (ou réécrit) le dossier de la proposition ; renvoie le résultat du contrôle du script."""
    dossier = racine(reglages) / c["id"]
    dossier.mkdir(parents=True, exist_ok=True)
    os.chmod(dossier, 0o700)
    s = d["solution"]
    script = s["script"]
    if script.strip() and s["type"] != "alias_zsh" and not script.startswith("#!"):
        script = "#!/bin/zsh\n" + script
    verification = verifier(script, s["type"])
    for ancien in ("script.sh", "alias.zsh"):
        (dossier / ancien).unlink(missing_ok=True)
    if script.strip():
        _ecrire(dossier / nom_script(s["type"]), script if script.endswith("\n") else script + "\n", 0o700)
    _ecrire(dossier / "README.md", readme(c, d, verification))
    _ecrire(
        dossier / "proposition.json",
        json.dumps({"candidat": c, "description": d, "verification": verification}, ensure_ascii=False, indent=1),
    )
    return verification


def lire(reglages: dict[str, Any], id_: str) -> dict[str, Any] | None:
    chemin = racine(reglages) / id_.lower() / "proposition.json"
    if not chemin.exists():
        return None
    resultat: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    return resultat


# --- l'installation (sur ta demande seulement) -------------------------------------------------------------------


class Refus(Exception):
    """L'installation n'a pas eu lieu : le message dit pourquoi et quoi faire."""


def _registre(reglages: dict[str, Any]) -> Path:
    return config.dossier_donnees(reglages) / "installations.json"


def installations(reglages: dict[str, Any]) -> dict[str, dict[str, Any]]:
    chemin = _registre(reglages)
    if not chemin.exists():
        return {}
    resultat: dict[str, dict[str, Any]] = json.loads(chemin.read_text(encoding="utf-8"))
    return resultat


def _noter(reglages: dict[str, Any], registre: dict[str, dict[str, Any]]) -> None:
    chemin = _registre(reglages)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    _ecrire(chemin, json.dumps(registre, ensure_ascii=False, indent=1))


def _sauvegarder(reglages: dict[str, Any], fichier: Path) -> str | None:
    if not fichier.exists():
        return None
    dossier = config.dossier_donnees(reglages) / "sauvegardes"
    dossier.mkdir(parents=True, exist_ok=True)
    copie = dossier / f"{fichier.name}.{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(fichier, copie)
    os.chmod(copie, 0o600)
    return str(copie)


def fichier_alias(reglages: dict[str, Any]) -> Path:
    return config.dossier_donnees(reglages) / "alias.zsh"


def declencheur(c: dict[str, Any]) -> dict[str, Any] | None:
    """Quand lancer la tâche : à l'heure habituelle, sinon dès qu'un fichier arrive dans le dossier de départ."""
    details = c.get("details") or {}
    if creneau := details.get("creneau"):
        heure, minute = (int(x) for x in creneau.split(":"))
        moment: dict[str, Any] = {"Hour": heure, "Minute": minute}
        if details.get("jour_semaine") in JOURS:
            moment["Weekday"] = JOURS.index(details["jour_semaine"]) + 1  # launchd : 1 = lundi, 7 = dimanche
        return {"StartCalendarInterval": moment}
    for t in c["tokens"]:
        sorte, _, reste = t.partition(":")
        if sorte in ("fmove", "fren", "fconv", "fcreate"):
            lieu = re.split(r"→| \[", reste, maxsplit=1)[0]
            if dossier_reel(lieu) is None or lieu.startswith("/"):
                return None
            return {"WatchPaths": [str(Path.home() / lieu) if lieu != "~" else str(Path.home())]}
    return None


def installer(
    reglages: dict[str, Any],
    id_: str,
    lancer: Callable[..., Any] = subprocess.run,
    uid: int | None = None,
) -> str:
    """Installe la solution d'une proposition. Lève Refus avec un message clair si ce n'est pas possible."""
    prop = lire(reglages, id_)
    if prop is None:
        raise Refus(f"Aucune proposition « {id_} » (python corvees.py rapport pour la liste).")
    c, d, verification = prop["candidat"], prop["description"], prop["verification"]
    type_ = d["solution"]["type"]
    if c["id"] in installations(reglages):
        raise Refus(f"« {d['titre_court']} » est déjà installée (python corvees.py desinstaller {c['id']}).")
    if type_ not in INSTALLABLES:
        raise Refus(f"Cette solution ({type_}) s'installe à la main : suis le pas à pas du README.")
    if not d["solution"]["script"].strip():
        raise Refus("Cette proposition n'a pas de script à installer : suis le pas à pas du README.")
    if not verification["ok"]:
        raise Refus("Script ⚠️ à vérifier, pas d'installation automatique : " + " ; ".join(verification["problemes"]))
    registre = installations(reglages)
    if type_ == "alias_zsh":
        entree = _installer_alias(reglages, c, d)
    else:
        entree = _installer_tache(reglages, c, d, lancer, os.getuid() if uid is None else uid)
    registre[c["id"]] = {**entree, "type": type_, "titre": d["titre_court"], "quand": time.time()}
    _noter(reglages, registre)
    return entree["message"]


def _installer_alias(reglages: dict[str, Any], c: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    fichier = fichier_alias(reglages)
    sauvegarde = _sauvegarder(reglages, fichier)
    ancien = fichier.read_text(encoding="utf-8") if fichier.exists() else "# Alias proposés par le détecteur.\n"
    bloc = f"# corvée {c['id']} : {d['titre_court']}\n{d['solution']['script'].strip()}\n# fin corvée {c['id']}\n"
    _ecrire(fichier, ancien.rstrip("\n") + "\n" + bloc)
    message = (
        f"Alias installé dans {fichier}.\nSi ce n'est pas déjà fait, ajoute une fois cette ligne à ton ~/.zshrc"
        f" (le détecteur n'y touche jamais) :\n  source '{fichier}'"
    )
    return {"fichiers": [str(fichier)], "sauvegardes": [s for s in [sauvegarde] if s], "message": message}


def _installer_tache(
    reglages: dict[str, Any], c: dict[str, Any], d: dict[str, Any], lancer: Callable[..., Any], uid: int
) -> dict[str, Any]:
    quand = declencheur(c)
    if quand is None:
        raise Refus("Pas de moment évident pour lancer cette tâche : suis le pas à pas du README.")
    i = reglages["installation"]
    etiquette = f"{i['prefixe']}.{c['id']}"
    dossier_taches = Path(i["launchagents"]).expanduser()
    dossier_taches.mkdir(parents=True, exist_ok=True)
    plist = dossier_taches / f"{etiquette}.plist"
    proposition = racine(reglages) / c["id"]
    contenu = {
        "Label": etiquette,
        "ProgramArguments": ["/bin/zsh", str(proposition / "script.sh")],
        "StandardOutPath": str(proposition / "journal.txt"),
        "StandardErrorPath": str(proposition / "journal.txt"),
        **quand,
    }
    sauvegarde = _sauvegarder(reglages, plist)
    with open(plist, "wb") as f:
        plistlib.dump(contenu, f)
    os.chmod(plist, 0o644)  # launchd refuse un fichier modifiable par d'autres
    proc = lancer(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], capture_output=True, text=True)
    if proc.returncode != 0:
        plist.unlink(missing_ok=True)
        if sauvegarde:
            shutil.copy2(sauvegarde, plist)
        raise Refus(f"launchctl a refusé la tâche : {(proc.stderr or proc.stdout).strip()[:200]}")
    if "WatchPaths" in quand:
        moment = f"dès qu'un fichier arrive dans {quand['WatchPaths'][0]}"
    else:
        moment = "à {Hour:02d}:{Minute:02d}".format(**quand["StartCalendarInterval"])
    return {
        "fichiers": [str(plist)],
        "sauvegardes": [s for s in [sauvegarde] if s],
        "etiquette": etiquette,
        "message": f"Tâche installée ({etiquette}) : elle se lancera {moment}.",
    }


def desinstaller(
    reglages: dict[str, Any], id_: str, lancer: Callable[..., Any] = subprocess.run, uid: int | None = None
) -> str:
    """Défait une installation : la tâche est arrêtée et son fichier retiré, ou le bloc d'alias enlevé."""
    registre = installations(reglages)
    entree = registre.get(id_.lower())
    if entree is None:
        raise Refus(f"Rien d'installé sous « {id_} ».")
    if entree["type"] == "tache_launchd":
        uid = os.getuid() if uid is None else uid
        try:  # déjà arrêtée, ou launchctl absent : on retire quand même le fichier
            lancer(["launchctl", "bootout", f"gui/{uid}/{entree['etiquette']}"], capture_output=True, text=True)
        except OSError:
            pass
        for fichier in entree["fichiers"]:
            Path(fichier).unlink(missing_ok=True)
        message = f"Tâche {entree['etiquette']} arrêtée et retirée."
    else:
        fichier = fichier_alias(reglages)
        if fichier.exists():
            _sauvegarder(reglages, fichier)
            texte = fichier.read_text(encoding="utf-8")
            motif = re.compile(rf"# corvée {re.escape(id_.lower())} :.*?# fin corvée {re.escape(id_.lower())}\n", re.S)
            _ecrire(fichier, motif.sub("", texte))
        message = "Alias retiré (ouvre un nouveau terminal pour que ce soit pris en compte)."
    del registre[id_.lower()]
    _noter(reglages, registre)
    return message
