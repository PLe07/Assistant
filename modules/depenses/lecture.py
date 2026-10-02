"""Lire le texte d'un reçu SUR TON MAC : Vision (comme les yeux) pour une photo, PDFKit pour un PDF.
L'image ne quitte jamais le Mac : seul le texte lu part à Claude."""

from pathlib import Path


class RecuIllisible(Exception):
    """Le message dit pourquoi, simplement."""


def _image(chemin: Path):
    """L'image remise droite (photo d'iPhone prise de travers) et de taille raisonnable."""
    try:
        import Quartz
        from Foundation import NSURL, NSDictionary
    except ImportError:
        raise RecuIllisible("lecture des photos impossible ici (elle se fait avec macOS)")
    source = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(chemin)), None)
    if source is None:
        raise RecuIllisible("image illisible (format non reconnu ?)")
    options = NSDictionary.dictionaryWithDictionary_({  # un vrai dictionnaire macOS (comme pour Vision)
        Quartz.kCGImageSourceCreateThumbnailFromImageAlways: True,
        Quartz.kCGImageSourceCreateThumbnailWithTransform: True,
        Quartz.kCGImageSourceThumbnailMaxPixelSize: 3000})
    image = Quartz.CGImageSourceCreateThumbnailAtIndex(source, 0, options)
    if image is None:
        raise RecuIllisible("image illisible")
    return image


def texte_du_recu(chemin: Path) -> str:
    if chemin.suffix.lower() == ".pdf":
        from modules.coach.cours import CoursIllisible, _pdf

        try:
            texte = _pdf(chemin)
        except CoursIllisible as e:
            raise RecuIllisible(str(e))
        if len(texte.strip()) < 10:
            raise RecuIllisible("PDF sans texte (un scan ?) : envoie plutôt une photo du reçu")
        return texte
    from modules.yeux.capture import lire_texte

    try:
        lignes = lire_texte(_image(chemin))
    except RecuIllisible:
        raise
    except Exception as e:  # une erreur de macOS : le reçu est mis de côté, rien ne plante
        raise RecuIllisible(f"lecture de la photo impossible ({e})")
    if len(" ".join(lignes).strip()) < 10:
        raise RecuIllisible("presque aucun texte lu sur la photo (floue, trop sombre ?)")
    return "\n".join(lignes)
