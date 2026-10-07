"""L'échange avec l'iPhone par iCloud Drive (§5, §8) : les raccourcis déposent, le Mac répond.

- « Mon frigo » dépose `Quotidien/entree/frigo-<id>.jpg` (ou `.txt`) ; « Envie de… » dépose `envie-<id>.txt`.
- Le Mac répond dans `Quotidien/reponses/<id>.txt`, dans le MÊME dossier racine que la demande : un chemin relatif
  d'un raccourci désigne le dossier iCloud de l'app Raccourcis (leçon du Trieur), le Mac surveille donc les deux.
- Une demande est traitée une seule fois (table `demandes`), puis supprimée (une photo garde ses métadonnées sur
  l'iPhone, pas sur le Mac). Les réponses de plus d'un jour sont effacées.
- Un fichier encore en cours d'écriture par iCloud (récent de moins de 2 s, ou « .icloud » pas encore téléchargé)
  attend le tour suivant.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from quotidien import config
from quotidien.db import Base as BaseDonnees
from quotidien.journal import log

NOM_DEMANDE = re.compile(r"^(?P<genre>frigo|envie)-(?P<id>[A-Za-z0-9_\-]{4,60})(?:\.(?P<ext>[A-Za-z0-9]{1,5}))?$")
IMAGES = {"jpg", "jpeg", "png", "heic", "heif", "webp"}
TAILLE_MAX = 25 * 1024 * 1024
TEXTE_MAX = 4000
STABLE_S = 2.0
GARDE_REPONSES_S = 86400
ECHEC = "😕 Le Mac n'a pas réussi à traiter ta demande. Réessaie, ou écris la liste en texte."


@dataclass(frozen=True)
class Demande:
    genre: str  # frigo ou envie
    id: str  # « frigo-20261007-193000-4821 » : le nom de la réponse
    chemin: Path
    racine: Path  # Quotidien/ (iCloud Drive) ou Shortcuts/Quotidien/

    @property
    def image(self) -> bool:
        return self.chemin.suffix.lower().lstrip(".") in IMAGES

    def texte(self) -> str:
        return self.chemin.read_text(encoding="utf-8", errors="replace")[:TEXTE_MAX].strip()


def racines() -> list[Path]:
    return [config.dossier_icloud(), config.dossier_icloud_raccourcis()]


def preparer_dossiers() -> None:
    for r in racines():
        for sous in ("entree", "reponses"):
            (r / sous).mkdir(parents=True, exist_ok=True)


def en_attente(maintenant: float | None = None) -> list[Demande]:
    t = maintenant or time.time()
    trouvees: list[Demande] = []
    for racine in racines():
        entree = racine / "entree"
        if not entree.is_dir():
            continue
        for f in sorted(entree.iterdir()):
            m = NOM_DEMANDE.match(f.name)
            if not m or not f.is_file() or f.is_symlink():
                continue
            try:
                info = f.stat()
            except OSError:
                continue
            if t - info.st_mtime < STABLE_S:
                continue  # iCloud écrit encore
            trouvees.append(Demande(m.group("genre"), f.name.rsplit(".", 1)[0] if m.group("ext") else f.name, f,
                                    racine))  # fmt: skip
    return trouvees


def repondre(demande: Demande, texte: str) -> Path:
    """Écrit la réponse d'un coup (fichier temporaire puis renommage) : l'iPhone ne lit jamais une moitié."""
    dossier = demande.racine / "reponses"
    dossier.mkdir(parents=True, exist_ok=True)
    final = dossier / f"{demande.id}.txt"
    temporaire = dossier / f".{demande.id}.tmp"
    temporaire.write_text(texte.strip() + "\n", encoding="utf-8")
    temporaire.replace(final)
    return final


def deja_traitee(db: BaseDonnees, demande: Demande) -> bool:
    return db.cx.execute("SELECT 1 FROM demandes WHERE id = ?", (demande.id,)).fetchone() is not None


def noter(db: BaseDonnees, demande: Demande, statut: str, maintenant: float) -> None:
    with db.transaction() as cx:
        cx.execute("INSERT OR REPLACE INTO demandes(id, recue_le, genre, statut) VALUES (?, ?, ?, ?)",
                   (demande.id, maintenant, demande.genre, statut))  # fmt: skip


Traitement = Callable[[Demande], str]


def traiter(db: BaseDonnees, traitements: dict[str, Traitement], maintenant: float | None = None) -> int:
    """Traite chaque nouvelle demande (une seule fois), répond, puis supprime la demande. Renvoie le nombre traité."""
    t = maintenant or time.time()
    n = 0
    for d in en_attente(t):
        if deja_traitee(db, d):
            _supprimer(d.chemin)
            continue
        try:
            if d.chemin.stat().st_size > TAILLE_MAX:
                reponse = "📷 Fichier trop gros (25 Mo au plus) : envoie une photo plus légère ou la liste en texte."
            else:
                reponse = traitements[d.genre](d)
            statut = "ok"
        except Exception as e:  # noqa: BLE001 - une demande abîmée ne doit jamais arrêter le démon
            log().warning("demande %s : %s", d.genre, e.__class__.__name__)
            reponse, statut = ECHEC, "erreur"
        repondre(d, reponse)
        noter(db, d, statut, t)
        _supprimer(d.chemin)
        n += 1
    nettoyer(t)
    return n


def _supprimer(chemin: Path) -> None:
    try:
        chemin.unlink()
    except OSError:
        pass


def nettoyer(maintenant: float) -> None:
    for racine in racines():
        dossier = racine / "reponses"
        if not dossier.is_dir():
            continue
        for f in dossier.iterdir():
            try:
                if f.is_file() and maintenant - f.stat().st_mtime > GARDE_REPONSES_S:
                    f.unlink()
            except OSError:
                continue
