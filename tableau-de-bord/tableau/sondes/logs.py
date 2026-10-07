"""Les journaux des modules : lus par la fin, en lecture seule, avec un curseur gardé chez nous (§1.2).

- Le curseur (numéro de fichier, position, taille, empreinte du début) est dans **notre** base : après un redémarrage
  du tableau de bord, la lecture reprend où elle s'était arrêtée, sans recompter les erreurs.
- Rotation (`assistant.log` → `assistant.log.1`) : la fin de l'ancien fichier est lue sous son nouveau nom (même
  numéro de fichier), puis le nouveau depuis le début. Troncature, ou fichier réécrit sous le même numéro : relu
  depuis le début.
- La première fois, seuls les 256 derniers Ko sont lus (les erreurs des dernières 24 h, sans tout l'historique).
- Chaque lecture ouvre le fichier, lit au plus 512 Ko de lignes complètes, et le referme aussitôt.

Formats reconnus (tolérants) : `2026-10-07 10:00:00 ERROR   [trieur] …` (assistant), `2026-10-07 10:00:00,123 ERROR
[daemon] …` (Bouclier), `2026-10-07 10:00:00,123 ERROR …` (Quotidien), et toute ligne sans date (« Traceback »,
sortie d'erreur brute). Une ligne sans date qui suit une ligne datée en est la suite (pile d'appels) : elle n'est
pas recomptée.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tableau.db import Base

PREMIERE_LECTURE = 256 * 1024
LECTURE_MAX = 512 * 1024
TETE = 256

_DATE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T](?P<heure>\d{2}:\d{2}:\d{2})(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?\s+"
)
_NIVEAU = re.compile(
    r"^(?P<niveau>DEBUG|INFO|NOTICE|WARNING|WARN|ERROR|CRITICAL|FATAL|ERREUR|AVERTISSEMENT|ATTENTION)\b[:\s]*",
    re.IGNORECASE,
)
_COMPOSANT = re.compile(r"^\[(?P<composant>[\w.\-]+)\]\s?")
_ERREUR_LIBRE = re.compile(r"Traceback \(most recent call last\)|\b(Error|Exception|Erreur|Plantage)\b[:\s]")
NIVEAUX = {
    "error": "erreur",
    "critical": "erreur",
    "fatal": "erreur",
    "erreur": "erreur",
    "warning": "avertissement",
    "warn": "avertissement",
    "avertissement": "avertissement",
    "attention": "avertissement",
}


@dataclass
class Ligne:
    ts: float | None
    niveau: str  # erreur, avertissement, info
    composant: str | None
    message: str


def _instant(date: str, heure: str) -> float | None:
    try:
        return datetime.strptime(f"{date} {heure}", "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def analyser(texte: str) -> list[Ligne]:
    """Les enregistrements d'un morceau de journal (les suites de pile d'appels rattachées à leur ligne)."""
    resultat: list[Ligne] = []
    pile: str | None = None  # « rattachee » : pile d'une ligne datée ; « libre » : pile seule (sortie d'erreur)
    for brute in texte.splitlines():
        if not brute.strip():
            continue
        m = _DATE.match(brute)
        if m:
            pile = None
            reste = brute[m.end() :]
            niveau = "info"
            n = _NIVEAU.match(reste)
            if n:
                niveau = NIVEAUX.get(n.group("niveau").lower(), "info")
                reste = reste[n.end() :]
            composant = None
            c = _COMPOSANT.match(reste)
            if c:
                composant = c.group("composant")
                reste = reste[c.end() :]
            if niveau == "info" and n is None and _ERREUR_LIBRE.search(reste):
                niveau = "erreur"
            resultat.append(Ligne(_instant(m.group("date"), m.group("heure")), niveau, composant, reste.strip()))
            continue
        # Une ligne sans date.
        if brute[:1] in (" ", "\t"):
            continue  # suite d'une pile d'appels ou d'un message sur plusieurs lignes
        if brute.startswith("Traceback"):
            if resultat and resultat[-1].ts is not None and pile is None:
                pile = "rattachee"  # la pile de l'erreur datée juste au-dessus : pas une nouvelle erreur
            else:
                resultat.append(Ligne(None, "erreur", None, brute.strip()))
                pile = "libre"
            continue
        if pile is not None:
            # La dernière ligne d'une pile (« ValueError: … ») : le message d'une pile seule, rien sinon.
            if pile == "libre" and resultat:
                resultat[-1].message = brute.strip()
            pile = None
            continue
        if resultat and resultat[-1].ts is not None:
            continue  # suite d'un enregistrement daté (message sur plusieurs lignes)
        niveau = "erreur" if _ERREUR_LIBRE.search(brute) else "info"
        resultat.append(Ligne(None, niveau, None, brute.strip()))
    return resultat


def _tete(chemin: Path, n: int = TETE) -> str:
    """« n:empreinte » des n premiers octets : un fichier réécrit sous le même numéro n'a plus la même tête."""
    with open(chemin, "rb") as f:
        debut = f.read(n)
    return f"{len(debut)}:{hashlib.sha1(debut).hexdigest()}"


def _meme_tete(chemin: Path, tete: str) -> bool:
    try:
        n = int(tete.split(":", 1)[0])
    except ValueError:
        return True
    return _tete(chemin, n) == tete


def _lire(chemin: Path, debut: int, maximum: int) -> tuple[bytes, int]:
    """Les lignes complètes à partir de `debut` (au plus `maximum` octets) et la nouvelle position."""
    with open(chemin, "rb") as f:
        f.seek(debut)
        donnees = f.read(maximum)
    fin = donnees.rfind(b"\n")
    if fin < 0:
        return b"", debut
    return donnees[: fin + 1], debut + fin + 1


def _aligner(chemin: Path, position: int) -> int:
    """La première ligne complète à partir de `position` (0 reste 0)."""
    if position <= 0:
        return 0
    with open(chemin, "rb") as f:
        f.seek(position - 1)
        bloc = f.read(65536)
    i = bloc.find(b"\n")
    return position + i if i >= 0 else position


class LecteurJournaux:
    def __init__(self, base: Base, horloge: Callable[[], float] = time.time) -> None:
        self.base = base
        self.horloge = horloge
        self._tour: dict[str, list[Ligne]] = {}

    def nouveau_tour(self) -> None:
        self._tour = {}

    def nouvelles_lignes(self, chemin: Path) -> list[Ligne]:
        """Les lignes apparues depuis la dernière lecture (une seule lecture par fichier et par tour)."""
        cle = str(chemin)
        if cle not in self._tour:
            try:
                self._tour[cle] = analyser(self._nouveau_texte(chemin).decode("utf-8", errors="replace"))
            except OSError:
                self._tour[cle] = []
        return self._tour[cle]

    def _curseur(self, cle: str) -> tuple[int | None, int, int, str] | None:
        r = self.base.ligne("SELECT inode, position, taille, tete FROM curseurs WHERE cle = ?", (cle,))
        return None if r is None else (r["inode"], int(r["position"]), int(r["taille"]), r["tete"] or "")

    def _retenir(self, cle: str, inode: int, position: int, taille: int, tete: str) -> None:
        self.base.executer(
            "INSERT INTO curseurs (cle, inode, position, taille, tete, maj) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(cle) DO UPDATE SET inode = excluded.inode, position = excluded.position, "
            "taille = excluded.taille, tete = excluded.tete, maj = excluded.maj",
            (cle, inode, position, taille, tete, self.horloge()),
        )

    def _ancien_sous_un_autre_nom(self, chemin: Path, inode: int) -> Path | None:
        """Après une rotation, le fichier lu jusqu'ici porte un autre nom (`x.log.1`, `x.log.0`…)."""
        try:
            voisins = [p for p in chemin.parent.iterdir() if p.name.startswith(chemin.name) and p != chemin]
        except OSError:
            return None
        for p in sorted(voisins)[:10]:
            try:
                if os.stat(p).st_ino == inode:
                    return p
            except OSError:
                continue
        return None

    def _nouveau_texte(self, chemin: Path) -> bytes:
        cle = str(chemin)
        try:
            st = os.stat(chemin)
        except OSError:
            return b""
        curseur = self._curseur(cle)
        morceaux: list[bytes] = []
        if curseur is None:
            position = _aligner(chemin, max(0, st.st_size - PREMIERE_LECTURE))
        else:
            inode, position, _taille, tete = curseur
            if inode is not None and inode != st.st_ino:
                ancien = self._ancien_sous_un_autre_nom(chemin, inode)
                if ancien is not None:
                    morceau, _ = _lire(ancien, position, LECTURE_MAX)
                    morceaux.append(morceau)
                position = 0
            elif st.st_size < position or (tete and not _meme_tete(chemin, tete)):
                position = 0  # tronqué, ou réécrit sous le même numéro
        morceau, position = _lire(chemin, position, LECTURE_MAX)
        morceaux.append(morceau)
        self._retenir(cle, st.st_ino, position, st.st_size, _tete(chemin))
        return b"".join(morceaux)


def debut_de_case(ts: float, pas: int = 300) -> float:
    return float(int(ts // pas) * pas)


def compter(base: Base, module: str, lignes: list[Ligne], maintenant: float) -> None:
    """Range les erreurs et avertissements par tranches de 5 minutes, et garde les dernières erreurs (caviardées)."""
    from tableau.caviardage import caviarder

    cases: dict[float, list[int]] = {}
    erreurs: list[tuple[str, float, str]] = []
    for ligne in lignes:
        if ligne.niveau == "info":
            continue
        ts = ligne.ts if ligne.ts is not None and ligne.ts <= maintenant + 120 else maintenant
        if ts < maintenant - 35 * 86400:
            continue
        case = cases.setdefault(debut_de_case(ts), [0, 0])
        case[0 if ligne.niveau == "erreur" else 1] += 1
        if ligne.niveau == "erreur":
            erreurs.append((module, ts, caviarder(ligne.message, 300)))
    if cases:
        base.plusieurs(
            "INSERT INTO compteurs_logs (module, heure, erreurs, avertissements) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(module, heure) DO UPDATE SET erreurs = erreurs + excluded.erreurs, "
            "avertissements = avertissements + excluded.avertissements",
            [(module, case, e, a) for case, (e, a) in cases.items()],
        )
    if erreurs:
        base.plusieurs("INSERT INTO dernieres_erreurs (module, ts, message) VALUES (?, ?, ?)", erreurs[-20:])


def statistiques(base: Base, module: str, maintenant: float) -> dict[str, int | float | str | None]:
    """Erreurs et avertissements sur 1 h et 24 h, moyenne horaire sur 7 jours, dernière erreur."""

    def somme(colonne: str, depuis: float, jusqua: float | None = None) -> int:
        fin = maintenant + 300 if jusqua is None else jusqua
        return int(
            base.valeur(
                f"SELECT COALESCE(SUM({colonne}), 0) FROM compteurs_logs WHERE module = ? AND heure >= ? AND heure < ?",
                (module, debut_de_case(depuis), fin),
                0,
            )
        )

    derniere = base.ligne(
        "SELECT ts, message FROM dernieres_erreurs WHERE module = ? ORDER BY ts DESC LIMIT 1", (module,)
    )
    semaine = somme("erreurs", maintenant - 7 * 86400, debut_de_case(maintenant - 3600))
    return {
        "erreurs_1h": somme("erreurs", maintenant - 3600),
        "erreurs_24h": somme("erreurs", maintenant - 86400),
        "avert_1h": somme("avertissements", maintenant - 3600),
        "avert_24h": somme("avertissements", maintenant - 86400),
        "moyenne_horaire_7j": semaine / (7 * 24 - 1),
        "derniere_erreur": derniere["message"] if derniere else None,
        "derniere_erreur_ts": float(derniere["ts"]) if derniere else None,
    }


def dernieres_erreurs(base: Base, module: str, n: int = 10) -> list[tuple[float, str]]:
    return [
        (float(r["ts"]), str(r["message"]))
        for r in base.lignes(
            "SELECT ts, message FROM dernieres_erreurs WHERE module = ? ORDER BY ts DESC LIMIT ?", (module, n)
        )
    ]


def nettoyer_dernieres_erreurs(base: Base, module: str, garder: int = 50) -> None:
    base.executer(
        "DELETE FROM dernieres_erreurs WHERE module = ? AND ts < COALESCE((SELECT ts FROM dernieres_erreurs "
        "WHERE module = ? ORDER BY ts DESC LIMIT 1 OFFSET ?), 0)",
        (module, module, garder - 1),
    )
