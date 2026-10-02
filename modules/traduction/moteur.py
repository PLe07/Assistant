"""La traduction français → anglais, SUR TON MAC, lue par CTranslate2 (déjà utilisé par les oreilles) et
SentencePiece. Aucun texte ne quitte le Mac, aucun appel à Claude. Deux modèles libres :

- le grand, NLLB (Meta, ~1,3 Go) : comprend le sens (« contrôle » de classe = test) ; ~1 s par phrase.
  Se télécharge une fois :  python -m modules.traduction --telecharger
- le petit, Argos Translate (~100 Mo) : 0,1 s, mais presque mot à mot. Sert si le grand n'est pas là.
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


def _dossier_nllb(racine: Path = p.NLLB) -> tuple[Path, Path] | None:
    """(dossier CTranslate2, fichier SentencePiece) du grand modèle, ou None."""
    if not racine.exists():
        return None
    binaires, decoupeurs = sorted(racine.rglob("model.bin")), sorted(racine.rglob("sentencepiece.bpe.model"))
    return (binaires[0].parent, decoupeurs[0]) if binaires and decoupeurs else None


def present() -> bool:
    """Un modèle est là (le grand ou le petit) : la traduction peut s'allumer."""
    return _dossier_nllb() is not None or _dossier_modele() is not None


def telecharger_nllb(afficher=print) -> Path:
    """Télécharge le grand modèle (une fois, ~1,3 Go) depuis Hugging Face, l'essaie sur une phrase, puis
    l'installe. Plusieurs copies sont essayées dans l'ordre ; si aucune ne marche, rien n'est installé et le
    petit modèle continue de servir."""
    if _dossier_nllb() is not None:
        afficher(f"✅ Grand modèle déjà prêt dans {p.NLLB}")
        return p.NLLB
    from huggingface_hub import hf_hub_download, list_repo_files, snapshot_download

    p.DOSSIER.mkdir(parents=True, exist_ok=True)
    for depot in p.NLLB_DEPOTS:
        with tempfile.TemporaryDirectory(dir=p.DOSSIER) as tmp:
            cible = Path(tmp) / "nllb"
            try:
                fichiers = set(list_repo_files(depot))
                if "model.bin" not in fichiers:
                    afficher(f"   · {depot} : pas un modèle CTranslate2, suivant")
                    continue
                afficher(f"Téléchargement du grand modèle ({depot}), une seule fois…")
                snapshot_download(depot, local_dir=str(cible), allow_patterns=sorted(fichiers & {
                    "model.bin", "config.json", "shared_vocabulary.txt", "shared_vocabulary.json",
                    "sentencepiece.bpe.model"}))
                if not (cible / "sentencepiece.bpe.model").exists():  # le découpeur, depuis le modèle officiel
                    hf_hub_download(p.NLLB_DECOUPEUR[0], p.NLLB_DECOUPEUR[1], local_dir=str(cible))
                essai = Traducteur(dossier_nllb=cible).traduire("Bonjour, je suis étudiant.")
                if "student" not in essai.lower():
                    afficher(f"   · {depot} : l'essai ne donne pas une vraie traduction ({essai!r}), suivant")
                    continue
            except Exception as e:  # réseau, copie retirée, format inattendu… : la suivante
                afficher(f"   · {depot} : impossible ({type(e).__name__} : {str(e)[:120]}), suivant")
                continue
            if p.NLLB.exists():
                shutil.rmtree(p.NLLB)
            shutil.move(str(cible), str(p.NLLB))
        afficher(f"✅ Grand modèle prêt dans {p.NLLB} (essai : « {essai} »)")
        return p.NLLB
    raise ModeleAbsent("aucune copie du grand modèle n'a pu être téléchargée : rien n'a été installé "
                       "(le petit modèle continue de servir)")


def telecharger(afficher=print) -> Path:
    """Télécharge et extrait le petit modèle (une seule fois). Rien d'autre n'est touché."""
    if _dossier_modele() is not None:
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
    """Chargé une fois (quelques secondes), puis chaque phrase se traduit en une seconde ou moins.
    Le modèle préféré (réglage « moteur ») s'il est là, sinon l'autre."""

    def __init__(self, moteur: str | None = None, dossier_nllb: Path | None = None):
        grand = _dossier_nllb(dossier_nllb) if dossier_nllb else _dossier_nllb()
        petit = None if dossier_nllb else _dossier_modele()
        prefere = "nllb" if dossier_nllb else (moteur or p.moteur())
        if grand and (prefere == "nllb" or petit is None):
            self.nom, (dossier, decoupeur) = "nllb", grand
        elif petit:
            self.nom, (dossier, decoupeur) = "argos", petit
        else:
            raise ModeleAbsent("le modèle de traduction n'est pas encore téléchargé : "
                               "python -m modules.traduction --telecharger")
        import ctranslate2
        import sentencepiece

        self.decoupeur = sentencepiece.SentencePieceProcessor(model_file=str(decoupeur))
        self.modele = ctranslate2.Translator(str(dossier), device="cpu", compute_type="auto", inter_threads=1)

    def traduire(self, texte: str) -> str:
        jetons = self.decoupeur.encode(texte, out_type=str)
        if self.nom == "nllb":  # NLLB : on lui dit la langue de départ, et celle d'arrivée
            resultat = self.modele.translate_batch([["fra_Latn", *jetons, "</s>"]], target_prefix=[["eng_Latn"]],
                                                   beam_size=4, max_decoding_length=min(512, 2 * len(jetons) + 16))
            return assembler(resultat[0].hypotheses[0][1:])
        resultat = self.modele.translate_batch([jetons], beam_size=4, max_decoding_length=512)
        return assembler(resultat[0].hypotheses[0])
