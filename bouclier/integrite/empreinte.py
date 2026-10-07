"""Empreinte des projets existants : capturer « avant », comparer ensuite.

Lecture seule, bibliothèque standard uniquement (tourne avant même l'environnement Python de Bouclier).

Ce qui est relevé :
- le dépôt qui contient Bouclier (l'assistant, avec Corvées, Nettoyeur, Trieur…), **hors** du dossier de Bouclier :
  l'arbre suivi par git, l'état `git status` et le SHA-256 de chaque fichier de code ou de réglages ;
- les autres projets de `~/Projets/*` (HEAD, état, SHA-256 de chaque fichier) ;
- sur le Mac : les LaunchAgents (plist + état launchd), les réglages dans `~/Library/Application Support/<Projet>/`,
  `~/.zshrc`, `~/.zprofile`, `crontab -l`, la liste du dossier iCloud `BoiteMac/` (empreinte seulement) et
  `shortcuts list` (empreinte seulement).

Usage :
    python3 empreinte.py capturer <fichier.json>
    python3 empreinte.py comparer <fichier.json>     (code 0 si identique, 1 sinon)
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE_BOUCLIER = ICI.parent
MAISON = Path.home()

# Données vivantes que les projets écrivent eux-mêmes en tournant (base, journal, caches d'outils) :
# elles changent sans nous, on ne les compare pas. Le code et les réglages, eux, doivent rester identiques.
DOSSIERS_VIVANTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "donnees",
    "logs",
    "node_modules",
    ".cache-ocr",
    ".cache-corpus",
}
FICHIERS_VIVANTS = re.compile(
    r"(\.db|\.db-journal|\.db-wal|\.db-shm|\.log|\.pyc|^\.coverage.*|^PAUSE|^\.verrou|^\.DS_Store)$"
)

# Les nôtres : jamais comparés (ils sont créés par l'installation de Bouclier).
NOTRE_LABEL = re.compile(r"^com\.[^.]+\.bouclier$")
NOS_DOSSIERS_SUPPORT = {"Bouclier"}

ICLOUD = MAISON / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
PROJETS_SUPPORT = ("Corvees", "Corvées", "Nettoyeur", "Trieur", "Ambiance", "Assistant", "Demarrage")
EXTENSIONS_REGLAGES = {".json", ".toml", ".plist", ".yaml", ".yml", ".ini", ".conf", ".cfg", ".txt"}


def sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def sha256_texte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8", "surrogateescape")).hexdigest()


def _commande(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, f"indisponible : {e.__class__.__name__}"
    return proc.returncode, proc.stdout


def _est_vivant(rel: Path) -> bool:
    if any(part in DOSSIERS_VIVANTS for part in rel.parts[:-1]):
        return True
    return bool(FICHIERS_VIVANTS.search(rel.name))


def fichiers_du_projet(racine: Path, exclure: Path | None) -> dict[str, str]:
    """SHA-256 de chaque fichier (code et réglages), hors .git, hors données vivantes, hors Bouclier."""
    resultat: dict[str, str] = {}
    for dossier, sous_dossiers, fichiers in os.walk(racine):
        d = Path(dossier)
        if exclure is not None and (d == exclure or exclure in d.parents):
            sous_dossiers[:] = []
            continue
        sous_dossiers[:] = sorted(
            s for s in sous_dossiers if s not in DOSSIERS_VIVANTS and not (exclure is not None and d / s == exclure)
        )
        for nom in sorted(fichiers):
            chemin = d / nom
            rel = chemin.relative_to(racine)
            if _est_vivant(rel) or chemin.is_symlink():
                continue
            try:
                resultat[rel.as_posix()] = sha256_fichier(chemin)
            except OSError as e:
                resultat[rel.as_posix()] = f"illisible : {e.__class__.__name__}"
    return resultat


def etat_git(racine: Path, exclure: Path | None) -> dict[str, str]:
    """Arbre suivi et état de la copie de travail, hors Bouclier.

    `--no-optional-locks` : `git status` ne réécrit pas l'index du projet (aucune écriture chez lui)."""
    contient_bouclier = exclure is not None and racine in exclure.parents
    prefixe = exclure.relative_to(racine).as_posix() + "/" if contient_bouclier and exclure is not None else None

    def hors_bouclier(lignes: str, chemin_de) -> str:
        if prefixe is None:
            return lignes
        return "\n".join(ligne for ligne in lignes.splitlines() if not chemin_de(ligne).startswith(prefixe))

    c1, arbre = _commande(["git", "--no-optional-locks", "ls-tree", "-r", "HEAD"], racine)
    c2, statut = _commande(["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=all"], racine)
    c3, head = _commande(["git", "--no-optional-locks", "rev-parse", "HEAD"], racine)
    if c1 or c2 or c3:
        return {"erreur": f"git a échoué (codes {c1}, {c2}, {c3})"}
    return {
        # Si Bouclier vit dans ce dépôt, HEAD avance à chaque commit de Bouclier : on compare l'arbre hors Bouclier.
        "head": "(avance avec les commits de Bouclier)" if contient_bouclier else head.strip(),
        "arbre_hors_bouclier": sha256_texte(hors_bouclier(arbre, lambda ligne: ligne.split("\t", 1)[-1])),
        "status_porcelain": hors_bouclier(statut, lambda ligne: ligne[3:].strip('"')),
    }


def racine_git(chemin: Path) -> Path | None:
    code, sortie = _commande(["git", "--no-optional-locks", "rev-parse", "--show-toplevel"], chemin)
    return Path(sortie.strip()).resolve() if code == 0 and sortie.strip() else None


def projets() -> dict[str, dict]:
    """Le dépôt qui contient Bouclier (s'il y en a un) et chaque dossier de ~/Projets (sauf Bouclier)."""
    resultat: dict[str, dict] = {}
    hote = racine_git(RACINE_BOUCLIER)
    if hote is not None and hote != RACINE_BOUCLIER:
        resultat["depot_hote"] = {
            "chemin": "(dépôt qui contient bouclier/)",
            "git": etat_git(hote, RACINE_BOUCLIER),
            "fichiers": fichiers_du_projet(hote, RACINE_BOUCLIER),
        }
    dossier_projets = MAISON / "Projets"
    if dossier_projets.is_dir():
        for p in sorted(dossier_projets.iterdir()):
            if not p.is_dir() or p.resolve() == RACINE_BOUCLIER:
                continue
            entree: dict = {"chemin": f"~/Projets/{p.name}", "fichiers": fichiers_du_projet(p, None)}
            if (p / ".git").exists():
                entree["git"] = etat_git(p, None)
            resultat[f"projets/{p.name}"] = entree
    return resultat


def launch_agents() -> dict[str, dict]:
    dossier = MAISON / "Library" / "LaunchAgents"
    resultat: dict[str, dict] = {}
    if not dossier.is_dir():
        return resultat
    code, liste = _commande(["launchctl", "list"])
    etats: dict[str, dict] = {}
    if code == 0:
        for ligne in liste.splitlines()[1:]:
            morceaux = ligne.split("\t")
            if len(morceaux) == 3:
                pid, _statut, label = morceaux
                # Chargé et en marche ou non : le numéro de processus change à chaque redémarrage du Mac, il ne
                # dit rien d'un changement fait par Bouclier.
                etats[label] = {"charge": True, "tourne": pid.strip() not in ("", "-")}
    for plist in sorted(dossier.glob("*.plist")):
        label = plist.stem
        if NOTRE_LABEL.match(label):
            continue
        resultat[label] = {
            "sha256": sha256_fichier(plist),
            "launchd": etats.get(label, {"charge": False, "tourne": False}),
        }
    return resultat


def support_applications() -> dict[str, str]:
    base = MAISON / "Library" / "Application Support"
    resultat: dict[str, str] = {}
    for nom in PROJETS_SUPPORT:
        d = base / nom
        if nom in NOS_DOSSIERS_SUPPORT or not d.is_dir():
            continue
        for chemin in sorted(d.rglob("*")):
            if chemin.is_file() and chemin.suffix.lower() in EXTENSIONS_REGLAGES:
                resultat[f"{nom}/{chemin.relative_to(d).as_posix()}"] = sha256_fichier(chemin)
    return resultat


def mac_divers() -> dict[str, str]:
    resultat: dict[str, str] = {}
    for nom in (".zshrc", ".zprofile"):
        f = MAISON / nom
        resultat[nom] = sha256_fichier(f) if f.is_file() else "absent"
    code, cron = _commande(["crontab", "-l"])
    resultat["crontab -l"] = sha256_texte(cron) if code == 0 else "vide ou absent"
    boite = ICLOUD / "BoiteMac"
    if boite.is_dir():
        noms = sorted(p.relative_to(boite).as_posix() for p in boite.rglob("*"))
        resultat["iCloud BoiteMac (liste)"] = sha256_texte("\n".join(noms))
    else:
        resultat["iCloud BoiteMac (liste)"] = "absent"
    code, raccourcis = _commande(["shortcuts", "list"])
    if code == 0:
        # Nos deux raccourcis, une fois ajoutés par toi, ne doivent pas faire croire à un changement.
        autres = [r for r in raccourcis.splitlines() if r.strip() not in ("Arnaque ?", "Envoyer sans traces")]
        resultat["shortcuts list"] = sha256_texte("\n".join(sorted(autres)))
    else:
        resultat["shortcuts list"] = "indisponible"
    return resultat


def capturer() -> dict:
    return {
        "format": 1,
        "machine": {"systeme": platform.system(), "noeud": sha256_texte(platform.node())[:16]},
        "projets": projets(),
        "launch_agents": launch_agents(),
        "application_support": support_applications(),
        "divers": mac_divers(),
    }


def _diff_dict(prefixe: str, avant: dict, apres: dict, ecarts: list[str]) -> None:
    for cle in sorted(set(avant) | set(apres)):
        a, b = avant.get(cle, "∅ (absent)"), apres.get(cle, "∅ (absent)")
        if isinstance(a, dict) and isinstance(b, dict):
            _diff_dict(f"{prefixe}{cle} › ", a, b, ecarts)
        elif a != b:
            ecarts.append(f"{prefixe}{cle} : {str(a)[:80]!s} → {str(b)[:80]!s}")


def comparer(reference: dict, actuel: dict) -> list[str]:
    ecarts: list[str] = []
    for section in ("projets", "launch_agents", "application_support", "divers"):
        _diff_dict(f"[{section}] ", reference.get(section, {}), actuel.get(section, {}), ecarts)
    return ecarts


def resume(etat: dict) -> str:
    n_fichiers = sum(len(p.get("fichiers", {})) for p in etat["projets"].values())
    return (
        f"{len(etat['projets'])} projet(s), {n_fichiers} fichiers, {len(etat['launch_agents'])} LaunchAgent(s), "
        f"{len(etat['application_support'])} réglage(s) Application Support, {len(etat['divers'])} élément(s) divers"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("capturer", "comparer"):
        print(__doc__)
        return 2
    cible = Path(argv[2])
    if argv[1] == "capturer":
        etat = capturer()
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(json.dumps(etat, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Empreinte « avant » écrite : {resume(etat)}")
        return 0
    reference = json.loads(cible.read_text(encoding="utf-8"))
    actuel = capturer()
    ecarts = comparer(reference, actuel)
    if ecarts:
        print(f"INTÉGRITÉ : {len(ecarts)} ÉCART(S) par rapport à {cible.name}")
        for e in ecarts[:50]:
            print("  ✗", e)
        return 1
    print(f"INTÉGRITÉ OK : identique à {cible.name} ({resume(actuel)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
