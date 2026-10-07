"""Le gardien d'intégrité : le code et les réglages de chaque projet, comparés à leur référence (§4.5).

- Même périmètre que l'empreinte « avant » (§1.1) : chaque fichier de code et de réglages du projet (sans `.git/`,
  sans données ni journaux), le plist de ses LaunchAgents, les réglages de son dossier Application Support.
- La **référence** est prise la première fois (ou quand tu dis « C'était moi, nouvelle référence ») et gardée dans
  notre base. Ensuite : contrôle toutes les 30 minutes, et dès que FSEvents signale un changement dans un dossier de
  code. Un fichier dont la taille, la date et le numéro n'ont pas bougé n'est pas relu ; une fois par jour, tout est
  relu.
- Un changement : la liste des fichiers (ajoutés, modifiés, supprimés) avec leur date, et le commit git s'il y en a
  un. Le tableau de bord ne restaure jamais rien : « Pas normal » affiche la commande `git diff` à lancer toi-même.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tableau import systeme
from tableau.db import Base
from tableau.module import DefModule

RACINE_TABLEAU = Path(__file__).resolve().parents[2]
DOSSIERS_VIVANTS = {
    ".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".hypothesis",
    "donnees", "logs", "node_modules", ".cache-ocr", ".cache-corpus", "sorties", "caches", "cache", "copies",
}  # fmt: skip
FICHIERS_VIVANTS = re.compile(
    r"(\.db|\.db-journal|\.db-wal|\.db-shm|\.sqlite|\.sqlite-wal|\.sqlite-shm|\.log|\.log\.\d+|\.pyc"
    r"|^\.coverage.*|^PAUSE|^\.verrou|^\.DS_Store|\.verrou|\.tmp)$"
)
EXTENSIONS_REGLAGES = {".json", ".toml", ".plist", ".yaml", ".yml", ".ini", ".conf", ".cfg", ".txt"}
ETATS_VIVANTS_SUPPORT = re.compile(r"(^|/)(etat|brief|cache[^/]*)\.json$|(^|/)caches?/")
JOUR = 86400
FICHIERS_MAX = 50_000


@dataclass
class Fiche:
    sha256: str
    taille: int
    mtime_ns: int
    inode: int


@dataclass
class Ecart:
    chemin: str
    genre: str  # ajouté, modifié, supprimé
    quand: float | None


@dataclass
class Resultat:
    module: str
    reference_prise: bool = False
    ecarts: list[Ecart] = field(default_factory=list)
    commit: dict[str, str] | None = None
    fichiers: int = 0


def _vivant(rel: str) -> bool:
    morceaux = rel.split("/")
    return any(m in DOSSIERS_VIVANTS for m in morceaux[:-1]) or bool(FICHIERS_VIVANTS.search(morceaux[-1]))


def _sha(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


class Gardien:
    def __init__(self, base: Base, maison: Path, launch_agents: Path, horloge: Callable[[], float],
                 executer: Callable[[list[str]], systeme.Resultat] | None = None) -> None:  # fmt: skip
        self.base = base
        self.maison = maison
        self.launch_agents = launch_agents
        self.horloge = horloge
        self.executer = executer or (lambda args: systeme.executer(args, delai=10))

    # --- le périmètre -----------------------------------------------------------------------------------------------

    def racine(self, defn: DefModule) -> Path | None:
        return defn.chemin(defn.dossier_projet, self.maison) if defn.dossier_projet else None

    def fichiers(self, defn: DefModule) -> Iterator[tuple[str, Path]]:
        """(nom dans la référence, chemin) de chaque fichier du périmètre."""
        racine = self.racine(defn)
        vus = 0
        if racine is not None and racine.is_dir():
            exclus = {(racine / e).resolve() for e in defn.perimetre_exclu}
            exclus.add(RACINE_TABLEAU)
            for inclus in defn.perimetre_code:
                depart = (racine / inclus).resolve() if inclus != "." else racine.resolve()
                if depart.is_file():
                    yield inclus, depart
                    continue
                for dossier, sous, noms in os.walk(depart):
                    d = Path(dossier)
                    sous[:] = sorted(s for s in sous if s not in DOSSIERS_VIVANTS and (d / s).resolve() not in exclus)
                    for nom in sorted(noms):
                        chemin = d / nom
                        rel = chemin.relative_to(racine.resolve()).as_posix()
                        if _vivant(rel) or chemin.is_symlink() or chemin.resolve() in exclus:
                            continue
                        vus += 1
                        if vus > FICHIERS_MAX:
                            return
                        yield rel, chemin
        for label in defn.labels:
            plist = self.launch_agents / f"{label}.plist"
            if plist.is_file():
                yield f"plist:{label}", plist
        support = defn.chemin(defn.dossier_donnees, self.maison) if defn.dossier_donnees else None
        if support is not None and support.is_dir():
            for chemin in sorted(support.rglob("*")):
                rel = chemin.relative_to(support).as_posix()
                if (chemin.is_file() and chemin.suffix.lower() in EXTENSIONS_REGLAGES
                        and not ETATS_VIVANTS_SUPPORT.search(rel) and not _vivant(rel)):  # fmt: skip
                    yield f"reglages:{rel}", chemin

    # --- référence et contrôle --------------------------------------------------------------------------------------

    def reference(self, module: str) -> dict[str, Fiche]:
        return {
            r["chemin"]: Fiche(r["sha256"], int(r["taille"] or 0), int(r["mtime_ns"] or 0), int(r["inode"] or 0))
            for r in self.base.lignes(
                "SELECT chemin, sha256, taille, mtime_ns, inode FROM integrite_reference WHERE module = ?", (module,)
            )
        }

    def empreinte(self, defn: DefModule, connues: dict[str, Fiche], complet: bool) -> dict[str, Fiche]:
        resultat: dict[str, Fiche] = {}
        for nom, chemin in self.fichiers(defn):
            try:
                st = os.stat(chemin)
            except OSError:
                continue
            ancienne = connues.get(nom)
            if (not complet and ancienne is not None and ancienne.taille == st.st_size
                    and ancienne.mtime_ns == st.st_mtime_ns and ancienne.inode == st.st_ino):  # fmt: skip
                resultat[nom] = ancienne
                continue
            try:
                resultat[nom] = Fiche(_sha(chemin), st.st_size, st.st_mtime_ns, st.st_ino)
            except OSError:
                continue
        return resultat

    def _head(self, defn: DefModule) -> str | None:
        racine = self.racine(defn)
        if racine is None or not (racine / ".git").exists():
            return None
        r = self.executer(["git", "--no-optional-locks", "-C", str(racine), "rev-parse", "HEAD"])
        return r.sortie.strip() if r.ok and r.sortie.strip() else None

    def commit(self, defn: DefModule) -> dict[str, str] | None:
        racine = self.racine(defn)
        if racine is None or not (racine / ".git").exists():
            return None
        r = self.executer(["git", "--no-optional-locks", "-C", str(racine), "log", "-1", "--format=%h%x09%ci%x09%s"])
        if not r.ok or "\t" not in r.sortie:
            return None
        court, date, sujet = (r.sortie.strip().split("\t", 2) + ["", ""])[:3]
        return {"commit": court, "date": date, "sujet": sujet}

    def prendre_reference(self, defn: DefModule) -> int:
        fiches = self.empreinte(defn, {}, complet=True)
        maintenant = self.horloge()
        with self.base.transaction():
            self.base.db.execute("DELETE FROM integrite_reference WHERE module = ?", (defn.id,))
            self.base.db.executemany(
                "INSERT INTO integrite_reference (module, chemin, sha256, taille, mtime_ns, inode) VALUES (?, ?, ?, ?, ?, ?)",
                [(defn.id, nom, f.sha256, f.taille, f.mtime_ns, f.inode) for nom, f in fiches.items()],
            )
            self.base.db.execute(
                "INSERT INTO integrite_etat (module, reference_le, controle_le, ecarts, head, head_reference) "
                "VALUES (?, ?, ?, '[]', ?, ?) ON CONFLICT(module) DO UPDATE SET reference_le = excluded.reference_le, "
                "controle_le = excluded.controle_le, ecarts = '[]', head = excluded.head, "
                "head_reference = excluded.head_reference, signale_le = NULL",
                (defn.id, maintenant, maintenant, self._head(defn), self._head(defn)),
            )
        return len(fiches)

    def controler(self, defn: DefModule, complet: bool | None = None) -> Resultat:
        etat = self.base.ligne("SELECT reference_le, controle_le FROM integrite_etat WHERE module = ?", (defn.id,))
        if etat is None:
            return Resultat(defn.id, reference_prise=True, fichiers=self.prendre_reference(defn))
        maintenant = self.horloge()
        if complet is None:
            dernier_complet = float(self.base.lire_meta(f"integrite_complet:{defn.id}") or 0)
            complet = maintenant - dernier_complet >= JOUR
        reference = self.reference(defn.id)
        actuel = self.empreinte(defn, reference, complet)
        if complet:
            self.base.ecrire_meta(f"integrite_complet:{defn.id}", str(maintenant))
        ecarts: list[Ecart] = []
        for nom in sorted(set(reference) | set(actuel)):
            a, b = reference.get(nom), actuel.get(nom)
            if a is None and b is not None:
                ecarts.append(Ecart(nom, "ajouté", b.mtime_ns / 1e9))
            elif b is None and a is not None:
                ecarts.append(Ecart(nom, "supprimé", None))
            elif a is not None and b is not None and a.sha256 != b.sha256:
                ecarts.append(Ecart(nom, "modifié", b.mtime_ns / 1e9))
        head = self._head(defn)
        self.base.executer(
            "UPDATE integrite_etat SET controle_le = ?, ecarts = ?, head = ? WHERE module = ?",
            (maintenant, json.dumps([vars(e) for e in ecarts], ensure_ascii=False), head, defn.id),
        )
        commit = self.commit(defn) if ecarts else None
        return Resultat(defn.id, ecarts=ecarts, commit=commit, fichiers=len(actuel))

    def etat(self, module: str) -> dict[str, Any] | None:
        r = self.base.ligne("SELECT * FROM integrite_etat WHERE module = ?", (module,))
        if r is None:
            return None
        try:
            ecarts = json.loads(r["ecarts"] or "[]")
        except ValueError:
            ecarts = []
        return {
            "reference_le": r["reference_le"],
            "controle_le": r["controle_le"],
            "ecarts": ecarts,
            "head": r["head"],
            "head_reference": r["head_reference"],
            "commit_change": bool(r["head"] and r["head_reference"] and r["head"] != r["head_reference"]),
        }

    def commande_diff(self, defn: DefModule) -> str:
        """La commande à lancer toi-même pour voir ce qui a changé (le tableau de bord ne restaure rien)."""
        racine = self.racine(defn)
        if racine is None:
            return "Pas de dossier de projet connu pour ce module."
        affiche = str(racine).replace(str(self.maison), "~", 1)
        if (racine / ".git").exists():
            chemins = " ".join(f"'{c}'" for c in defn.perimetre_code if c != ".")
            return f"cd {affiche} && git status && git diff {('-- ' + chemins) if chemins else ''}".rstrip()
        return f"cd {affiche} && ls -la"
