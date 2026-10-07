"""Le vide-frigo assemblé : mémoire du frigo, réponse pour l'iPhone ou le Terminal, « ajouter au menu de ce soir »,
idée originale contrôlée, et la commande `quotidien frigo`."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from quotidien import cli, config, ia
from quotidien.db import Base as BaseDonnees
from quotidien.frigo import service
from quotidien.repas import planificateur as pl
from quotidien.repas import service as menus
from quotidien.repas.base import charger
from quotidien.systeme import Resultat, Systeme

BASE = charger()
MERCREDI = datetime(2026, 10, 14, 18, 0).timestamp()


class Client:
    nom = "imitation"

    def __init__(self, *reponses: Any) -> None:
        self.reponses = list(reponses)

    def envoyer(self, systeme: str, contenu: ia.Contenu, max_jetons: int, delai: float) -> ia.ReponseBrute:
        r = self.reponses.pop(0)
        return ia.ReponseBrute(r if isinstance(r, str) else json.dumps(r), 900, 400)


@pytest.fixture
def db(maison: Path) -> BaseDonnees:
    return BaseDonnees(config.chemin_base())


def _frigo(db: BaseDonnees) -> dict[str, tuple[Any, ...]]:
    return {r[0]: tuple(r[1:]) for r in db.lignes("SELECT ingredient, quantite, incertain FROM frigo")}


def test_texte_memorise_puis_retire(db: BaseDonnees) -> None:
    r = config.defauts()
    rep = service.depuis_texte(db, r, "2 courgettes, feta, un reste de riz, bananes", BASE, horloge=MERCREDI)
    assert [e.ingredient for e in rep.elements] == ["courgette", "feta", "riz"] and rep.inconnus == ["bananes"]
    assert rep.propositions and not rep.message
    assert _frigo(db) == {"courgette": (2.0, 0), "feta": (None, 0), "riz": (None, 0)}
    assert db.lire_json("frigo:dernieres")["recettes"] == [p.recette.id for p in rep.propositions]
    # Le planificateur le voit : la courgette se perd dans quelques jours.
    assert set(pl.frigo_actuel(db, BASE, MERCREDI)) == {"courgette", "feta", "riz"}
    service.depuis_texte(db, r, "plus de feta, 3 courgettes", BASE, horloge=MERCREDI + 60)
    assert _frigo(db) == {"courgette": (3.0, 0), "riz": (None, 0)}
    service.depuis_texte(db, r, "poireaux", BASE, garder=False)
    assert "poireau" not in _frigo(db)
    rien = service.depuis_texte(db, r, "zzz", BASE)
    assert rien.message.startswith("🤔 Je n'ai reconnu aucun aliment") and not rien.propositions
    service.vider(db)
    assert _frigo(db) == {}


def test_photo_memorise_seulement_le_sur(db: BaseDonnees, tmp_path: Path) -> None:
    chemin = tmp_path / "frigo.heic"
    Image.new("RGB", (64, 48), (0, 120, 0)).save(chemin.with_suffix(".jpg"))
    chemin = chemin.with_suffix(".jpg")
    assert service.est_une_image(chemin) and service.est_une_image(Path("x.HEIC"))
    assert not service.est_une_image(Path("liste.txt"))
    client = Client({"ingredients": [{"nom": "courgette", "confiance": 0.9}, {"nom": "feta", "confiance": 0.4}]})
    rep = service.depuis_photo(db, config.defauts(), chemin, BASE, client=client, horloge=MERCREDI)
    assert [e.ingredient for e in rep.elements] == ["courgette", "feta"] and rep.cout_usd > 0
    assert _frigo(db) == {"courgette": (None, 0)}  # la feta, incertaine, n'est pas retenue
    texte = service.formater(rep, BASE)
    assert "🧊 J'ai compris : courgette." in texte and "❓ À confirmer : feta → feta ?" in texte
    sans_ia = service.depuis_photo(db, config.defauts(), chemin, BASE)
    assert sans_ia.message.startswith("📷") and not sans_ia.propositions


def test_formater_long_et_court(db: BaseDonnees) -> None:
    r = config.defauts()
    rep = service.depuis_texte(db, r, "1 oeuf, 200 g de saumon, 2 poireaux, crème, plus de lait, kiwis", BASE)
    long = service.formater(rep, BASE)
    assert long.splitlines()[0].startswith("🧊 J'ai compris : 1 œuf, pavé de saumon (200 g), 2 poireaux")
    deux = service.ReponseFrigo(elements=service.analyse_texte.analyser("2 pavés de saumon, ½ citron", BASE))
    assert "2 pavés de saumon, ½ citron." in service.formater(deux, BASE)
    assert "🚫 Plus de : lait demi-écrémé (retiré de ton frigo)." in long
    assert "🤷 Pas reconnu : kiwis." in long
    assert "1. " in long and " min · " in long and "quotidien frigo ce-soir 1" in long
    court = service.formater(rep, BASE, court=True)
    assert "ce-soir" not in court and len(court) < len(long)
    rien = service.depuis_texte(db, r, "sel", BASE)
    assert "Rien de réalisable" in service.formater(rien, BASE) and "--creatif" in service.formater(rien, BASE)
    assert "--creatif" not in service.formater(rien, BASE, court=True)
    reste = service.ReponseFrigo(elements=service.analyse_texte.analyser("un reste de riz", BASE))
    assert "reste de riz long" in service.formater(reste, BASE)


def test_ajouter_ce_soir(db: BaseDonnees) -> None:
    r = config.defauts()
    mercredi = date(2026, 10, 14)
    with pytest.raises(service.ChoixImpossible, match="lance d'abord"):
        service.ajouter_ce_soir(db, r, 1, mercredi, BASE)
    rep = service.depuis_texte(db, r, "poulet, crème, champignons", BASE)
    with pytest.raises(service.ChoixImpossible, match="quotidien menu"):
        service.ajouter_ce_soir(db, r, 1, mercredi, BASE)
    menus.produire(db, r, date(2026, 10, 12), base=BASE)
    with pytest.raises(service.ChoixImpossible, match="n°9"):
        service.ajouter_ce_soir(db, r, 9, mercredi, BASE)
    repas = service.ajouter_ce_soir(db, r, 2, mercredi, BASE, MERCREDI)
    assert repas.recette == rep.propositions[1].recette.id and repas.raisons == ["ajouté depuis ton frigo"]
    menu = pl.menu_couvrant(db, mercredi)
    assert menu is not None and menu.repas_du(mercredi).recette == repas.recette  # type: ignore[union-attr]


def test_ajouter_ce_soir_refuse_ce_que_le_profil_interdit(db: BaseDonnees, maison: Path) -> None:
    r = config.defauts()
    menus.produire(db, r, date(2026, 10, 12), base=BASE)
    service.depuis_texte(db, r, "poulet, crème, champignons", BASE)
    config.dossier_support().mkdir(parents=True, exist_ok=True)
    (config.dossier_support() / "profil.toml").write_text('[repas]\nregime = "vegetarien"\n', encoding="utf-8")
    with pytest.raises(service.ChoixImpossible, match="interdite par ton profil"):
        service.ajouter_ce_soir(db, config.charger(), 1, date(2026, 10, 14), BASE)


def _creative(**kw: Any) -> dict[str, Any]:
    d = {"nom": "Poêlée de poulet aux courgettes", "temps_min": 25,
         "ingredients": [{"nom": "filet de poulet", "quantite": 150, "unite": "g"},
                         {"nom": "courgette", "quantite": 2, "unite": "p"}],
         "etapes": ["Coupe le poulet et les courgettes.", "Fais revenir 15 min."]}  # fmt: skip
    d.update(kw)
    return d


def test_idee_originale_controlee(db: BaseDonnees) -> None:
    r = config.defauts()
    rep = service.depuis_texte(db, r, "poulet, courgettes", BASE)
    creative, message = service.creer(db, r, rep, BASE, client=Client(_creative()))
    assert message == "" and creative is not None
    assert creative.ingredients == ["150 g de filet de poulet", "2 courgettes"]
    assert creative.securite[0].startswith("Cuis filet de poulet à cœur")  # les étapes ne le disaient pas
    assert creative.securite[-1].startswith("Restes : au frigo dans les 2 h, 3 jours au plus")
    rep.creative, rep.propositions = creative, []
    texte = service.formater(rep, BASE)
    assert "✨ Idée originale : Poêlée de poulet aux courgettes — 25 min" in texte and "Allergènes : aucun" in texte
    assert "   1. Coupe le poulet" in texte and "⚠️" in texte
    assert "1. Coupe" not in service.formater(rep, BASE, court=True)
    # Les étapes disent déjà « à cœur » : pas de rappel en double.
    etapes = ["Coupe tout.", "Cuis le poulet à cœur, 12 min."]
    creative, _ = service.creer(db, r, rep, BASE, client=Client(_creative(etapes=etapes)))
    assert creative is not None and len(creative.securite) == 1


def _avec(nom: str, quantite: float, unite: str) -> dict[str, Any]:
    return _creative(ingredients=[{"nom": nom, "quantite": quantite, "unite": unite},
                                  {"nom": "courgette", "quantite": 1, "unite": "p"}])  # fmt: skip


@pytest.mark.parametrize(
    ("profil", "reponse", "refus"),
    [
        ("", _avec("fruit du dragon", 1, "p"), "n'est pas dans ma base"),
        ('[repas]\nallergies = ["lait"]\n', _avec("feta", 100, "g"), "allergènes"),
        ('[repas]\ndeteste = ["courgette"]\n', _creative(), "ne veux pas"),
        ('[repas]\nregime = "vegetarien"\n', _creative(), "régime (vegetarien)"),
        ('[repas]\nregime = "sans_porc"\n', _avec("lardons", 100, "g"), "régime (sans_porc)"),
        ("", "pas du json", "indisponible"),
    ],
)
def test_idee_originale_refusee(db: BaseDonnees, profil: str, reponse: Any, refus: str) -> None:
    if profil:
        config.dossier_support().mkdir(parents=True, exist_ok=True)
        (config.dossier_support() / "profil.toml").write_text(profil, encoding="utf-8")
    r = config.charger()
    assert not r.avertissements, r.avertissements
    rep = service.depuis_texte(db, r, "courgettes, feta", BASE)
    reponses = [reponse, reponse] if isinstance(reponse, str) else [reponse]
    creative, message = service.creer(db, r, rep, BASE, client=Client(*reponses))
    assert creative is None and refus in message


def test_idee_originale_budget_et_frigo_vide(db: BaseDonnees) -> None:
    r = config.defauts()
    vide = service.ReponseFrigo()
    assert service.creer(db, r, vide, BASE, client=Client()) == (None, "Dis-moi d'abord ce que tu as.")
    ia.Budget(db, r.reglages).noter(ia.ReponseBrute("", 0, 0, cout_usd=5.0), "test")
    rep = service.depuis_texte(db, r, "courgettes", BASE)
    creative, message = service.creer(db, r, rep, BASE, client=Client())
    assert creative is None and "Plus de budget IA" in message


# --- La commande ---------------------------------------------------------------------------------------------------


def _systeme() -> Systeme:
    return Systeme(lambda a, e, d: Resultat(1, ""), mac=False)


def test_cli_frigo(maison: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    s = _systeme()
    assert cli.main(["frigo"], s, lambda: MERCREDI) == 2
    assert "Dis-moi ce que tu as" in capsys.readouterr().out
    assert cli.main(["frigo", "2 courgettes, feta, un reste de riz"], s, lambda: MERCREDI) == 0
    sortie = capsys.readouterr().out
    assert sortie.startswith("🧊 J'ai compris : 2 courgettes, feta, reste de riz long.") and "1. " in sortie
    assert cli.main(["frigo", "poulet", "crème", "champignons", "--court"], s, lambda: MERCREDI) == 0
    assert "ce-soir" not in capsys.readouterr().out
    # Ajouter au menu de ce soir : il faut d'abord un menu.
    assert cli.main(["frigo", "ce-soir", "1"], s, lambda: MERCREDI) == 1
    assert "quotidien menu" in capsys.readouterr().out
    assert cli.main(["menu"], s, lambda: MERCREDI) == 0
    capsys.readouterr()
    assert cli.main(["frigo", "ce-soir", "1"], s, lambda: MERCREDI) == 0
    assert capsys.readouterr().out.startswith("✅ Au menu ce soir : ")
    assert cli.main(["frigo", "ce-soir"], s, lambda: MERCREDI) == 2
    assert cli.main(["frigo", "ce-soir", "un"], s, lambda: MERCREDI) == 2
    assert cli.main(["frigo", "ce-soir", "7"], s, lambda: MERCREDI) == 1
    capsys.readouterr()
    # Rien de reconnu ; l'idée originale demandée, mais pas d'IA dans les tests.
    assert cli.main(["frigo", "zzz"], s, lambda: MERCREDI) == 1
    assert cli.main(["frigo", "sel", "--creatif"], s, lambda: MERCREDI) == 1
    assert "IA indisponible" in capsys.readouterr().out
    # Une photo : sans IA, on propose le texte ; une image absente est signalée.
    photo = tmp_path / "frigo.jpg"
    Image.new("RGB", (32, 32)).save(photo)
    assert cli.main(["frigo", str(photo)], s, lambda: MERCREDI) == 1
    assert "envoie-moi plutôt la liste en texte" in capsys.readouterr().out
    assert cli.main(["frigo", str(tmp_path / "absente.jpg")], s, lambda: MERCREDI) == 1
    assert "Je ne trouve pas l'image absente.jpg" in capsys.readouterr().out
    # --sans-garder, puis vider.
    db = BaseDonnees(config.chemin_base())
    avant = _frigo(db)
    assert cli.main(["frigo", "poireaux", "--sans-garder"], s, lambda: MERCREDI) in (0, 1)
    assert _frigo(db) == avant
    assert cli.main(["frigo", "vider"], s, lambda: MERCREDI) == 0
    assert "Frigo oublié" in capsys.readouterr().out and _frigo(db) == {}


def test_cli_frigo_creatif_avec_ia(maison: Path, capsys: pytest.CaptureFixture[str],
                                   monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.setattr(ia, "choisir_client", lambda *a, **k: Client(_creative(
        ingredients=[{"nom": "sel", "quantite": 2, "unite": "g"}, {"nom": "poivre", "quantite": 1, "unite": "g"}],
        nom="Assaisonnement", etapes=["Mélange.", "Goûte."])))  # fmt: skip
    assert cli.main(["frigo", "sel", "--creatif"], _systeme(), lambda: MERCREDI) == 0
    assert "✨ Idée originale : Assaisonnement" in capsys.readouterr().out
