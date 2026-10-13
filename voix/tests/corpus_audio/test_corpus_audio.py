"""Le corpus audio et le banc d'essai (§9.2).

Par défaut (rapide) : le corpus se fabrique en mémoire, de façon reproductible, au bon rapport signal/bruit ; le banc
tourne sur quelques phrases. Avec `./check.sh --complet` : tout le corpus (toutes les voix, 3 débits, 7 conditions)
et 10 minutes sans parole. Whisper lui-même ne tourne que sur le Mac (marqueur `mac`, rejoué par `voix verifier`).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from outils import banc_audio as ba
from outils import corpus_audio as ca
from voix.nlu.intentions import INTENTIONS

VOIX = ca.voix_disponibles()
pytestmark = pytest.mark.skipif(not VOIX, reason="aucune voix française (say ou espeak-ng) sur cette machine")


def test_les_phrases_couvrent_les_intentions() -> None:
    cas = ca.phrases()
    intentions = {c.intention for c in cas if c.intention}
    assert len(intentions) >= 0.9 * len(INTENTIONS), sorted(set(INTENTIONS) - intentions)
    assert sum(c.intention is None for c in cas) == 30 and len(cas) >= 200
    assert all(";" not in c.phrase and "$" not in c.phrase for c in cas)


def test_voix_du_mac_lues_dans_say() -> None:
    sortie = ("Amélie              fr_CA    # Bonjour, je m'appelle Amélie.\n"
              "Thomas              fr_FR    # Bonjour, je m'appelle Thomas.\n"
              "Audrey (Premium)    fr_FR    # Bonjour, je m'appelle Audrey.\n"
              "Samantha            en_US    # Hello, my name is Samantha.\n")  # fmt: skip
    assert [v.nom for v in ca.voix_say(sortie)] == ["Amélie", "Thomas", "Audrey (Premium)"]


def test_bruits_reproductibles_et_rapport_signal_bruit() -> None:
    for genre in ("cafe", "clavier", "rue", "ventilateur", "souffle", "silence"):
        a = ca.bruit(genre, 1.0, 7, VOIX)
        assert len(a) == ca.TAUX and np.array_equal(a, ca.bruit(genre, 1.0, 7, VOIX)) and np.abs(a).max() <= 1.0
    with pytest.raises(ValueError):
        ca.bruit("tonnerre", 1.0, 1)
    parole = ca.synthetiser("ouvre Safari", VOIX[0], ca.DEBITS[VOIX[0].moteur][1])
    debut, fin = ca.bornes_parole(parole)
    for snr in (20.0, 10.0):
        b = ca.bruit("rue", len(parole) / ca.TAUX + 0.1, 3)
        x = ca.melanger(parole, debut, fin, b, snr)
        n = x - parole
        voisee = slice(int(debut * ca.TAUX), int(fin * ca.TAUX))
        mesure = 20 * np.log10(ca.rms(parole[voisee]) / ca.rms(n[: len(parole)]))
        assert abs(mesure - snr) < 1.0, mesure
    assert ca.bornes_parole(np.zeros(100, np.float32)) == (0.0, 0.0) and ca.rms(np.zeros(0)) == 0.0


def test_corpus_en_memoire_aucun_fichier_laisse() -> None:
    avant = set(Path(tempfile.gettempdir()).glob("voix-corpus-*"))
    cas = ca.phrases()[:2]
    ech = list(ca.echantillons(cas, VOIX, [("aucun", None), ("cafe", 10.0)]))
    assert len(ech) == 4 and {e.bruit for e in ech} == {"aucun", "cafe"}
    assert all(e.audio.dtype == np.float32 and 0.3 < e.debut_s < e.fin_s for e in ech)
    assert ech[0].voix != ech[2].voix or ech[0].debit != ech[2].debit  # voix et débits à tour de rôle
    assert set(Path(tempfile.gettempdir()).glob("voix-corpus-*")) == avant
    with pytest.raises(RuntimeError):
        list(ca.echantillons(cas, []))
    morceaux = list(ca.sans_parole(minutes=1.0))
    assert len(morceaux) == 2 and all(len(a) == 30 * ca.TAUX for _, a in morceaux)


def test_le_banc_sur_quelques_phrases() -> None:
    cas = [c for c in ca.phrases() if c.intention][:4] + ca.phrases(0, 2)
    b = ba.banc(ca.echantillons(cas, VOIX, [("aucun", None), ("rue", 20.0)]), ba.Oracle())
    s = b.resume(b.resultats)
    assert s["ordres"] == 8 and s["intention"] == 1.0 and s["params"] == 1.0 and s["fins_manquees"] == 0
    assert s["hors"] == 4 and s["hors_actions"] == 0
    assert s["latence_p90"] is not None and s["latence_p90"] < 800
    assert "| sans bruit | 4 |" in b.tableau() and "| 20 dB | 4 |" in b.tableau()


def test_l_epreuve_sans_parole_attrape_un_whisper_qui_invente() -> None:
    """Un faux Whisper qui invente « ouvre Safari » à chaque écoute : sur du bruit sans parole, rien ne passe."""
    h = ba.epreuve_sans_parole(ba.Hallucine(), minutes=1.0)
    assert h.secondes == 60.0 and h.sorties == []


@pytest.mark.complet
def test_corpus_audio_complet_sans_whisper() -> None:
    """Tout le corpus, transcription parfaite : ce que valent le détecteur de voix et la compréhension seuls."""
    b = ba.banc(ca.echantillons(ca.phrases(), VOIX), ba.Oracle())
    print("\n" + b.tableau())
    for nom, rs in b.par_condition().items():
        s = b.resume(rs)
        assert s["intention"] >= 0.99 and s["hors_actions"] == 0, (nom, s)
        assert s["fins_manquees"] == 0, (nom, s)
    tout = b.resume(b.resultats)
    assert tout["latence_p90"] is not None and tout["latence_p90"] <= 800, tout


@pytest.mark.complet
def test_dix_minutes_sans_parole_zero_hallucination() -> None:
    h = ba.epreuve_sans_parole(ba.Hallucine(), minutes=10.0)
    print(f"\n{h.secondes / 60:.0f} min sans parole : {h.ecoutes_declenchees} écoute(s) déclenchée(s), "
          f"{h.transcriptions} transcription(s), {len(h.sorties)} hallucination(s)")  # fmt: skip
    assert h.secondes >= 600 and h.sorties == []


@pytest.mark.complet
@pytest.mark.mac
def test_corpus_audio_whisper() -> None:
    """Les critères de §9.2 avec le vrai Whisper (Mac Apple Silicon, modèle installé)."""
    from voix.audio import whisper_local

    choix = whisper_local.charger(Path.home() / "Library/Application Support/Voix/modeles")
    if choix.transcripteur is None:
        pytest.skip(f"Whisper indisponible ici : {choix.raison}")
    b = ba.banc(ca.echantillons(ca.phrases(), VOIX), choix.transcripteur)
    print("\n" + b.tableau())
    groupes = b.par_condition()
    assert b.resume(groupes["sans bruit"])["intention"] >= 0.96
    assert b.resume(groupes["10 dB"])["intention"] >= 0.90
    tout = b.resume(b.resultats)
    assert tout["hors_actions"] == 0 and tout["latence_p90"] is not None and tout["latence_p90"] <= 800
    h = ba.epreuve_sans_parole(choix.transcripteur, minutes=10.0)
    assert h.sorties == []
