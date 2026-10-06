"""§10 : aucune fuite vers Claude. Tout le corpus passe par la vraie chaîne, avec un seuil qui envoie TOUT à Claude
(sauf ce qui est sensible), et un espion à la place de Claude. On vérifie chaque message reçu par l'espion."""

from __future__ import annotations

import random
import re
import shutil
from pathlib import Path

import pytest

from core.cerveau import Reponse
from modules.trieur import traitement
from modules.trieur.ia import CoucheIA
from tests.trieur.corpus.donnees import personne
from tests.trieur.corpus.generer import generer
from tests.trieur.corpus.juge import moteur_des_tests
from tests.trieur.outils import FauxSysteme

GRAINE = 20261006  # celle du corpus 1 : la personne fictive est le premier tirage (generer.py)


class Espion:
    def __init__(self):
        self.messages: list[str] = []

    def __call__(self, message, **options):
        self.messages.append(message)
        return Reponse("", {"type": "autre", "confiance": 0.3, "emetteur": None, "date": None, "montant": None,
                            "detail": ""}, 800, 40)  # fmt: skip


def test_rien_de_personnel_ne_part_chez_claude(corpus1, reglages, tmp_path):
    assert generer.__defaults__ == (GRAINE,)
    moi = personne(random.Random(GRAINE))
    copie = tmp_path / "corpus"
    shutil.copytree(corpus1.dossier, copie)
    reglages["classement"]["seuil_ia"] = 1.01  # tout irait chez Claude
    reglages["ia"]["mots_masques"] = [f"{moi.prenom} {moi.nom}", moi.prenom, moi.nom]  # = le nom de la session Mac
    espion = Espion()
    o = traitement.outils(reglages, systeme_=FauxSysteme(), moteur=moteur_des_tests(), ia=None)
    o.ia = CoucheIA(reglages, o.base, demander=espion)
    envoyes_par_fichier: dict[str, int] = {}
    for v in corpus1.verites:
        chemin = copie / v.fichier
        if not chemin.exists():
            continue
        avant = len(espion.messages)
        traitement.traiter(o, o.base.ajouter(chemin, "boite"))
        for enfant in list(o.ajoutes):
            traitement.traiter(o, enfant)
        o.ajoutes.clear()
        envoyes_par_fichier[v.fichier] = len(espion.messages) - avant
    o.base.fermer()

    # 1. Les documents sensibles (santé, identité, impôts, paie) ne sont jamais envoyés.
    sensibles = [v.fichier for v in corpus1.verites if v.sensible and v.fichier in envoyes_par_fichier]
    assert len(sensibles) >= 15
    assert [f for f in sensibles if envoyes_par_fichier[f]] == []
    # 2. Assez de documents sont partis pour que le contrôle ait un sens.
    print(f"\n{len(espion.messages)} messages, {len(sensibles)} documents sensibles retenus")
    assert len(espion.messages) >= 60
    # 3. Aucun message ne contient une donnée personnelle de la personne fictive.
    secrets = {"IBAN": moi.iban, "IBAN collé": moi.iban.replace(" ", ""), "carte": moi.carte, "n° sécu": moi.nir,
               "courriel": moi.courriel, "téléphone": moi.telephone, "adresse": moi.adresse, "ville": moi.ville,
               "nom": moi.nom, "prénom": moi.prenom}  # fmt: skip
    fuites = [(quoi, i) for i, m in enumerate(espion.messages) for quoi, s in secrets.items() if s.lower() in m.lower()]
    assert fuites == []
    for m in espion.messages:
        extrait = m.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        assert len(extrait) <= 3000
        assert not re.search(r"\d(?:[ .-]?\d){12,}", extrait), extrait  # aucun long numéro (carte, sécu, compte)
        assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", extrait)
    # 4. Rien n'a été perdu : chaque fichier est rangé quelque part (ou mis de côté), jamais effacé sans copie.
    restants = [p for p in copie.iterdir() if p.is_file() and not p.name.startswith(".") and p.name != "verite.json"]
    assert restants == [], restants


@pytest.mark.parametrize(
    "texte", ["Patient : Camille", "Votre numéro fiscal", "BULLETIN DE PAIE", "1 85 05 78 006 084 36"]
)
def test_indices_sensibles_suffisent(reglages, tmp_path, texte):
    from modules.trieur.base import Base
    from modules.trieur.extraction import Extraction

    base = Base(tmp_path / "t.db")
    espion = Espion()
    ia = CoucheIA(reglages, base, demander=espion)
    el = base.element(base.ajouter(Path("/x/a.pdf"), "cli"))
    assert ia.classer(Extraction("pdf", f"Document\n{texte}\nTotal 12,00 €"), None, el) is None
    assert espion.messages == []
    base.fermer()
