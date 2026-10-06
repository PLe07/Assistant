"""Les autres formats : .docx (un zip de XML), texte, courriel .eml (texte et pièces jointes), liens (.url, .webloc,
un texte qui n'est qu'une adresse web)."""

from __future__ import annotations

import html
import plistlib
import re
import zipfile
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path

LIEN = re.compile(r"^\s*(https?://\S+)\s*$", re.IGNORECASE)


TAILLE_MAX_XML = 50_000_000  # un .docx dont le texte décompressé dépasse 50 Mo est refusé (archive piégée)


def docx(chemin: Path) -> str:
    with zipfile.ZipFile(chemin) as z:
        if z.getinfo("word/document.xml").file_size > TAILLE_MAX_XML:
            raise ValueError("document.xml trop gros")
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    paragraphes = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        morceaux = re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", p, flags=re.S)
        texte = html.unescape("".join(morceaux)).strip()
        if texte:
            paragraphes.append(texte)
    return "\n".join(paragraphes)


def texte(chemin: Path) -> str:
    donnees = chemin.read_bytes()
    for codage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return donnees.decode(codage)
        except UnicodeDecodeError:
            continue
    return donnees.decode("utf-8", "replace")


def lien(chemin: Path) -> str | None:
    """L'adresse d'un raccourci web (.url de Windows, .webloc du Mac) ou d'un texte qui n'est qu'une adresse."""
    suffixe = chemin.suffix.lower()
    try:
        if suffixe == ".webloc":
            return str(plistlib.loads(chemin.read_bytes()).get("URL") or "") or None
        contenu = texte(chemin)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    if suffixe == ".url":
        m = re.search(r"^URL=(\S+)", contenu, flags=re.M)
        return m.group(1) if m else (LIEN.match(contenu).group(1) if LIEN.match(contenu) else None)  # type: ignore[union-attr]
    m = LIEN.match(contenu)
    return m.group(1) if m else None


@dataclass
class Courriel:
    sujet: str
    expediteur: str
    corps: str
    pieces: list[tuple[str, bytes]] = field(default_factory=list)


def courriel(chemin: Path) -> Courriel:
    with chemin.open("rb") as f:
        message = BytesParser(policy=policy.default).parse(f)
    corps = message.get_body(preferencelist=("plain", "html"))
    contenu = corps.get_content() if corps is not None else ""
    if corps is not None and corps.get_content_type() == "text/html":
        contenu = html.unescape(re.sub(r"<[^>]+>", " ", contenu))
    pieces = []
    for partie in message.iter_attachments():
        nom = partie.get_filename()
        donnees = partie.get_payload(decode=True)
        if nom:
            pieces.append((Path(nom).name, donnees if isinstance(donnees, bytes) else b""))
    return Courriel(str(message.get("Subject", "")), str(message.get("From", "")), str(contenu), pieces)
