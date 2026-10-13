"""Le corpus audio (§9.2), entièrement automatique et **en mémoire** : rien n'est gardé sur le disque.

- Phrases : pour chaque intention, des tournures orales des jeux écrits à la main (jeux 3 et 6), plus des phrases
  hors catalogue (qui ne doivent rien déclencher).
- Voix : `say` sur le Mac (toutes les voix françaises), espeak-ng + MBROLA fr1 à fr7 dans le conteneur de construction
  (D-06). Trois débits. Chaque phrase reçoit une voix et un débit à tour de rôle : toutes les combinaisons sont
  couvertes à parts égales.
- Bruits générés (graine fixe) : café (brouhaha de voix lointaines et tintements), clavier, rue ; mélangés à 20 et
  10 dB de rapport signal/bruit. Pour l'épreuve des hallucinations : silence, souffle, clavier, rue, ventilateur,
  sans aucune parole.
- 16 kHz mono, flottants. `say` écrit forcément un fichier : il est lu puis effacé aussitôt (dossier temporaire).
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from outils import corpus_phrases_3, corpus_phrases_6
from outils.corpus_phrases import Cas

TAUX = 16_000
GRAINE = 20261013
DEBITS = {"say": (150, 185, 220), "espeak": (130, 160, 190)}  # mots par minute : lent, normal, rapide
MBROLA = Path("/usr/share/mbrola")
NIVEAU_SILENCE = 3e-4  # environ -70 dB : le souffle d'un micro dans une pièce calme, jamais un zéro parfait


@dataclass(frozen=True)
class Voix:
    moteur: str  # say, espeak
    nom: str


@dataclass
class Echantillon:
    cas: Cas
    voix: Voix
    debit: int
    bruit: str  # aucun, cafe, clavier, rue
    snr_db: float | None
    audio: np.ndarray
    debut_s: float  # où commence et finit la parole dans `audio`
    fin_s: float
    infos: dict[str, Any] = field(default_factory=dict)


# --- les voix -------------------------------------------------------------------------------------------------------


def voix_say(sortie: str) -> list[Voix]:
    """Les voix françaises de `say -v '?'` (« Thomas  fr_FR  # Bonjour… », « Amélie (Premium)  fr_CA  # … »)."""
    voix = []
    for ligne in sortie.splitlines():
        m = re.match(r"^(.+?)\s+(fr_[A-Z]{2})\s+#", ligne)
        if m:
            voix.append(Voix("say", m.group(1).strip()))
    return voix


def voix_disponibles() -> list[Voix]:
    if shutil.which("say"):
        proc = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=30, check=False)
        trouvees = voix_say(proc.stdout)
        if trouvees:
            return trouvees
    if shutil.which("espeak-ng"):
        mbrola = [Voix("espeak", f"mb-fr{i}") for i in range(1, 8) if (MBROLA / f"fr{i}").exists()]
        return mbrola or [Voix("espeak", "fr")]
    return []


def lire_wav(donnees: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(donnees)) as w:
        taux, largeur, canaux = w.getframerate(), w.getsampwidth(), w.getnchannels()
        brut = w.readframes(w.getnframes())
    if largeur != 2:
        raise ValueError("WAV 16 bits attendu")
    x = np.frombuffer(brut, dtype="<i2").astype(np.float32) / 32768.0
    if canaux > 1:
        x = x.reshape(-1, canaux).mean(axis=1)
    return reechantillonner(x, taux)


def reechantillonner(x: np.ndarray, taux: int) -> np.ndarray:
    if taux == TAUX or len(x) == 0:
        return x.astype(np.float32)
    t = np.arange(0, len(x) / taux, 1 / TAUX)
    return np.interp(t, np.arange(len(x)) / taux, x).astype(np.float32)


def synthetiser(texte: str, voix: Voix, debit: int) -> np.ndarray:
    """La phrase dite par cette voix, en mémoire (16 kHz mono)."""
    if voix.moteur == "espeak":
        sortie = subprocess.run(["espeak-ng", "-v", voix.nom, "-s", str(debit), "--stdout", texte],
                                capture_output=True, timeout=60, check=True).stdout  # fmt: skip
        return lire_wav(sortie)
    with tempfile.TemporaryDirectory(prefix="voix-corpus-") as d:
        fichier = Path(d) / "phrase.wav"
        subprocess.run(["say", "-v", voix.nom, "-r", str(debit), "-o", str(fichier), "--file-format=WAVE",
                        "--data-format=LEI16@16000", texte], capture_output=True, timeout=60, check=True)  # fmt: skip
        donnees = fichier.read_bytes()
        fichier.unlink()
    return lire_wav(donnees)


def bornes_parole(x: np.ndarray, seuil: float = 0.01) -> tuple[float, float]:
    """Début et fin de la parole dans un enregistrement propre (énergie au-dessus d'un seuil)."""
    idx = np.nonzero(np.abs(x) > seuil)[0]
    if len(idx) == 0:
        return 0.0, 0.0
    return idx[0] / TAUX, (idx[-1] + 1) / TAUX


# --- les bruits -----------------------------------------------------------------------------------------------------


def _filtre_passe_bas(x: np.ndarray, coupure_hz: float) -> np.ndarray:
    spectre = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / TAUX)
    spectre[f > coupure_hz] *= np.exp(-((f[f > coupure_hz] - coupure_hz) / 500.0))  # une pente douce
    return np.fft.irfft(spectre, len(x)).astype(np.float32)


def _rose(n: int, r: np.random.Generator) -> np.ndarray:
    spectre = np.fft.rfft(r.standard_normal(n))
    f = np.arange(len(spectre))
    f[0] = 1
    x = np.fft.irfft(spectre / np.sqrt(f), n)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def _brun(n: int, r: np.random.Generator) -> np.ndarray:
    spectre = np.fft.rfft(r.standard_normal(n))
    f = np.arange(len(spectre)).astype(np.float64)
    f[0] = 1
    x = np.fft.irfft(spectre / f, n)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def _clics(n: int, r: np.random.Generator, ecart_s: tuple[float, float] = (0.08, 0.25)) -> np.ndarray:
    x = np.zeros(n, dtype=np.float32)
    t = int(r.uniform(0, 0.2) * TAUX)
    duree = int(0.006 * TAUX)
    enveloppe = np.exp(-np.linspace(0, 6, duree)).astype(np.float32)
    while t + duree < n:
        x[t : t + duree] += r.standard_normal(duree).astype(np.float32) * enveloppe * r.uniform(0.4, 1.0)
        t += int(r.uniform(*ecart_s) * TAUX)
    return x


def _tintements(n: int, r: np.random.Generator) -> np.ndarray:
    x = np.zeros(n, dtype=np.float32)
    for _ in range(max(1, n // (TAUX * 2))):
        debut = int(r.uniform(0, max(1, n - TAUX // 2)))
        duree = min(TAUX // 2, n - debut)
        t = np.arange(duree) / TAUX
        f = r.uniform(2500, 5000)
        x[debut : debut + duree] += (np.sin(2 * np.pi * f * t) * np.exp(-t * 12) * r.uniform(0.2, 0.6)).astype(
            np.float32
        )
    return x


_BROUHAHA: dict[int, np.ndarray] = {}
TEXTES_BROUHAHA = [
    "alors je lui ai dit que ce n'était pas possible avant la semaine prochaine",
    "tu veux un autre café ou on y va tout de suite",
    "il paraît que le restaurant d'en face a fermé depuis le printemps",
    "on se retrouve devant la gare vers six heures et demie",
    "elle a encore oublié ses clés chez sa sœur ce matin",
    "je crois qu'il va pleuvoir tout le week-end de toute façon",
]


def _brouhaha(n: int, r: np.random.Generator, voix: list[Voix]) -> np.ndarray:
    """Des conversations lointaines : phrases synthétisées, superposées, étouffées."""
    cle = len(voix)
    if cle not in _BROUHAHA:
        morceaux = []
        for i, texte in enumerate(TEXTES_BROUHAHA):
            v = voix[i % len(voix)]
            morceaux.append(synthetiser(texte, v, DEBITS[v.moteur][1]))
        _BROUHAHA[cle] = np.concatenate(morceaux)
    source = _BROUHAHA[cle]
    x = np.zeros(n, dtype=np.float32)
    for _ in range(4):
        debut = int(r.uniform(0, len(source)))
        piste = np.roll(source, -debut)
        piste = np.tile(piste, n // len(piste) + 1)[:n]
        x += piste * r.uniform(0.5, 1.0)
    return _filtre_passe_bas(x, 2500)


def bruit(genre: str, duree_s: float, graine: int, voix: list[Voix] | None = None) -> np.ndarray:
    """Un bruit de `duree_s` secondes, normalisé (crête à 1), reproductible."""
    n = int(duree_s * TAUX)
    r = np.random.default_rng(graine)
    if genre == "cafe":
        x = _brouhaha(n, r, voix or []) if voix else _rose(n, r)
        x = x / (np.abs(x).max() + 1e-9) + 0.5 * _tintements(n, r) + 0.15 * _rose(n, r)
    elif genre == "clavier":
        x = _clics(n, r) + 0.05 * _rose(n, r)
    elif genre == "rue":
        voitures = np.zeros(n, dtype=np.float32)
        for _ in range(max(1, int(duree_s / 4))):
            centre = r.uniform(0, duree_s)
            t = np.arange(n) / TAUX
            voitures += np.exp(-(((t - centre) / r.uniform(0.8, 2.0)) ** 2)).astype(np.float32)
        x = _brun(n, r) * (0.4 + voitures) + 0.2 * _rose(n, r)
    elif genre == "ventilateur":
        t = np.arange(n) / TAUX
        x = 0.6 * _rose(n, r) + 0.3 * np.sin(2 * np.pi * 120 * t).astype(np.float32)
    elif genre == "souffle":
        x = _rose(n, r)
    elif genre == "silence":
        x = r.standard_normal(n).astype(np.float32)  # une pièce calme (à multiplier par NIVEAU_SILENCE)
    else:
        raise ValueError(f"bruit inconnu : {genre}")
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if len(x) else 0.0


def melanger(parole: np.ndarray, debut_s: float, fin_s: float, bruit_: np.ndarray, snr_db: float) -> np.ndarray:
    """La parole + le bruit, au rapport signal/bruit voulu (mesuré sur la partie parlée)."""
    voisee = parole[int(debut_s * TAUX) : int(fin_s * TAUX)]
    cible = rms(voisee) / (10 ** (snr_db / 20))
    b = bruit_[: len(parole)]
    b = b * (cible / (rms(b) + 1e-12))
    x = parole + b
    crete = np.abs(x).max()
    return (x / crete * 0.9 if crete > 0.99 else x).astype(np.float32)


# --- les phrases et le corpus ----------------------------------------------------------------------------------------


def phrases(par_intention: int = 3, hors: int = 30) -> list[Cas]:
    """Les phrases du corpus audio : tournures orales écrites à la main, `par_intention` au plus par intention."""
    vus: dict[str | None, int] = {}
    choisies: list[Cas] = []
    for c in [*corpus_phrases_3.generer(), *corpus_phrases_6.generer()]:
        if c.intention is None or vus.get(c.intention, 0) >= par_intention:
            continue
        if not re.fullmatch(r"[\w\s'’,.?!àâäçéèêëîïôöùûüÿœæ-]+", c.phrase, flags=re.IGNORECASE):
            continue  # des symboles qu'une voix lirait mal (« ; », « $ ») : pas pour l'oral
        vus[c.intention] = vus.get(c.intention, 0) + 1
        choisies.append(c)
    hc = [c for c in corpus_phrases_3.hors_catalogue() + corpus_phrases_6.hors_catalogue()][:hors]
    return choisies + hc


CONDITIONS: list[tuple[str, float | None]] = [("aucun", None), ("cafe", 20.0), ("clavier", 20.0), ("rue", 20.0),
                                              ("cafe", 10.0), ("clavier", 10.0), ("rue", 10.0)]  # fmt: skip


def echantillons(
    cas: list[Cas], voix: list[Voix], conditions: list[tuple[str, float | None]] | None = None,
    avant_s: float = 0.4, apres_s: float = 1.2,
) -> Iterator[Echantillon]:  # fmt: skip
    """Chaque phrase, dite par une voix et un débit à tour de rôle, dans chaque condition de bruit."""
    if not voix:
        raise RuntimeError("aucune voix française (say ou espeak-ng)")
    conditions = conditions if conditions is not None else CONDITIONS
    combinaisons = [(v, d) for v in voix for d in DEBITS[v.moteur]]
    for i, c in enumerate(cas):
        v, d = combinaisons[i % len(combinaisons)]
        propre = synthetiser(c.phrase, v, d)
        debut, fin = bornes_parole(propre)
        parole = np.concatenate([np.zeros(int(avant_s * TAUX), np.float32), propre,
                                 np.zeros(int(apres_s * TAUX), np.float32)])  # fmt: skip
        debut, fin = debut + avant_s, fin + avant_s
        for j, (genre, snr) in enumerate(conditions):
            if genre == "aucun" or snr is None:
                audio = parole + bruit("silence", len(parole) / TAUX, GRAINE + i)[: len(parole)] * NIVEAU_SILENCE
            else:
                b = bruit(genre, len(parole) / TAUX + 0.1, GRAINE + 1000 * j + i, voix)
                audio = melanger(parole, debut, fin, b, snr)
            yield Echantillon(c, v, d, genre, snr, audio.astype(np.float32), debut, fin)


SANS_PAROLE = ["silence", "souffle", "clavier", "rue", "ventilateur"]


def sans_parole(minutes: float = 10.0, morceau_s: float = 30.0) -> Iterator[tuple[str, np.ndarray]]:
    """`minutes` d'audio sans aucune parole (silence et bruits), en morceaux de 30 s : l'épreuve des hallucinations."""
    n = int(minutes * 60 / morceau_s)
    for i in range(n):
        genre = SANS_PAROLE[i % len(SANS_PAROLE)]
        niveau = NIVEAU_SILENCE if genre == "silence" else [0.01, 0.05, 0.15][i % 3]
        yield genre, bruit(genre, morceau_s, GRAINE + 7 * i) * niveau
