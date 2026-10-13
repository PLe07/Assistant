"""Le banc d'essai audio (§9.2) : du son à l'intention, phrase par phrase, avec la latence ressentie.

Pour chaque échantillon du corpus audio (voix, débit, bruit) :
  détection de fin de phrase (Silero) → transcription (anticipée dès 200 ms de silence) → filtre anti-hallucination →
  compréhension → comparaison avec l'intention et les paramètres attendus.
Latence ressentie = de la vraie fin de ta parole au moment où l'intention est prête :
  attente du silence + ce qui reste de la transcription (une partie est faite pendant l'attente) + compréhension.
Transcripteurs : Whisper (mlx, sur le Mac), Apple Speech (`voix verifier`, après autorisation), ou « oracle » (le
texte exact, sans reconnaissance : mesure le détecteur de voix et la compréhension seuls, pour le conteneur).
Épreuve des hallucinations : des minutes d'audio sans parole passent par le même chemin ; rien ne doit en sortir.

    python -m outils.banc_audio [--phrases 3] [--hors 30] [--transcripteur oracle|whisper] [--minutes 10]
"""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from outils import catalogue_reference as ref
from outils import corpus_audio as ca
from outils.evaluation import params_identiques
from voix.audio import anti_hallucination
from voix.audio.vad import FinDePhrase, Silero, Vad
from voix.audio.whisper_local import Transcripteur, Transcription, invite
from voix.nlu.comprendre import Contexte, comprendre

MORCEAU = 1600  # 100 ms, comme l'app


class Oracle:
    """Une « transcription » parfaite (le texte de la phrase) et instantanée : pour mesurer le reste de la chaîne."""

    nom = "oracle"

    def __init__(self) -> None:
        self.texte = ""

    def transcrire(self, audio: np.ndarray, invite: str = "") -> Transcription:
        return Transcription(self.texte, 0.0)

    def liberer(self, maintenant: float | None = None) -> bool:
        return False


class Hallucine:
    """Le pire cas pour l'épreuve sans parole : un Whisper qui inventerait « ouvre Safari » à chaque écoute, avec
    une confiance parfaite. Seul le détecteur de voix (et la durée de parole entendue) peut alors l'arrêter."""

    nom = "hallucine"

    def transcrire(self, audio: np.ndarray, invite: str = "") -> Transcription:
        return Transcription("ouvre Safari", 0.0)

    def liberer(self, maintenant: float | None = None) -> bool:
        return False


@dataclass
class Resultat:
    phrase: str
    attendu: str | None
    obtenu: str | None
    statut: str
    juste: bool
    params_justes: bool
    latence_ms: float | None  # None : fin de phrase jamais trouvée
    transcription: str
    voix: str
    debit: int
    bruit: str
    snr_db: float | None


@dataclass
class Bilan:
    resultats: list[Resultat] = field(default_factory=list)

    def par_condition(self) -> dict[str, list[Resultat]]:
        groupes: dict[str, list[Resultat]] = defaultdict(list)
        for r in self.resultats:
            groupes["sans bruit" if r.snr_db is None else f"{r.snr_db:.0f} dB"].append(r)
        return dict(groupes)

    @staticmethod
    def resume(rs: list[Resultat]) -> dict[str, Any]:
        ordres = [r for r in rs if r.attendu is not None]
        hors = [r for r in rs if r.attendu is None]
        lat = [r.latence_ms for r in ordres if r.latence_ms is not None]
        return {
            "ordres": len(ordres),
            "intention": sum(r.juste for r in ordres) / len(ordres) if ordres else 1.0,
            "params": (sum(r.params_justes for r in ordres if r.juste) / max(1, sum(r.juste for r in ordres))),
            "hors_actions": sum(r.statut in ("compris", "ambigu") for r in hors),
            "hors": len(hors),
            "fins_manquees": sum(r.latence_ms is None for r in ordres),
            "latence_p50": float(np.percentile(lat, 50)) if lat else None,
            "latence_p90": float(np.percentile(lat, 90)) if lat else None,
        }

    def tableau(self) -> str:
        lignes = ["| Condition | Ordres | Intention | Paramètres | Hors catalogue : actions | Fin manquée | "
                  "Latence p50 | Latence p90 |", "|---|---|---|---|---|---|---|---|"]  # fmt: skip
        groupes = self.par_condition()
        for nom in sorted(groupes, key=lambda n: (n != "sans bruit", n)):
            s = self.resume(groupes[nom])
            lignes.append(
                f"| {nom} | {s['ordres']} | {100 * s['intention']:.1f} % | {100 * s['params']:.1f} % | "
                f"{s['hors_actions']} / {s['hors']} | {s['fins_manquees']} | {_ms(s['latence_p50'])} | "
                f"{_ms(s['latence_p90'])} |"
            )
        return "\n".join(lignes)


def _ms(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f} ms"


def passer(e: ca.Echantillon, vad: Vad, transcripteur: Transcripteur, ctx: Contexte, silence_fin_ms: int = 500,
           ) -> Resultat:  # fmt: skip
    """Un échantillon, en temps simulé : l'audio arrive par morceaux de 100 ms, comme depuis l'app."""
    if isinstance(transcripteur, Oracle):
        transcripteur.texte = e.cas.phrase
    f = FinDePhrase(vad, silence_fin_ms=silence_fin_ms)
    vocabulaire = invite(ctx.catalogue)
    anticipee: tuple[float, float, Transcription] | None = None  # (fin de parole, instant de lancement, résultat)
    fin = None
    audio = np.concatenate([e.audio, ca.bruit("silence", 3.0, 3)[: 3 * ca.TAUX] * ca.NIVEAU_SILENCE])
    for i in range(0, len(audio), MORCEAU):
        for ev in f.ajouter(audio[i : i + MORCEAU]):
            if ev.genre == "pause":
                anticipee = (f.fin_parole_s or 0.0, ev.instant_s, transcripteur.transcrire(f.audio(), vocabulaire))
            elif ev.genre == "fin":
                fin = ev
        if fin is not None:
            break
    if fin is None or fin.raison == "rien":
        return Resultat(e.cas.phrase, e.cas.intention, None, "fin manquée", False, False, None, "", e.voix.nom,
                        e.debit, e.bruit, e.snr_db)  # fmt: skip
    if anticipee is not None and anticipee[0] == f.fin_parole_s:
        t = anticipee[2]
        pret_s = max(fin.instant_s, anticipee[1] + t.duree_s)
    else:
        t = transcripteur.transcrire(f.audio(), vocabulaire)
        pret_s = fin.instant_s + t.duree_s
    debut_nlu = time.perf_counter()
    verdict = anti_hallucination.filtrer(t.texte, f.parole_s)
    c = comprendre(verdict.texte, ctx) if verdict.texte is not None else None
    nlu_s = time.perf_counter() - debut_nlu
    latence = (pret_s + nlu_s - e.fin_s) * 1000
    if c is None:
        return Resultat(e.cas.phrase, e.cas.intention, None, "rejeté", False, False, latence, t.texte, e.voix.nom,
                        e.debit, e.bruit, e.snr_db)  # fmt: skip
    if e.cas.statut == "refus":
        juste = c.statut == "refus"
    else:
        juste = c.statut == "compris" and c.intention == e.cas.intention
    return Resultat(e.cas.phrase, e.cas.intention, c.intention, c.statut, juste,
                    juste and params_identiques(e.cas.params, c.params), latence, t.texte, e.voix.nom, e.debit,
                    e.bruit, e.snr_db)  # fmt: skip


def banc(echantillons: Iterable[ca.Echantillon], transcripteur: Transcripteur, vad: Vad | None = None,
         suivi: Callable[[int], None] | None = None) -> Bilan:  # fmt: skip
    ctx = Contexte(ref.catalogue(), ref.commandes())
    vad = vad or Silero()
    b = Bilan()
    for i, e in enumerate(echantillons):
        b.resultats.append(passer(e, vad, transcripteur, ctx))
        if suivi is not None:
            suivi(i + 1)
    return b


@dataclass
class Hallucinations:
    morceaux: int = 0
    secondes: float = 0.0
    ecoutes_declenchees: int = 0  # le détecteur a cru entendre parler
    transcriptions: int = 0
    sorties: list[tuple[str, str]] = field(default_factory=list)  # (bruit, texte) qui seraient arrivés jusqu'à NLU


def epreuve_sans_parole(transcripteur: Transcripteur, minutes: float = 10.0, vad: Vad | None = None,
                        ecoute_s: float = 8.0) -> Hallucinations:  # fmt: skip
    """Des écoutes de 8 s sur `minutes` d'audio sans parole : tout ce qui sortirait du filtre est une hallucination."""
    vad = vad or Silero()
    h = Hallucinations()
    for genre, audio in ca.sans_parole(minutes):
        h.morceaux += 1
        h.secondes += len(audio) / ca.TAUX
        pas = int(ecoute_s * ca.TAUX)
        for debut in range(0, len(audio) - pas + 1, pas):
            f = FinDePhrase(vad)
            fin = None
            for i in range(debut, debut + pas, MORCEAU):
                evs = f.ajouter(audio[i : i + MORCEAU])
                fin = next((ev for ev in evs if ev.genre == "fin"), fin)
                if fin is not None:
                    break
            if f.parle:
                h.ecoutes_declenchees += 1
            if fin is None:
                fin = f.relacher()
            if fin.raison == "rien" or f.parole_s < anti_hallucination.PAROLE_MIN_S:
                continue
            h.transcriptions += 1
            t = transcripteur.transcrire(f.audio())
            v = anti_hallucination.filtrer(t.texte, f.parole_s)
            if v.texte is not None and not (t.sans_parole > 0.6 and t.logprob < -1.0):
                h.sorties.append((genre, v.texte))
    return h


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Banc d'essai audio de Voix")
    p.add_argument("--phrases", type=int, default=3, help="phrases par intention")
    p.add_argument("--hors", type=int, default=30, help="phrases hors catalogue")
    p.add_argument("--transcripteur", default="oracle", choices=["oracle", "whisper"])
    p.add_argument("--minutes", type=float, default=10.0, help="minutes d'audio sans parole")
    p.add_argument("--modeles", default=str(Path.home() / "Library/Application Support/Voix/modeles"))
    a = p.parse_args(argv)
    transcripteur: Transcripteur = Oracle()
    if a.transcripteur == "whisper":
        from voix.audio import whisper_local

        choix = whisper_local.charger(Path(a.modeles))
        if choix.transcripteur is None:
            print(f"Whisper indisponible : {choix.raison}")
            return 1
        transcripteur = choix.transcripteur
    voix = ca.voix_disponibles()
    cas = ca.phrases(a.phrases, a.hors)
    print(f"{len(cas)} phrases, {len(voix)} voix, {len(ca.CONDITIONS)} conditions, transcripteur {transcripteur.nom}")
    debut = time.time()
    b = banc(ca.echantillons(cas, voix), transcripteur)
    print(b.tableau())
    print(f"({time.time() - debut:.0f} s)")
    h = epreuve_sans_parole(Hallucine() if isinstance(transcripteur, Oracle) else transcripteur, a.minutes)
    print(f"Sans parole : {h.secondes / 60:.1f} min, {h.ecoutes_declenchees} écoute(s) déclenchée(s), "
          f"{h.transcriptions} transcription(s), {len(h.sorties)} hallucination(s) {h.sorties[:5]}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
