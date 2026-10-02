"""La traduction français → anglais, SUR TON MAC : un modèle Argos Translate (libre), lu par CTranslate2
(déjà utilisé par les oreilles) et SentencePiece. Aucun texte ne quitte le Mac, aucun appel à Claude.

Le modèle (~100 Mo) se télécharge une fois :  python -m modules.traduction --telecharger
"""

import shutil
import ssl
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from modules.traduction import parametres as p


class ModeleAbsent(Exception):
    """Le message dit comment le télécharger."""


def _dossier_modele(racine: Path = p.MODELE) -> tuple[Path, Path] | None:
    """(dossier CTranslate2, fichier SentencePiece) dans le modèle extrait, ou None."""
    if not racine.exists():
        return None
    binaires = sorted(racine.rglob("model.bin"))
    decoupeurs = sorted(racine.rglob("sentencepiece.model")) or sorted(racine.rglob("*.model"))
    return (binaires[0].parent, decoupeurs[0]) if binaires and decoupeurs else None


def present() -> bool:
    return _dossier_modele() is not None


def telecharger(afficher=print) -> Path:
    """Télécharge et extrait le modèle (une seule fois). Rien d'autre n'est touché."""
    if present():
        afficher(f"✅ Modèle déjà prêt dans {p.MODELE}")
        return p.MODELE
    import certifi

    p.DOSSIER.mkdir(parents=True, exist_ok=True)
    contexte = ssl.create_default_context(cafile=certifi.where())
    with tempfile.TemporaryDirectory(dir=p.DOSSIER) as tmp:
        archive = Path(tmp) / "modele.zip"
        afficher("Téléchargement du modèle de traduction (~100 Mo, une seule fois)…")
        requete = urllib.request.Request(p.URL_MODELE, headers={"User-Agent": "Assistant/1.0"})
        with urllib.request.urlopen(requete, timeout=60, context=contexte) as r, open(archive, "wb") as f:
            shutil.copyfileobj(r, f)
        extrait = Path(tmp) / "modele"
        with zipfile.ZipFile(archive) as z:
            for nom in z.namelist():  # jamais en dehors du dossier prévu
                cible = (extrait / nom).resolve()
                if not str(cible).startswith(str(extrait.resolve())):
                    raise ModeleAbsent(f"archive suspecte ({nom}) : rien n'a été installé")
            z.extractall(extrait)
        if _dossier_modele(extrait) is None:
            raise ModeleAbsent("le fichier téléchargé n'est pas un modèle de traduction : rien n'a été installé")
        if p.MODELE.exists():
            shutil.rmtree(p.MODELE)
        shutil.move(str(extrait), str(p.MODELE))
    afficher(f"✅ Modèle prêt dans {p.MODELE}")
    return p.MODELE


def assembler(morceaux: list[str]) -> str:
    """Les morceaux rendus par le modèle → une phrase. « ▁ » marque le début d'un mot : on le remplace par une
    espace (comme Argos Translate), car le découpeur français ne connaît pas les mots anglais et les laisserait."""
    texte = "".join(m for m in morceaux if m not in ("<unk>", "<s>", "</s>"))
    return " ".join(texte.replace("▁", " ").split())


class Traducteur:
    """Chargé une fois (2 à 3 s), puis chaque phrase se traduit en moins d'une seconde."""

    def __init__(self):
        trouve = _dossier_modele()
        if trouve is None:
            raise ModeleAbsent("le modèle de traduction n'est pas encore téléchargé : "
                               "python -m modules.traduction --telecharger")
        import ctranslate2
        import sentencepiece

        dossier, decoupeur = trouve
        self.decoupeur = sentencepiece.SentencePieceProcessor(model_file=str(decoupeur))
        self.modele = ctranslate2.Translator(str(dossier), device="cpu", compute_type="auto", inter_threads=1)

    def traduire(self, texte: str) -> str:
        jetons = self.decoupeur.encode(texte, out_type=str)
        resultat = self.modele.translate_batch([jetons], beam_size=4, max_decoding_length=512)
        return assembler(resultat[0].hypotheses[0])
