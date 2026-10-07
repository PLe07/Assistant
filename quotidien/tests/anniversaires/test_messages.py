"""Le message prêt (§6, §10.4) : 3 variantes, longueur, 0 formule interdite, et rien de privé envoyé à l'IA."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from quotidien import config, ia
from quotidien.anniversaires import messages
from quotidien.anniversaires.dates import DateNaissance
from quotidien.anniversaires.proches import Personne
from quotidien.db import Base as BaseDonnees

NOTES = ("souvenir : voyage à Lisbonne avec Max Exemple-Secret", "adore le foot",
         "son numéro : 06 12 34 56 78, 12 rue des Lilas 33000 Bordeaux")  # fmt: skip
LEA = Personne("cle-lea", "Léa", "Exemple-Secret", DateNaissance(14, 3, 2001), "ami_proche", "drole", NOTES,
               "06 98 76 54 32", "contacts", True)  # fmt: skip


class Espion:
    nom = "espion"

    def __init__(self, *reponses: Any) -> None:
        self.reponses = list(reponses)
        self.recus: list[tuple[str, Any]] = []

    def envoyer(self, systeme: str, contenu: ia.Contenu, max_jetons: int, delai: float) -> ia.ReponseBrute:
        self.recus.append((systeme, contenu))
        r = self.reponses.pop(0)
        return ia.ReponseBrute(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False), 500, 200)


@pytest.fixture
def db(tmp_path: Path) -> BaseDonnees:
    return BaseDonnees(tmp_path / "q.db")


def test_rien_de_prive_n_est_envoye_a_l_ia(db: BaseDonnees) -> None:
    variantes = ["Joyeux anniversaire Léa !\nOn se fait un foot bientôt ?",
                 "Bon anniversaire Léa 🎂\nLisbonne, la suite quand tu veux.",
                 "Léa, joyeux anniversaire !\n25 ans, et toujours imbattable au baby-foot."]  # fmt: skip
    espion = Espion({"variantes": variantes})
    m = messages.rediger(db, config.defauts().reglages, LEA, 25, 2026, client=espion)
    assert m.source == "ia" and len(m.variantes) == 3 and m.cout_usd > 0
    ((systeme, contenu),) = espion.recus
    assert isinstance(contenu, str)
    envoye = json.loads(contenu.removeprefix("<personne>").removesuffix("</personne>"))
    assert set(envoye) == {"prenom", "relation", "ton", "age", "notes"}
    assert envoye["prenom"] == "Léa" and envoye["relation"] == "ami proche" and envoye["ton"] == "drôle"
    assert envoye["age"] == 25
    tout = contenu + systeme
    for secret in ("Exemple-Secret", "06 12 34 56 78", "06 98 76 54 32", "rue des Lilas", "33000", "cle-lea"):
        assert secret not in tout, secret
    assert "voyage à Lisbonne" in contenu and "adore le foot" in contenu  # tes notes, elles, partent


def test_variantes_de_l_ia_verifiees_et_completees(db: BaseDonnees) -> None:
    mauvaises = {"variantes": [
        "Joyeux anniversaire Léa ! Que tous tes rêves se réalisent.",  # cliché
        "Bon anniversaire !\nPasse une belle journée.",  # sans le prénom
        "Léa",  # trop court
        "Joyeux anniversaire Léa !\nUne belle journée à toi, et à très vite pour fêter ça ensemble.",  # bonne
        "Joyeux anniversaire Léa !\nUne belle journée à toi, et à très vite pour fêter ça ensemble.",  # doublon
    ]}  # fmt: skip
    m = messages.rediger(db, config.defauts().reglages, LEA, 25, 2026, client=Espion(mauvaises))
    assert m.source == "mixte" and len(m.variantes) == 3
    assert m.variantes[0].startswith("Joyeux anniversaire Léa !\nUne belle journée")
    assert all(messages.defaut(v, "Léa") is None for v in m.variantes)
    sans_ia = messages.rediger(db, config.defauts().reglages, LEA, 25, 2026)  # ni clé ni Claude Code
    assert sans_ia.source == "local" and sans_ia.variantes == messages.locaux(LEA, 25, 2026)
    rien = messages.rediger(db, config.defauts().reglages, LEA, 25, 2026, client=Espion({"variantes": ["x" * 50]}))
    assert rien.source == "local"


@pytest.mark.parametrize(
    ("texte", "raison"),
    [
        ("Bon anniversaire Léa", "longueur"),
        ("Léa " + "a" * 400, "longueur"),
        ("Léa\n1\n2\n3\n4 et encore un peu de texte pour la longueur", "trop de lignes"),
        ("Joyeux anniversaire Léa ! Plein de bonheur pour cette nouvelle année.", "formule interdite"),
        ("Joyeux anniversaire Léa ! HAPPY BIRTHDAY, profite de ta journée.", "formule interdite"),
        ("Joyeux anniversaire Léa ! Tu prends un coup de vieux, mais ça te va.", "formule interdite"),
        ("Joyeux anniversaire Léa ! Regarde ça : https://exemple.fr/carte", "lien"),
        ("Joyeux anniversaire {prenom} ! Belle journée à toi, et à bientôt.", "sans le prénom"),
        ("Joyeux anniversaire Hugo ! Belle journée à toi, et à très bientôt.", "sans le prénom"),
    ],
)
def test_defauts(texte: str, raison: str) -> None:
    d = messages.defaut(texte, "Léa")
    assert d is not None and d.startswith(raison)


def test_tous_les_modeles_locaux_sont_bons() -> None:
    """Chaque ton × relation × âge × notes : 3 variantes différentes, valides, sans trou ni cliché."""
    notes_possibles = [(), ("souvenir : voyage à Lisbonne",), ("adore le foot",), ("souvenir : nos vacances en Corse",
                       "aime la montagne"), ("souvenir : la soirée du bac", "fan de jazz")]  # fmt: skip
    vus = 0
    for ton, relation, age, notes in itertools.product(config.TONS, (*config.RELATIONS, None), (None, 18, 20, 21, 25,
                                                       27, 30, 40, 52), notes_possibles):  # fmt: skip
        p = Personne(f"{ton}{relation}{age}", "Zoé", "Nom", DateNaissance(1, 1), relation, ton, notes)
        variantes = messages.locaux(p, age, 2026)
        assert len(variantes) == 3 and len(set(variantes)) == 3
        for v in variantes:
            assert messages.defaut(v, "Zoé") is None, (ton, relation, age, notes, v)
            assert 2 <= len(v.splitlines()) <= 4
            assert ("vous" in v.lower().split()) == (ton == "formel"), v  # vouvoiement seulement en formel
            if age and relation in ("collegue", "professeur"):
                assert f"{age} ans" not in v  # on ne parle pas de l'âge d'un collègue
        vus += 1
    assert vus == 4 * 7 * 9 * 5
    for ton in config.TONS:  # fêtes
        p = Personne("x", "Zoé", "", DateNaissance(0, 0), None, ton)
        assert all("Zoé" in v and "{" not in v for v in messages.fete(p))


def test_notes_transformees() -> None:
    assert messages._touches(("souvenir : voyage à Lisbonne",)) == ("notre voyage à Lisbonne", None)
    assert messages._touches(("Souvenirs - vacances en Corse.",)) == ("nos vacances en Corse", None)
    assert messages._touches(("souvenir : la soirée du bac", "adore le foot")) == ("la soirée du bac", "foot")
    assert messages._touches(("fan de jazz", "passion : la photo")) == (None, "jazz")
    assert messages._touches(("rien de spécial",)) == (None, None)


def test_meme_personne_meme_annee_memes_variantes() -> None:
    assert messages.locaux(LEA, 25, 2026) == messages.locaux(LEA, 25, 2026)
    assert messages.locaux(LEA, 25, 2026) != messages.locaux(LEA, 26, 2027)
