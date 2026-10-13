"""Le protocole entre l'app « Commandes Vocales » et le moteur : une ligne JSON par message (UTF-8), `"v": 1`.

App → moteur :
  {"type": "bonjour", "client": "app", "version": "1.0.0"}
  {"type": "ecoute", "etat": "debut", "id": 7, "mode": "maintien" | "appui" | "eveil"}
  {"type": "audio", "id": 7, "pcm": "<base64 : 16 bits, 16 kHz, mono, ~100 ms>"}
  {"type": "ecoute", "etat": "relache" | "annule", "id": 7}
  {"type": "texte", "id": 7, "texte": "…", "source": "apple"}      (la transcription d'Apple Speech pour l'écoute 7)
  {"type": "texte", "texte": "…", "source": "clic" | "clavier", "ref": "a1"}  (suggestion cliquée, phrase tapée ;
                                                                  `ref`, facultatif, revient dans la réponse)
  {"type": "pont", "id": 3, "ok": true, "donnees": {…}, "erreur": ""}  (la réponse à un ordre du moteur)
Moteur → app :
  {"type": "bonjour", "moteur": "1.0.0", "transcription": "whisper" | "apple", "vocabulaire": […]}
  {"type": "etat", "etat": "ecoute" | "reflexion" | "repos", "id": 7}
  {"type": "micro", "ouvert": false, "id": 7, "raison": "silence" | "duree_max" | "rien" | "relache"}
  {"type": "transcrire", "id": 7}                                 (mode Apple : donne ta transcription finale)
  {"type": "reponse", "id": 7, "ref": null, "statut": "fait", "texte": "✓ Safari ouvert", "suggestions": […],
   "choix": […]}
  {"type": "pont", "id": 3, "ordre": "app.quitter", "params": {…}}  (un ordre fermé, voir actions/pont.py)
Une ligne plus longue que 1 Mio, illisible ou d'une autre version est ignorée (et comptée).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

VERSION = 1
TAILLE_MAX_LIGNE = 1 << 20
AUDIO_MAX_OCTETS = 64_000  # 2 s de son par message au plus
TYPES_ENTRANTS = {"bonjour", "ecoute", "audio", "texte", "pont"}
ETATS_ECOUTE = {"debut", "relache", "annule"}
MODES = {"maintien", "appui", "eveil"}
SOURCES = {"apple", "clic", "clavier"}
REF = re.compile(r"[A-Za-z0-9_-]{1,40}")


class MessageInvalide(ValueError):
    pass


def encoder(message: dict[str, Any]) -> bytes:
    return (json.dumps({"v": VERSION, **message}, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def _entier(m: dict[str, Any], cle: str) -> int:
    v = m.get(cle)
    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < 2**53:
        raise MessageInvalide(f"{cle} : entier attendu")
    return v


def decoder(ligne: bytes) -> dict[str, Any]:
    """Une ligne reçue → un message vérifié, ou MessageInvalide."""
    if len(ligne) > TAILLE_MAX_LIGNE:
        raise MessageInvalide("ligne trop longue")
    try:
        m = json.loads(ligne.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise MessageInvalide("JSON illisible") from e
    if not isinstance(m, dict):
        raise MessageInvalide("objet JSON attendu")
    if m.get("v") != VERSION:
        raise MessageInvalide(f"version {m.get('v')!r} non prise en charge")
    genre = m.get("type")
    if genre not in TYPES_ENTRANTS:
        raise MessageInvalide(f"type inconnu : {genre!r}")
    if genre == "ecoute":
        _entier(m, "id")
        if m.get("etat") not in ETATS_ECOUTE:
            raise MessageInvalide("etat d'écoute inconnu")
        if m["etat"] == "debut" and m.get("mode", "appui") not in MODES:
            raise MessageInvalide("mode inconnu")
    elif genre == "audio":
        _entier(m, "id")
        m["octets"] = pcm(m.get("pcm"))
    elif genre == "texte":
        texte = m.get("texte")
        if not isinstance(texte, str) or len(texte) > 500 or "\x00" in texte:
            raise MessageInvalide("texte invalide")
        if m.get("source") not in SOURCES:
            raise MessageInvalide("source inconnue")
        if m["source"] == "apple":
            _entier(m, "id")
        ref = m.get("ref")
        if ref is not None and not (isinstance(ref, str) and REF.fullmatch(ref)):
            raise MessageInvalide("ref invalide")
    elif genre == "pont":
        _entier(m, "id")
        if not isinstance(m.get("ok"), bool):
            raise MessageInvalide("ok : vrai ou faux")
        if not isinstance(m.get("donnees", {}), dict) or not isinstance(m.get("erreur", ""), str):
            raise MessageInvalide("réponse du pont invalide")
    return m


def pcm(brut: Any) -> bytes:
    if not isinstance(brut, str) or len(brut) > AUDIO_MAX_OCTETS * 4 // 3 + 4:
        raise MessageInvalide("audio invalide")
    try:
        octets = base64.b64decode(brut, validate=True)
    except (binascii.Error, ValueError) as e:
        raise MessageInvalide("audio : base64 invalide") from e
    if len(octets) % 2:
        raise MessageInvalide("audio : nombre d'octets impair")
    return octets
