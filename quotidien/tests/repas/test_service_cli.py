"""Le menu assemblé et ses commandes : `quotidien menu`, `--regenerer`, `menu remplacer jeudi`, `noter jeudi 👍`,
`envie "…"`."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from quotidien import cli, config
from quotidien.db import Base as BaseDonnees
from quotidien.repas import planificateur as pl
from quotidien.repas import service
from quotidien.repas.base import charger
from quotidien.systeme import Resultat, Systeme

BASE = charger()
MERCREDI = datetime(2026, 10, 14, 18, 0).timestamp()
DIMANCHE_SOIR = datetime(2026, 10, 18, 17, 30).timestamp()


def _systeme() -> Systeme:
    return Systeme(lambda a, e, d: Resultat(0, ""), mac=False)


def test_semaine_affichee() -> None:
    r = config.defauts()
    assert service.semaine_affichee(r, datetime(2026, 10, 14, 9, 0)) == date(2026, 10, 12)
    assert service.semaine_affichee(r, datetime(2026, 10, 18, 16, 59)) == date(2026, 10, 12)
    assert service.semaine_affichee(r, datetime(2026, 10, 18, 17, 0)) == date(2026, 10, 19)
    assert service.semaine_affichee(r, datetime(2026, 10, 12, 0, 0)) == date(2026, 10, 12)


def test_jours() -> None:
    menu = pl.Menu("2026-10-12", [])
    assert service.jour_dans_menu(menu, "Jeudi") == date(2026, 10, 15)
    assert service.jour_dans_menu(menu, "dim") == date(2026, 10, 18)
    assert service.jour_dans_menu(menu, "2026-10-13") == date(2026, 10, 13)
    with pytest.raises(service.JourInconnu):
        service.jour_dans_menu(menu, "jeudo")
    mercredi = date(2026, 10, 14)
    assert service.jour_passe("lundi", mercredi) == date(2026, 10, 12)
    assert service.jour_passe("mercredi", mercredi) == mercredi
    assert service.jour_passe("jeudi", mercredi) == date(2026, 10, 8)  # le dernier jeudi passé
    assert service.jour_passe("hier", mercredi) == date(2026, 10, 13)
    assert service.jour_passe("ce soir", mercredi) == mercredi
    assert service.jour_passe("2026-10-01", mercredi) == date(2026, 10, 1)
    with pytest.raises(service.JourInconnu):
        service.jour_passe("bientôt", mercredi)


def test_produire_garde_puis_regenere(maison: Path) -> None:
    db = BaseDonnees(config.chemin_base())
    r = config.defauts()
    lundi = date(2026, 10, 12)
    a = service.produire(db, r, lundi, base=BASE)
    assert a.nouveau and a.page.name == "Menu de la semaine.html" and a.page.parent == config.dossier_support()
    b = service.produire(db, r, lundi, base=BASE)
    assert not b.nouveau and [x.recette for x in b.menu.repas] == [x.recette for x in a.menu.repas]
    config.icloud_drive().mkdir(parents=True)
    c = service.produire(db, r, lundi, regenerer=True, base=BASE)
    assert c.nouveau and [x.recette for x in c.menu.repas] != [x.recette for x in a.menu.repas]
    assert c.page.parent == config.dossier_icloud() and c.page.exists()
    texte = service.resume(c, BASE)
    assert texte.startswith("🍽️ Menu de la semaine du lundi 12 octobre") and "🛒 Courses du lundi" in texte
    assert all(f"  {config.JOURS[i]}" in texte for i in range(7))


def test_cli_menu_remplacer_noter_envie(maison: Path, capsys: pytest.CaptureFixture[str]) -> None:
    s = _systeme()
    assert cli.main(["menu"], s, lambda: MERCREDI) == 0
    sortie = capsys.readouterr().out
    assert "Menu de la semaine du lundi 12 octobre" in sortie
    db = BaseDonnees(config.chemin_base())
    avant = service.menu_de(db, date(2026, 10, 12))
    assert avant is not None
    jeudi_avant = avant.repas_du(date(2026, 10, 15))
    assert cli.main(["menu", "remplacer", "jeudi"], s, lambda: MERCREDI) == 0
    assert "✅ Nouveau plat : jeudi" in capsys.readouterr().out
    apres = service.menu_de(db, date(2026, 10, 12))
    assert apres is not None and apres.repas_du(date(2026, 10, 15)).recette != jeudi_avant.recette  # type: ignore[union-attr]
    assert cli.main(["menu", "remplacer"], s, lambda: MERCREDI) == 2
    assert cli.main(["menu", "remplacer", "jeudo"], s, lambda: MERCREDI) == 1
    # Noter : « lundi » est le lundi passé de cette semaine.
    assert cli.main(["noter", "lundi", "👎"], s, lambda: MERCREDI) == 0
    assert "Il ne reviendra plus" in capsys.readouterr().out
    lundi = apres.repas_du(date(2026, 10, 12))
    assert lundi is not None and lundi.recette in pl.notes(db)[1]
    assert cli.main(["noter", "lundi", "bof bof"], s, lambda: MERCREDI) == 2
    assert cli.main(["noter", "jeudi", "👍"], s, lambda: MERCREDI) == 1  # le jeudi passé n'a pas de menu
    # Envie : comprise en local, gardée pour le prochain menu.
    assert cli.main(["envie", "envie", "de", "mexicain"], s, lambda: MERCREDI) == 0
    assert "Envie notée" in capsys.readouterr().out
    assert cli.main(["envie"], s, lambda: MERCREDI) == 2
    assert cli.main(["envie", "zzz"], s, lambda: MERCREDI) == 1  # rien de reconnu, pas d'IA ici
    # Dimanche soir : le menu de la semaine suivante, qui tient compte de l'envie.
    assert cli.main(["menu"], s, lambda: DIMANCHE_SOIR) == 0
    assert "lundi 19 octobre" in capsys.readouterr().out
    suivant = service.menu_de(db, date(2026, 10, 19))
    assert suivant is not None and suivant.envies == ["envie de mexicain"]
    assert cli.main(["menu", "--regenerer"], s, lambda: DIMANCHE_SOIR) == 0
    assert cli.main([], s) == 0


def test_cli_reglages_abimes_signales(maison: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config.dossier_support().mkdir(parents=True)
    (config.dossier_support() / "profil.toml").write_text("[repas]\nbudget_semaine = 'beaucoup'\n", encoding="utf-8")
    assert cli.main(["noter", "lundi", "👍"], _systeme(), lambda: MERCREDI) == 1
    assert "budget_semaine" in capsys.readouterr().err


def test_restes_la_semaine_suivante_dits_clairement() -> None:
    rec = next(iter(BASE.recettes))
    dimanche = pl.Repas("2026-10-18", "diner", "cuisine", rec, 2.0, restes_pour=["2026-10-21/diner"])
    assert service.ligne_repas(BASE, dimanche).endswith("en faire plus pour mercredi soir de la semaine prochaine")
    lundi = pl.Repas("2026-10-12", "diner", "cuisine", rec, 2.0, restes_pour=["2026-10-14/dejeuner"])
    assert service.ligne_repas(BASE, lundi).endswith("en faire plus pour mercredi midi")
