"""Le moteur audio, brique par brique : détection de voix et de fin de phrase, filtre anti-hallucination, Whisper
(avec un faux mlx : le vrai ne tourne que sur un Mac Apple Silicon), protocole."""

from __future__ import annotations

import base64
import json
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from outils import catalogue_reference as ref
from outils import corpus_audio as ca
from voix import protocole
from voix.audio import anti_hallucination as ah
from voix.audio import vad as vad_mod
from voix.audio import whisper_local as wl
from voix.audio.vad import TAUX, TRAME, FinDePhrase


class VadScript:
    """Un détecteur de voix qui suit un script : 1 = parole, 0 = silence, une valeur par trame de 32 ms."""

    nom = "script"

    def __init__(self, script: list[float]) -> None:
        self.script = script
        self.i = 0

    def reinitialiser(self) -> None:
        self.i = 0

    def probabilite(self, trame: np.ndarray) -> float:
        p = self.script[self.i] if self.i < len(self.script) else 0.0
        self.i += 1
        return p


def trames(n: int, niveau: float = 0.1) -> np.ndarray:
    return (np.ones(n * TRAME, dtype=np.float32) * niveau) if niveau else np.zeros(n * TRAME, dtype=np.float32)


# --- détection de voix ------------------------------------------------------------------------------------------


def test_silero_verifie_son_empreinte(tmp_path: Path) -> None:
    v = vad_mod.Silero()
    assert v.nom == "silero" and 0.0 <= v.probabilite(np.zeros(TRAME, dtype=np.float32)) < 0.5
    faux = tmp_path / "silero_vad.onnx"
    faux.write_bytes(b"pas un modele")
    with pytest.raises(vad_mod.ModeleInvalide, match="empreinte"):
        vad_mod.Silero(faux)
    assert isinstance(vad_mod.charger("webrtc"), vad_mod.WebRtc)
    assert isinstance(vad_mod.charger(), vad_mod.Silero)


def test_repli_webrtc_si_silero_manque(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vad_mod, "modele_silero", lambda: None)
    v = vad_mod.charger()
    assert v.nom == "webrtc" and v.probabilite(np.zeros(TRAME, dtype=np.float32)) == 0.0
    v.reinitialiser()


def test_pcm_en_flottants() -> None:
    x = vad_mod.en_flottants(np.array([0, 16384, -32768], dtype="<i2").tobytes())
    assert x.tolist() == [0.0, 0.5, -1.0]


def test_fin_de_phrase_par_le_silence() -> None:
    script = [0] * 5 + [1] * 20 + [0] * 30
    f = FinDePhrase(VadScript(script), silence_fin_ms=480, anticipation_ms=192)
    evs = f.ajouter(trames(len(script)))
    assert [(e.genre, e.raison) for e in evs] == [("debut", ""), ("pause", ""), ("fin", "silence")]
    assert evs[0].instant_s == pytest.approx(5 * TRAME / TAUX)
    assert f.fin_parole_s == pytest.approx(25 * TRAME / TAUX) and f.parole_s == pytest.approx(20 * TRAME / TAUX)
    assert evs[2].instant_s == pytest.approx(40 * TRAME / TAUX)
    # Tout ce qui a été reçu avant la fin (8 trames avant le début : moins que les 300 ms de réserve), parole, silence.
    assert len(f.audio()) == (5 + 20 + 15) * TRAME
    f = FinDePhrase(VadScript([0] * 30 + [1] * 10 + [0] * 20), silence_fin_ms=480)
    f.ajouter(trames(60))
    # La réserve est bornée à 300 ms (9 trames : 6 de silence + les 3 premières de parole), puis la suite.
    assert len(f.audio()) == (6 + 10 + 15) * TRAME
    assert f.ajouter(trames(5)) == []  # fini : plus rien


def test_reprise_apres_une_pause() -> None:
    script = [1] * 10 + [0] * 8 + [1] * 10 + [0] * 20
    f = FinDePhrase(VadScript(script), silence_fin_ms=480, anticipation_ms=192)
    evs = [e.genre for e in f.ajouter(trames(len(script)))]
    assert evs == ["debut", "pause", "pause", "fin"]  # deux pauses : la première transcription anticipée est jetée


def test_duree_max_attente_max_et_relache() -> None:
    f = FinDePhrase(VadScript([1] * 400), duree_max_s=2.0)
    assert [e.raison for e in f.ajouter(trames(400)) if e.genre == "fin"] == ["duree_max"]
    f = FinDePhrase(VadScript([0] * 400), attente_max_s=1.0)
    assert [e.raison for e in f.ajouter(trames(400))] == ["rien"]
    f = FinDePhrase(VadScript([1] * 10))
    f.ajouter(trames(10) + 0.0)
    f.ajouter(np.ones(100, dtype=np.float32) * 0.1)  # un bout de trame en attente
    assert f.relacher().raison == "relache" and f.relacher().raison == "relache"
    assert len(f.audio()) == 11 * TRAME
    f = FinDePhrase(VadScript([0] * 10))
    f.ajouter(trames(3))
    assert f.relacher().raison == "rien" and len(f.audio()) == 0


def test_le_brouhaha_plus_faible_que_ta_voix_compte_comme_du_silence() -> None:
    """Des voix au loin (le détecteur dit « parole ») mais 20 dB sous ta voix : la fin est trouvée."""
    script = [1.0] * 60
    signal = np.concatenate([trames(20, 0.3), trames(40, 0.03)])
    f = FinDePhrase(VadScript(script), silence_fin_ms=480)
    assert [e.raison for e in f.ajouter(signal) if e.genre == "fin"] == ["silence"]
    f = FinDePhrase(VadScript(script), silence_fin_ms=480, ecart_db=None)  # sans la règle : pas de fin
    assert [e for e in f.ajouter(signal) if e.genre == "fin"] == []


def test_vraie_parole_synthetisee() -> None:
    """Silero sur une vraie phrase française synthétisée (espeak-ng ici, `say` sur le Mac)."""
    voix = ca.voix_disponibles()
    if not voix:
        pytest.skip("aucune voix française sur cette machine")
    parole = ca.synthetiser("mets le volume à trente pour cent", voix[0], ca.DEBITS[voix[0].moteur][1])
    debut, fin = ca.bornes_parole(parole)
    signal = np.concatenate([np.zeros(8000, np.float32), parole, np.zeros(24000, np.float32)])
    signal += ca.bruit("silence", len(signal) / TAUX, 1)[: len(signal)] * ca.NIVEAU_SILENCE
    f = FinDePhrase(vad_mod.Silero())
    evs = [e for i in range(0, len(signal), 1600) for e in f.ajouter(signal[i : i + 1600])]
    assert [e.genre for e in evs if e.genre != "pause"] == ["debut", "fin"]
    assert abs(evs[0].instant_s - (0.5 + debut)) < 0.25
    latence = evs[-1].instant_s - (0.5 + fin)
    assert 0.3 < latence < 0.75, latence


# --- filtre anti-hallucination -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texte",
    [
        "Sous-titres réalisés par la communauté d'Amara.org", "Merci d'avoir regardé cette vidéo !",
        "Abonnez-vous à la chaîne.", "Sous-titrage Société Radio-Canada", "[Musique]", "♪♪♪", "...", "",
        "Merci de votre attention.", "ouvre ouvre ouvre ouvre", "le son le son le son le son", "Привет мир",
        "你好", "Au revoir et à bientôt", "Traduit par Jean",
    ],
)  # fmt: skip
def test_hallucinations_rejetees(texte: str) -> None:
    assert ah.filtrer(texte, 2.0).texte is None


def test_phrases_gardees_et_nettoyees() -> None:
    assert ah.filtrer("  Ouvre Safari.  ", 1.0).texte == "Ouvre Safari."
    assert ah.filtrer("« Monte le son ! »", 1.0).texte == "Monte le son !"
    assert ah.filtrer("Ferme Notion. Sous-titres réalisés par la communauté d'Amara.org", 1.5).texte == "Ferme Notion."
    assert ah.filtrer("Mets la musique, merci d'avoir regardé", 1.5).texte is not None  # pas une fin collée
    assert ah.filtrer("mets le volume à trente pour cent s’il te plaît", 2.5).texte is not None


def test_sans_parole_ou_trop_de_mots() -> None:
    assert ah.filtrer("ouvre Safari", 0.05) == ah.Verdict(None, "aucune parole entendue")
    assert ah.filtrer("Non.", 0.128).texte == "Non."  # un « non » dit vite : 4 trames de parole, gardé
    long = " ".join(f"mot{i}" for i in range(20))
    assert ah.filtrer(long, 1.0).raison == "trop de mots pour la parole entendue"
    assert ah.filtrer(long, 4.0).texte is not None
    assert ah.filtrer("!!! ???", 1.0).raison == "rien de lisible"
    assert ah.filtrer("— ", 1.0).raison == "rien de lisible"


# --- Whisper ------------------------------------------------------------------------------------------------------


def _modele(dossier: Path, fichiers: dict[str, bytes]) -> None:
    dossier.mkdir(parents=True)
    empreintes = {}
    for nom, contenu in fichiers.items():
        (dossier / nom).write_bytes(contenu)
        empreintes[nom] = {"sha256": wl.empreinte(dossier / nom), "taille": len(contenu)}
    (dossier / "EMPREINTES.json").write_text(json.dumps(empreintes))


def test_verifier_modele(tmp_path: Path) -> None:
    d = tmp_path / "whisper-small-mlx"
    assert wl.verifier_modele(d) == "modèle absent (pas d'EMPREINTES.json)"
    _modele(d, {"config.json": b"{}", "weights.npz": b"poids" * 100})
    assert wl.verifier_modele(d) is None and wl.verifier_modele(d, complet=True) is None
    (d / "weights.npz").write_bytes(b"POIDS" * 100)  # même taille, autre contenu
    assert wl.verifier_modele(d) is None
    assert wl.verifier_modele(d, complet=True) == "empreinte différente : weights.npz"
    (d / "weights.npz").write_bytes(b"court")
    assert wl.verifier_modele(d) == "taille inattendue : weights.npz"
    (d / "weights.npz").unlink()
    assert wl.verifier_modele(d) == "fichier manquant : weights.npz"
    (d / "EMPREINTES.json").write_text('{"../x": {}}')
    assert wl.verifier_modele(d) == "entrée invalide : ../x"
    (d / "EMPREINTES.json").write_text("[]")
    assert wl.verifier_modele(d) == "EMPREINTES.json illisible"


def test_invite_avec_tes_noms() -> None:
    assert wl.invite(None) == wl.INVITE_BASE
    t = wl.invite(ref.catalogue())
    assert t.startswith(wl.INVITE_BASE) and "Noms : Safari" in t and "Notion" in t and len(t) <= wl.INVITE_MAX
    assert "(dossier)" not in t


def test_charger_whisper_hors_mac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wl, "apple_silicon", lambda: False)
    assert wl.charger(tmp_path).raison == "mlx-whisper demande un Mac Apple Silicon"
    assert wl.charger(tmp_path, backend="onnx").transcripteur is None
    monkeypatch.setattr(wl, "apple_silicon", lambda: True)
    monkeypatch.setattr(wl, "mlx_installe", lambda: False)
    assert wl.charger(tmp_path).raison == "mlx-whisper n'est pas installé"
    monkeypatch.setattr(wl, "mlx_installe", lambda: True)
    assert wl.charger(tmp_path, taille="auto").raison == "modèle absent (pas d'EMPREINTES.json)"
    _modele(tmp_path / "whisper-base-mlx", {"config.json": b"{}"})
    c = wl.charger(tmp_path, taille="base", garder_min=2)
    assert isinstance(c.transcripteur, wl.WhisperMlx) and c.raison == "Whisper base (mlx)"
    assert c.transcripteur.garder_s == 120


@pytest.fixture
def faux_mlx(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Un faux mlx-whisper : on vérifie ce que Voix lui demande (français, invite, une passe, sans horodatage)."""
    appels: dict[str, Any] = {"charges": 0}

    class Options:
        def __init__(self, **kw: Any) -> None:
            appels["options"] = kw

    def decode(modele: Any, mel: Any, options: Any) -> Any:
        appels["mel"] = mel
        return types.SimpleNamespace(text=" Ouvre Safari. ", no_speech_prob=0.01, avg_logprob=-0.2)

    def load_model(chemin: str, dtype: Any) -> Any:
        appels["charges"] += 1
        appels["chemin"] = chemin
        return types.SimpleNamespace(dims=types.SimpleNamespace(n_mels=80))

    modules = {
        "mlx": types.ModuleType("mlx"), "mlx.core": types.SimpleNamespace(float16="f16"),
        "mlx_whisper": types.ModuleType("mlx_whisper"),
        "mlx_whisper.load_models": types.SimpleNamespace(load_model=load_model),
        "mlx_whisper.audio": types.SimpleNamespace(
            N_FRAMES=3000, N_SAMPLES=480000,
            log_mel_spectrogram=lambda a, n_mels, padding: np.zeros((len(a) // 160 + padding // 160, n_mels)),
            pad_or_trim=lambda m, n, axis: m[:n],
        ),
        "mlx_whisper.decoding": types.SimpleNamespace(DecodingOptions=Options, decode=decode),
    }  # fmt: skip
    for nom, m in modules.items():
        monkeypatch.setitem(sys.modules, nom, m)
    return appels


def test_whisper_mlx_avec_un_faux_mlx(tmp_path: Path, faux_mlx: dict[str, Any]) -> None:
    t = [100.0]
    w = wl.WhisperMlx(tmp_path, garder_s=60, horloge=lambda: t[0])
    assert not w.charge and w.liberer() is False
    r = w.transcrire(np.zeros(16000, dtype=np.float32), "Commandes vocales")
    assert r.texte == "Ouvre Safari." and r.sans_parole == 0.01 and r.logprob == -0.2
    o = faux_mlx["options"]
    assert o["language"] == "fr" and o["temperature"] == 0.0 and o["without_timestamps"] is True
    assert o["prompt"] == "Commandes vocales" and faux_mlx["mel"].shape == (3000, 80)
    w.transcrire(np.zeros(16000, dtype=np.float32))
    assert faux_mlx["charges"] == 1 and faux_mlx["options"]["prompt"] is None and w.charge
    t[0] = 130.0
    assert w.liberer() is False and w.charge  # gardé au chaud
    assert w.liberer(maintenant=161.0) is True and not w.charge  # libéré après 60 s sans servir
    w.transcrire(np.zeros(1600, dtype=np.float32))
    assert faux_mlx["charges"] == 2


# --- protocole ----------------------------------------------------------------------------------------------------


def _ligne(**m: Any) -> bytes:
    return json.dumps({"v": 1, **m}).encode()


def test_protocole_messages_valides() -> None:
    assert protocole.encoder({"type": "etat", "etat": "repos"}) == b'{"v": 1, "type": "etat", "etat": "repos"}\n'
    pcm = base64.b64encode(np.zeros(1600, dtype="<i2").tobytes()).decode()
    assert len(protocole.decoder(_ligne(type="audio", id=1, pcm=pcm))["octets"]) == 3200
    assert protocole.decoder(_ligne(type="ecoute", etat="debut", id=1, mode="maintien"))["mode"] == "maintien"
    assert protocole.decoder(_ligne(type="texte", texte="ouvre Safari", source="clavier", ref="a-1"))["ref"] == "a-1"
    assert protocole.decoder(_ligne(type="texte", texte="x", source="apple", id=3))["id"] == 3
    assert protocole.decoder(_ligne(type="pont", id=2, ok=True, donnees={"a": 1}))["ok"] is True
    assert protocole.decoder(_ligne(type="bonjour", client="app"))["client"] == "app"


@pytest.mark.parametrize(
    "ligne",
    [
        b"pas du json", b"[1, 2]", b'{"type": "audio"}', _ligne(v=2, type="bonjour"), _ligne(type="shell"),
        _ligne(type="ecoute", etat="debut", id=-1), _ligne(type="ecoute", etat="exploser", id=1),
        _ligne(type="ecoute", etat="debut", id=1, mode="espion"), _ligne(type="ecoute", etat="debut", id=True),
        _ligne(type="audio", id=1, pcm="!!!"), _ligne(type="audio", id=1, pcm="AA=="),
        _ligne(type="audio", id=1, pcm="A" * 200_000), _ligne(type="audio", id=1, pcm=3),
        _ligne(type="texte", texte="x" * 501, source="clavier"), _ligne(type="texte", texte="a\x00b", source="clic"),
        _ligne(type="texte", texte="x", source="internet"), _ligne(type="texte", texte="x", source="apple"),
        _ligne(type="texte", texte="x", source="clic", ref="a b"), _ligne(type="pont", id=1, ok="oui"),
        _ligne(type="pont", id=1, ok=True, donnees=[]), b"\xff\xfe", b"x" * (protocole.TAILLE_MAX_LIGNE + 1),
    ],
)  # fmt: skip
def test_protocole_messages_refuses(ligne: bytes) -> None:
    with pytest.raises(protocole.MessageInvalide):
        protocole.decoder(ligne)
