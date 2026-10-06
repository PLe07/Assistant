"""Vidéos MOV et MP4 : `ffmpeg -map_metadata -1 -c copy` (sans recompression), s'il est installé sur le Mac.
Lecture préalable avec `ffprobe` pour dire ce qui est retiré (lieu, appareil, logiciel, date)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

CLES = {"location": "position GPS", "com.apple.quicktime.location.iso6709": "position GPS",
        "com.apple.quicktime.make": "appareil", "com.apple.quicktime.model": "appareil", "make": "appareil",
        "model": "appareil", "com.apple.quicktime.software": "logiciel", "encoder": "logiciel",
        "creation_time": "date de prise de vue", "com.apple.quicktime.creationdate": "date de prise de vue",
        "artist": "auteur", "author": "auteur", "copyright": "auteur", "comment": "commentaires"}  # fmt: skip


def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def lire(chemin: Path) -> list[str]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return []
    try:
        r = subprocess.run([ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
                            str(chemin)], capture_output=True, text=True, timeout=60)  # fmt: skip
        data = json.loads(r.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    tags: dict[str, str] = dict((data.get("format") or {}).get("tags") or {})
    for flux in data.get("streams") or []:
        tags.update(flux.get("tags") or {})
    trouves: list[str] = []
    for cle in tags:
        nom = CLES.get(cle.lower())
        if nom and nom not in trouves:
            trouves.append(nom)
    return trouves


def nettoyer(chemin: Path) -> bytes:
    programme = ffmpeg()
    if not programme:
        raise RuntimeError("vidéo non nettoyée : ffmpeg n'est pas installé sur ce Mac")
    with tempfile.TemporaryDirectory(prefix="bouclier-video-") as tmp:
        sortie = Path(tmp) / f"propre{chemin.suffix.lower()}"
        commande = [programme, "-v", "error", "-nostdin", "-i", str(chemin), "-map", "0", "-map_metadata", "-1",
                    "-map_chapters", "-1", "-c", "copy", "-fflags", "+bitexact", "-flags:v", "+bitexact",
                    "-flags:a", "+bitexact", str(sortie)]  # fmt: skip
        r = subprocess.run(commande, capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not sortie.exists():
            raise RuntimeError(f"ffmpeg n'a pas pu nettoyer la vidéo : {r.stderr.strip()[:200]}")
        return sortie.read_bytes()
