"""Empreinte des autres projets : capturer « avant », comparer ensuite (§1.1 et §1.3 de la mission).

Lecture seule, bibliothèque standard uniquement : ce script tourne avant même l'environnement Python du tableau de
bord, et n'écrit que le fichier de référence qu'on lui donne.

Ce qui est relevé, pour chaque projet trouvé :
- le dépôt qui contient le tableau de bord (l'assistant, avec Corvées, Nettoyeur, Trieur, Bouclier, Quotidien…),
  **hors** du dossier du tableau de bord : HEAD, `git status --porcelain`, l'arbre suivi et le SHA-256 de chaque
  fichier de code ou de réglages (sans `.git/`, sans les données ni les journaux) ;
- les autres projets de `~/Projets/*` (même chose) ;
- sur le Mac : les LaunchAgents (SHA-256 du plist + état launchd), les réglages dans
  `~/Library/Application Support/<Projet>/`, `~/.zshrc`, `~/.zprofile`, `crontab -l`, `shortcuts list` et
  `docker ps -a` (nom, image, état).

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
RACINE_TABLEAU = ICI.parent
MAISON = Path(os.environ.get("TABLEAU_INTEGRITE_MAISON") or Path.home())

# Données vivantes que les projets écrivent eux-mêmes en tournant (bases, journaux, caches d'outils) : elles changent
# sans nous, on ne les compare pas. Le code et les réglages, eux, doivent rester identiques.
DOSSIERS_VIVANTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    "donnees",
    "logs",
    "node_modules",
    ".cache-ocr",
    ".cache-corpus",
    "sorties",
}
FICHIERS_VIVANTS = re.compile(
    r"(\.db|\.db-journal|\.db-wal|\.db-shm|\.sqlite|\.sqlite-wal|\.sqlite-shm|\.log|\.log\.\d+|\.pyc"
    r"|^\.coverage.*|^PAUSE|^\.verrou|^\.DS_Store|\.verrou)$"
)

# Le nôtre : jamais comparé (il est créé par l'installation du tableau de bord). Nos agents de test
# (com.<x>.tdbtest.*), eux, SONT comparés : il ne doit en rester aucun après les tests.
NOTRE_LABEL = re.compile(r"^com\.[^.]+\.tableau$")
NOS_DOSSIERS_SUPPORT = {"TableauDeBord"}
PROJETS_SUPPORT = (
    "Corvees",
    "Corvées",
    "Nettoyeur",
    "Trieur",
    "Ambiance",
    "Assistant",
    "Demarrage",
    "Bouclier",
    "Quotidien",
)
EXTENSIONS_REGLAGES = {".json", ".toml", ".plist", ".yaml", ".yml", ".ini", ".conf", ".cfg", ".txt"}
# Fichiers d'état que les projets réécrivent eux-mêmes en tournant (ce sont des données, pas des réglages).
ETATS_VIVANTS_SUPPORT = re.compile(r"(^|/)(etat|brief|cache[^/]*|.*\.tmp)\.json$|(^|/)caches?/")


def sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def sha256_texte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8", "surrogateescape")).hexdigest()


def _commande(args: list[str], cwd: Path | None = None, delai: float = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=delai)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, f"indisponible : {e.__class__.__name__}"
    return proc.returncode, proc.stdout


def _est_vivant(rel: Path) -> bool:
    if any(part in DOSSIERS_VIVANTS for part in rel.parts[:-1]):
        return True
    return bool(FICHIERS_VIVANTS.search(rel.name))


def fichiers_du_projet(racine: Path, exclure: Path | None) -> dict[str, str]:
    """SHA-256 de chaque fichier (code et réglages), hors .git, hors données vivantes, hors tableau de bord."""
    resultat: dict[str, str] = {}
    for dossier, sous_dossiers, fichiers in os.walk(racine):
        d = Path(dossier)
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
    """HEAD, arbre suivi et état de la copie de travail, hors tableau de bord.

    `--no-optional-locks` : `git status` ne réécrit pas l'index du projet (aucune écriture chez lui)."""
    contient = exclure is not None and racine in exclure.parents
    prefixe = exclure.relative_to(racine).as_posix() + "/" if contient and exclure is not None else None

    def hors_tableau(lignes: str, chemin_de) -> str:
        return "\n".join(
            ligne for ligne in lignes.splitlines() if not (prefixe is not None and chemin_de(ligne).startswith(prefixe))
        )

    def hors_vivant(lignes: str) -> str:
        # Un journal ou une base suivis par git changent en tournant : ce sont des données, pas du code.
        return "\n".join(ligne for ligne in lignes.splitlines() if not _est_vivant(Path(ligne[3:].strip('"'))))

    c1, arbre = _commande(["git", "--no-optional-locks", "ls-tree", "-r", "HEAD"], racine)
    c2, statut = _commande(["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=all"], racine)
    c3, head = _commande(["git", "--no-optional-locks", "rev-parse", "HEAD"], racine)
    if c1 or c2 or c3:
        return {"erreur": f"git a échoué (codes {c1}, {c2}, {c3})"}
    return {
        # Si le tableau de bord vit dans ce dépôt, HEAD avance à chaque commit du tableau : on compare l'arbre hors
        # de son dossier, qui, lui, ne doit pas bouger.
        "head": "(avance avec les commits du tableau de bord)" if contient else head.strip(),
        "arbre_hors_tableau": sha256_texte(hors_tableau(arbre, lambda ligne: ligne.split("\t", 1)[-1])),
        "status_porcelain": hors_vivant(hors_tableau(statut, lambda ligne: ligne[3:].strip('"'))),
    }


def racine_git(chemin: Path) -> Path | None:
    code, sortie = _commande(["git", "--no-optional-locks", "rev-parse", "--show-toplevel"], chemin)
    return Path(sortie.strip()).resolve() if code == 0 and sortie.strip() else None


def projets() -> dict[str, dict]:
    """Le dépôt qui contient le tableau de bord (s'il y en a un) et chaque dossier de ~/Projets (sauf le nôtre)."""
    resultat: dict[str, dict] = {}
    hote = racine_git(RACINE_TABLEAU)
    if hote is not None and hote != RACINE_TABLEAU:
        resultat["depot_hote"] = {
            "chemin": "(dépôt qui contient tableau-de-bord/)",
            "git": etat_git(hote, RACINE_TABLEAU),
            "fichiers": fichiers_du_projet(hote, RACINE_TABLEAU),
        }
    dossier_projets = MAISON / "Projets"
    if dossier_projets.is_dir():
        for p in sorted(dossier_projets.iterdir()):
            if not p.is_dir() or p.resolve() == RACINE_TABLEAU or (hote is not None and p.resolve() == hote):
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
                pid, statut, label = morceaux
                # Le numéro de processus change à chaque redémarrage du Mac : on garde « chargé », « en marche » et
                # le dernier code de sortie, qui disent si un projet a été arrêté, relancé ou cassé.
                etats[label] = {
                    "charge": True,
                    "tourne": pid.strip() not in ("", "-"),
                    "dernier_code": statut.strip(),
                }
    for plist in sorted(dossier.glob("*.plist")):
        label = plist.stem
        if NOTRE_LABEL.match(label):
            continue
        resultat[label] = {
            "sha256": sha256_fichier(plist),
            "launchd": etats.get(label, {"charge": False, "tourne": False, "dernier_code": "-"}),
        }
    # Un de nos agents de test resté chargé sans son plist serait une trace : on le relève aussi.
    for label, etat in sorted(etats.items()):
        if ".tdbtest." in label and label not in resultat:
            resultat[label] = {"sha256": "(plist absent)", "launchd": etat}
    return resultat


def support_applications() -> dict[str, str]:
    base = MAISON / "Library" / "Application Support"
    resultat: dict[str, str] = {}
    for nom in PROJETS_SUPPORT:
        d = base / nom
        if nom in NOS_DOSSIERS_SUPPORT or not d.is_dir():
            continue
        for chemin in sorted(d.rglob("*")):
            rel = chemin.relative_to(d).as_posix()
            if (
                chemin.is_file()
                and chemin.suffix.lower() in EXTENSIONS_REGLAGES
                and not ETATS_VIVANTS_SUPPORT.search(rel)
            ):
                resultat[f"{nom}/{rel}"] = sha256_fichier(chemin)
    return resultat


def mac_divers() -> dict[str, str]:
    resultat: dict[str, str] = {}
    for nom in (".zshrc", ".zprofile"):
        f = MAISON / nom
        resultat[nom] = sha256_fichier(f) if f.is_file() else "absent"
    code, cron = _commande(["crontab", "-l"])
    resultat["crontab -l"] = sha256_texte(cron) if code == 0 else "vide ou absent"
    code, raccourcis = _commande(["shortcuts", "list"])
    resultat["shortcuts list"] = (
        sha256_texte("\n".join(sorted(raccourcis.splitlines()))) if code == 0 else "indisponible"
    )
    code, docker = _commande(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.State}}"], delai=30)
    resultat["docker ps -a"] = "\n".join(sorted(docker.strip().splitlines())) if code == 0 else "indisponible"
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
