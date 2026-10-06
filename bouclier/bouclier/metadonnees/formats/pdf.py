"""PDF (pikepdf) : le dictionnaire d'informations (auteur, logiciel, titre, dates…), les métadonnées XMP du
document et des pages, les informations privées des logiciels (PieceInfo) et le nom des auteurs d'annotations."""

from __future__ import annotations

import io

import pikepdf

CHAMPS = {"/Author": "auteur", "/Creator": "logiciel", "/Producer": "logiciel", "/Title": "titre",
          "/Subject": "sujet", "/Keywords": "mots-clés", "/CreationDate": "dates", "/ModDate": "dates"}  # fmt: skip


def lire(donnees: bytes) -> list[str]:
    trouves: list[str] = []
    with pikepdf.open(io.BytesIO(donnees)) as pdf:
        for cle, nom in CHAMPS.items():
            if cle in pdf.docinfo and str(pdf.docinfo[cle]).strip() and nom not in trouves:
                trouves.append(nom)
        if "/Metadata" in pdf.Root:
            trouves.append("données XMP")
        if any("/T" in a for page in pdf.pages for a in page.get("/Annots", [])):
            trouves.append("auteurs des annotations")
    return trouves


def nettoyer(donnees: bytes) -> bytes:
    with pikepdf.open(io.BytesIO(donnees)) as pdf:
        for cle in list(pdf.docinfo.keys()):
            del pdf.docinfo[cle]
        if "/Info" in pdf.trailer:
            del pdf.trailer["/Info"]
        for cle in ("/Metadata", "/PieceInfo"):
            if cle in pdf.Root:
                del pdf.Root[cle]
        for page in pdf.pages:
            for cle in ("/Metadata", "/PieceInfo"):
                if cle in page.obj:
                    del page.obj[cle]
            for annotation in page.get("/Annots", []):
                for cle in ("/T", "/M", "/CreationDate"):
                    if cle in annotation:
                        del annotation[cle]
        sortie = io.BytesIO()
        pdf.remove_unreferenced_resources()
        pdf.save(sortie, fix_metadata_version=False, deterministic_id=True)
    return sortie.getvalue()
