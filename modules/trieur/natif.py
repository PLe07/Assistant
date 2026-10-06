"""Tout ce qui parle directement à macOS par PyObjC, isolé ici (D-04) :
- Vision : le texte d'une image, avec la position de chaque ligne (VNRecognizeTextRequest) ;
- Vision : les quatre coins d'un document photographié (VNDetectDocumentSegmentationRequest) ;
- Finder : les tags d'un fichier, et un vrai alias (un « signet » qui suit le fichier s'il est déplacé).

Ce fichier n'est pas compté dans la couverture des tests du conteneur : il est vérifié sur ton Mac par
tests/trieur/e2e_mac. Ailleurs que sur macOS, chaque fonction échoue proprement (exception ou False).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from modules.trieur.extraction.ocr import Morceau, OCRImpossible


def vision_disponible() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import Vision  # noqa: F401
    except ImportError:
        return False
    return True


def _gestionnaire(image: Path) -> Any:
    import Vision
    from Foundation import NSURL, NSDictionary

    # Un vrai dictionnaire macOS, vide : un {} de Python fait planter Vision avec PyObjC 12.2 (comme pour les yeux).
    return Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(image)),
                                                                     NSDictionary.dictionary())  # fmt: skip


class Vision:
    nom = "vision"

    def lire(self, image: Path) -> list[Morceau]:
        import Vision as V

        requete = V.VNRecognizeTextRequest.alloc().init()
        requete.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate)
        requete.setUsesLanguageCorrection_(True)
        try:
            requete.setRecognitionLanguages_(["fr-FR", "en-US"])
        except Exception:
            pass
        ok, erreur = _gestionnaire(image).performRequests_error_([requete], None)
        if not ok:
            raise OCRImpossible(f"Vision : {erreur}")
        morceaux = []
        for observation in requete.results() or []:
            candidats = observation.topCandidates_(1)
            if not candidats or not len(candidats):
                continue
            cadre = observation.boundingBox()  # origine en bas à gauche, de 0 à 1
            haut = 1.0 - (cadre.origin.y + cadre.size.height)
            g, d = observation.topLeft(), observation.topRight()
            pente = -(d.y - g.y) / (d.x - g.x) if d.x - g.x > 1e-3 else 0.0  # l'axe y de Vision monte
            morceaux.append(Morceau(str(candidats[0].string()), float(cadre.origin.x), float(haut),
                                    float(cadre.size.width), float(cadre.size.height),
                                    float(candidats[0].confidence()), float(pente)))  # fmt: skip
        return morceaux


def coins_du_document(image: Path) -> list[tuple[float, float]] | None:
    """Les quatre coins (haut-gauche, haut-droit, bas-droit, bas-gauche ; de 0 à 1, origine en haut) du document
    photographié, ou None."""
    import Vision as V

    requete = V.VNDetectDocumentSegmentationRequest.alloc().init()
    ok, _ = _gestionnaire(image).performRequests_error_([requete], None)
    resultats = requete.results() if ok else None
    if not resultats:
        return None
    o = resultats[0]
    if float(o.confidence()) < 0.6:
        return None
    return [(float(p.x), 1.0 - float(p.y)) for p in (o.topLeft(), o.topRight(), o.bottomRight(), o.bottomLeft())]


def poser_tags(chemin: Path, tags: list[str]) -> bool:
    from Foundation import NSURL, NSURLTagNamesKey

    url = NSURL.fileURLWithPath_(str(chemin))
    ok, _ = url.setResourceValue_forKey_error_(list(tags), NSURLTagNamesKey, None)
    return bool(ok)


def lire_tags(chemin: Path) -> list[str]:
    from Foundation import NSURL, NSURLTagNamesKey

    ok, valeur, _ = NSURL.fileURLWithPath_(str(chemin)).getResourceValue_forKey_error_(None, NSURLTagNamesKey, None)
    return [str(t) for t in (valeur or [])] if ok else []


def creer_alias(cible: Path, alias: Path) -> bool:
    """Un alias du Finder (fichier signet) : il retrouve la facture même si tu la déplaces."""
    from Foundation import NSURL

    adaptee = 1 << 10  # NSURLBookmarkCreationSuitableForBookmarkFile
    donnees, erreur = NSURL.fileURLWithPath_(
        str(cible)
    ).bookmarkDataWithOptions_includingResourceValuesForKeys_relativeToURL_error_(adaptee, None, None, None)
    if donnees is None:
        return False
    ok, _ = NSURL.writeBookmarkData_toURL_options_error_(donnees, NSURL.fileURLWithPath_(str(alias)), adaptee, None)
    return bool(ok)
