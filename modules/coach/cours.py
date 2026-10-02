"""Tes cours, lus SUR TON MAC : PDF, Word, RTF, texte. Ils ne sont jamais envoyés en entier :
seul un extrait (un « morceau » d'environ une page) part à Claude pour préparer les questions du jour.

Range-les dans donnees/coach/cours/, dans le dossier de leur UE (créés pour toi) :
    cours/UE11 Contrôle de gestion/chapitre1.pdf
    cours/UE2 Droit des sociétés et des groupements d'affaires/fiches.docx
Un dossier ou un fichier dont le nom contient « UE » suivi du numéro est aussi reconnu (« DCG ue 11 »).
"""

import re
import subprocess
from pathlib import Path

from modules.coach import parametres as p

TEXTE = {".txt", ".md"}
TEXTUTIL = {".docx", ".doc", ".rtf", ".odt", ".html", ".htm"}  # lus par textutil, l'outil de macOS
A_EXPORTER = {".pages": "Pages", ".key": "Keynote", ".numbers": "Numbers"}
TAILLE_MORCEAU = 2000  # caractères : environ une page
TAILLE_MINI = 200


class CoursIllisible(Exception):
    """Le message dit quoi faire (exporter en PDF, fichier vide…)."""


def fichiers() -> list[Path]:
    if not p.COURS.exists():
        return []
    return sorted(f for f in p.COURS.rglob("*") if f.is_file() and not any(x.startswith(".") for x in f.relative_to(p.COURS).parts))


def matiere(chemin: Path) -> str | None:
    """L'UE d'un cours, d'après son dossier (ou son nom). None : on ne sait pas où le ranger."""
    parties = chemin.relative_to(p.COURS).parts
    return p.ue_de(parties[0]) or (p.ue_de(chemin.name) if len(parties) > 1 else None)


def creer_dossiers() -> None:
    """Un dossier par UE (ceux qui manquent seulement : rien n'est jamais déplacé ni effacé)."""
    p.COURS.mkdir(parents=True, exist_ok=True)
    deja = {p.ue_de(d.name) for d in p.COURS.iterdir() if d.is_dir()}
    for ue in p.UE:
        if ue not in deja:
            (p.COURS / ue).mkdir(exist_ok=True)


def _pdf(chemin: Path) -> str:
    try:
        from Foundation import NSURL
        from Quartz import PDFDocument
    except ImportError:
        raise CoursIllisible("lecture des PDF impossible ici (elle se fait avec macOS)")
    document = PDFDocument.alloc().initWithURL_(NSURL.fileURLWithPath_(str(chemin)))
    if document is None:
        raise CoursIllisible("PDF illisible (protégé par un mot de passe ou abîmé ?)")
    return str(document.string() or "")


def lire_texte(chemin: Path) -> str:
    ext = chemin.suffix.lower()
    if ext in A_EXPORTER:
        raise CoursIllisible(f"fichier {A_EXPORTER[ext]} : ouvre-le, puis Fichier → Exporter vers → Word ou PDF")
    if ext in TEXTE:
        texte = chemin.read_text(encoding="utf-8", errors="replace")
    elif ext == ".pdf":
        texte = _pdf(chemin)
    elif ext in TEXTUTIL:
        try:
            r = subprocess.run(["textutil", "-convert", "txt", "-stdout", "--", str(chemin)],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise CoursIllisible(f"lecture impossible ({e})")
        if r.returncode != 0:
            raise CoursIllisible(f"lecture impossible ({(r.stderr or '').strip()[:120]})")
        texte = r.stdout
    else:
        raise CoursIllisible("format non lu (PDF, Word, RTF ou texte attendus)")
    if len(texte.strip()) < TAILLE_MINI:
        raise CoursIllisible("presque pas de texte (un PDF scanné ? exporte-le avec du texte, ou en Word)")
    return texte


def decouper(texte: str) -> list[str]:
    """Des morceaux d'environ une page, coupés entre deux paragraphes."""
    paragraphes = [" ".join(x.split()) for x in re.split(r"\n\s*\n|\f", texte) if x.strip()]
    morceaux, courant = [], ""
    for para in paragraphes:
        while len(para) > TAILLE_MORCEAU:  # un paragraphe géant (PDF sans sauts de ligne) : coupé net
            if courant:
                morceaux.append(courant)
                courant = ""
            morceaux.append(para[:TAILLE_MORCEAU])
            para = para[TAILLE_MORCEAU:]
        if courant and len(courant) + len(para) + 1 > TAILLE_MORCEAU:
            morceaux.append(courant)
            courant = ""
        courant = f"{courant}\n{para}".strip()
    if courant:
        morceaux.append(courant)
    return [m for m in morceaux if len(m) >= TAILLE_MINI]
