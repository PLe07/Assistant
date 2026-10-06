"""Le nettoyeur de métadonnées (n°21) : une **copie propre** « nom (propre).ext » à côté de l'original, qui n'est
jamais modifié (son empreinte est vérifiée avant et après). Avec `--remplacer`, l'original part à la Corbeille par
le Finder (jamais `rm`) et la copie propre prend son nom.

Formats : JPEG, HEIC, PNG, WebP, TIFF (EXIF, GPS, XMP, IPTC, notes du fabricant, numéro de série), PDF (auteur,
logiciel, XMP), Word/Excel/PowerPoint (auteur, entreprise, dernier modificateur ; commentaires signalés), MOV/MP4
(avec ffmpeg). Tout autre format : rien n'est modifié, et Bouclier le dit.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from bouclier.metadonnees import lecture, verif
from bouclier.metadonnees.formats import image, office, pdf, video
from bouclier.systeme import Systeme

EXT_OFFICE = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm"}
EXT_VIDEO = {".mov", ".mp4", ".m4v"}


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def genre_de(chemin: Path, debut: bytes) -> str | None:
    g = image.format_image(debut)
    if g:
        return g
    if debut[:5] == b"%PDF-":
        return "pdf"
    ext = chemin.suffix.lower()
    if ext in EXT_OFFICE and debut[:2] == b"PK":
        return "office"
    if ext in EXT_VIDEO and debut[4:8] == b"ftyp":
        return "video"
    return None


def nom_propre(chemin: Path) -> Path:
    base = chemin.with_name(f"{chemin.stem} (propre){chemin.suffix}")
    n = 2
    while base.exists():
        base = chemin.with_name(f"{chemin.stem} (propre {n}){chemin.suffix}")
        n += 1
    return base


@dataclass
class Rapport:
    original: Path
    propre: Path | None = None
    supprime: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    restants: list[str] = field(default_factory=list)
    erreur: str | None = None
    remplace: bool = False

    def texte(self) -> str:
        if self.erreur:
            return f"❌ {self.original.name} : {self.erreur}"
        lignes = [f"✅ {self.original.name} → {self.propre.name if self.propre else '?'}"]
        lignes.append("   Supprimé : " + (", ".join(self.supprime) if self.supprime else "aucune métadonnée trouvée"))
        for a in self.avertissements:
            lignes.append(f"   ⚠️ {a}")
        if self.restants:
            lignes.append("   ⚠️ Encore présent après nettoyage : " + ", ".join(self.restants))
        if self.remplace:
            lignes.append("   L'original est dans la Corbeille (récupérable).")
        return "\n".join(lignes)


def _valeurs_sensibles(donnees: bytes, genre: str) -> list[str]:
    """Les valeurs en clair à rechercher après coup (auteur, appareil, numéro de série)."""
    valeurs: list[str] = []
    if genre in ("jpeg", "png", "webp", "tiff", "heic"):
        from PIL import Image

        image.ouvrir_heif()
        try:
            with Image.open(io.BytesIO(donnees)) as img:
                exif = img.getexif()
                detail = exif.get_ifd(image.IFD_EXIF)
                for v in (exif.get(0x013B), exif.get(0x010F), exif.get(0x0110), detail.get(0xA431),
                          detail.get(0xA435), img.info.get("Author")):  # fmt: skip
                    if v and str(v).strip():
                        valeurs.append(str(v).strip().strip("\x00"))
        except Exception:  # noqa: BLE001
            pass
    elif genre == "office":
        with zipfile.ZipFile(io.BytesIO(donnees)) as z:
            if "docProps/core.xml" in z.namelist():
                core = z.read("docProps/core.xml").decode("utf-8", "replace")
                valeurs += re.findall(r"<(?:\w+:)?(?:creator|lastModifiedBy)\b[^>]*>([^<]{4,})<", core)
    return valeurs


def nettoyer(chemin: Path, *, remplacer: bool = False, garder_date: bool = False,
             systeme: Systeme | None = None) -> Rapport:  # fmt: skip
    chemin = Path(chemin).expanduser()
    rapport = Rapport(chemin)
    if chemin.is_symlink() or not chemin.is_file():
        rapport.erreur = "ce n'est pas un fichier"
        return rapport
    with chemin.open("rb") as f:
        debut = f.read(64)
    genre = genre_de(chemin, debut)
    if genre is None:
        rapport.erreur = "format non géré : rien n'a été modifié (il peut contenir des métadonnées)"
        return rapport
    avant = empreinte(chemin)
    try:
        if genre == "video":
            rapport.supprime = video.lire(chemin)
            propre_octets = video.nettoyer(chemin)
            valeurs: list[str] = []
        else:
            donnees = chemin.read_bytes()
            valeurs = _valeurs_sensibles(donnees, genre)
            if genre == "pdf":
                rapport.supprime = pdf.lire(donnees)
                propre_octets = pdf.nettoyer(donnees)
                rapport.restants = verif.restants_pdf(propre_octets)
            elif genre == "office":
                rapport.supprime, rapport.avertissements = office.lire(donnees)
                propre_octets = office.nettoyer(donnees)
                rapport.restants = verif.restants_office(propre_octets)
            else:
                rapport.supprime = lecture.lire_image(donnees)
                resultat = image.nettoyer(donnees, genre, garder_date)
                propre_octets = resultat.donnees
                rapport.avertissements += resultat.notes
                rapport.restants = verif.restants_image(propre_octets, garder_date)
                if garder_date and "date de prise de vue" in rapport.supprime:
                    rapport.supprime.remove("date de prise de vue")
                    rapport.avertissements.append("date de prise de vue gardée, comme demandé")
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as e:
        rapport.erreur = str(e) or e.__class__.__name__
        return rapport
    except Exception as e:  # noqa: BLE001 - un fichier abîmé ne doit jamais faire planter Bouclier
        rapport.erreur = f"fichier illisible ({e.__class__.__name__}) : rien n'a été modifié"
        return rapport
    rapport.restants += [f"valeur « {v} »" for v in verif.valeurs_restantes(propre_octets, valeurs)]
    cible = nom_propre(chemin)
    temporaire = cible.with_name(f".{cible.name}.bouclier-tmp")
    temporaire.write_bytes(propre_octets)
    try:
        os.chmod(temporaire, chemin.stat().st_mode & 0o777)
    except OSError:
        pass
    os.replace(temporaire, cible)
    rapport.propre = cible
    autre = verif.exiftool(cible)
    if autre:
        rapport.restants += [f"exiftool : {k}" for k in autre if not (garder_date and "Date" in k)]
    if empreinte(chemin) != avant:  # pragma: no cover - impossible : l'original n'est jamais ouvert en écriture
        rapport.erreur = "l'original a changé pendant le nettoyage : vérifie-le"
        return rapport
    if remplacer and not rapport.restants:
        if (systeme or Systeme()).corbeille(chemin) and not chemin.exists():
            os.replace(cible, chemin)
            rapport.propre, rapport.remplace = chemin, True
        else:
            rapport.avertissements.append("l'original n'a pas pu aller à la Corbeille : les deux fichiers sont gardés")
    elif remplacer:
        rapport.avertissements.append("des métadonnées restent : l'original est gardé")
    return rapport
