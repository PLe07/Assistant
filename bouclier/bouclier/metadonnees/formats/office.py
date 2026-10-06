"""Word, Excel, PowerPoint (.docx, .xlsx, .pptx) : des archives zip. On vide `docProps/core.xml` (auteur, dernier
modificateur, dates, titre, mots-clés), on retire de `docProps/app.xml` l'entreprise, le responsable, le modèle et
le temps d'édition, on vide `docProps/custom.xml`. Le reste de l'archive est recopié tel quel.

Les commentaires et les révisions suivies contiennent aussi des noms : ils ne sont pas retirés (ce serait modifier
le contenu) mais **signalés**."""

from __future__ import annotations

import io
import re
import zipfile

CORE_VIDE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
)
CUSTOM_VIDE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
)
_APP_RETIRES = ("Company", "Manager", "Template", "TotalTime", "HyperlinkBase")
_CORE_CHAMPS = {"creator": "auteur", "lastModifiedBy": "dernier modificateur", "created": "dates",
                "modified": "dates", "title": "titre", "subject": "sujet", "keywords": "mots-clés",
                "description": "description", "category": "catégorie", "lastPrinted": "dates"}  # fmt: skip
_COMMENTAIRES = re.compile(r"^(word/(comments|people|commentsExtended)\w*\.xml|xl/(comments\d*|threadedComments/.*|"
                           r"persons/person)\.xml|ppt/(comments/.*|commentAuthors)\.xml)$")  # fmt: skip


def _valeur(xml: str, balise: str) -> bool:
    return re.search(rf"<(\w+:)?{balise}\b[^>]*>\s*[^<\s][^<]*</(\w+:)?{balise}>", xml) is not None


def lire(donnees: bytes) -> tuple[list[str], list[str]]:
    """(métadonnées présentes, avertissements : commentaires et révisions)."""
    trouves: list[str] = []
    avertissements: list[str] = []
    with zipfile.ZipFile(io.BytesIO(donnees)) as z:
        noms = z.namelist()
        if "docProps/core.xml" in noms:
            core = z.read("docProps/core.xml").decode("utf-8", "replace")
            for balise, nom in _CORE_CHAMPS.items():
                if _valeur(core, balise) and nom not in trouves:
                    trouves.append(nom)
        if "docProps/app.xml" in noms:
            app = z.read("docProps/app.xml").decode("utf-8", "replace")
            if _valeur(app, "Company"):
                trouves.append("entreprise")
            if _valeur(app, "Manager"):
                trouves.append("responsable")
        if "docProps/custom.xml" in noms and "<property" in z.read("docProps/custom.xml").decode("utf-8", "replace"):
            trouves.append("propriétés personnalisées")
        if any(_COMMENTAIRES.match(n) for n in noms):
            avertissements.append(
                "le document contient des commentaires (avec les noms de leurs auteurs) : supprime-les dans"
                " l'application avant d'envoyer"
            )
        document = z.read("word/document.xml").decode("utf-8", "replace") if "word/document.xml" in noms else ""
        if re.search(r"<w:(ins|del)\b[^>]*w:author=", document):
            avertissements.append(
                "le document contient des modifications suivies (avec les noms de leurs auteurs) : accepte-les ou"
                " refuse-les avant d'envoyer"
            )
    return trouves, avertissements


def nettoyer(donnees: bytes) -> bytes:
    sortie = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(donnees)) as entree, zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entree.infolist():
            contenu = entree.read(info.filename)
            if info.filename == "docProps/core.xml":
                contenu = CORE_VIDE.encode()
            elif info.filename == "docProps/custom.xml":
                contenu = CUSTOM_VIDE.encode()
            elif info.filename == "docProps/app.xml":
                texte = contenu.decode("utf-8", "replace")
                for balise in _APP_RETIRES:
                    texte = re.sub(rf"<{balise}\b[^>]*>.*?</{balise}>|<{balise}\b[^>]*/>", "", texte, flags=re.S)
                contenu = texte.encode("utf-8")
            nouvelle = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            nouvelle.compress_type = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            nouvelle.external_attr = info.external_attr
            z.writestr(nouvelle, contenu)
    return sortie.getvalue()
