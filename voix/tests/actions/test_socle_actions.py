"""L'exécuteur (liste blanche, pas de shell, délai), le pont (ordres fermés), le journal, les routines."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tests.faux_mac import FauxMac
from voix.actions.executeur import Executeur, ProgrammeRefuse, dossiers_modules
from voix.actions.pont import OrdreRefuse, PontAbsent, valider
from voix.actions.routines import EtapeRefusee, preparer
from voix.journal import Journal, caviarder
from voix.nlu.alias import Routine, lire
from voix.session import Session

# --- exécuteur ---------------------------------------------------------------------------------------------------


def test_executeur_refuse_hors_liste_et_arguments_douteux(mac: FauxMac) -> None:
    e = mac.outils().executeur
    for programme in ("rm", "sh", "bash", "sudo", "python3", "/bin/sh", "open; rm"):
        with pytest.raises(ProgrammeRefuse):
            e.lancer(programme, [])
    with pytest.raises(ProgrammeRefuse):
        e.lancer("open", ["a\x00b"])
    with pytest.raises(ProgrammeRefuse):
        e.lancer("open", ["x" * 5000])
    with pytest.raises(ProgrammeRefuse):
        Executeur([str(mac.racine / "vide")], []).lancer("open", ["x"])  # introuvable
    assert e.trouver("rm") is None and e.present("open")


def test_executeur_delai_et_sortie(mac: FauxMac) -> None:
    e = mac.outils().executeur
    e.delai_s = 0.5
    mac.regler(lent=["pmset"])
    r = e.lancer("pmset", ["-g", "batt"])
    assert r.delai_depasse and not r.ok
    mac.regler(lent=[], batt="100%; charged;")
    assert e.lancer("pmset", ["-g", "batt"]).sortie == "100%; charged;"


def test_executeur_environnement_minimal(tmp_path: Path) -> None:
    script = tmp_path / "open"
    script.write_text('#!/bin/sh\necho "$PATH|$SECRET"\n')
    script.chmod(0o755)
    module = tmp_path / "tableau"
    module.write_text('#!/bin/sh\necho "$PATH"\n')
    module.chmod(0o755)
    e = Executeur([str(tmp_path)], [str(tmp_path), "/opt/homebrew/bin"])
    import os

    os.environ["SECRET"] = "fuite"
    try:
        assert e.lancer("open", []).sortie.strip() == "/usr/bin:/bin:/usr/sbin:/sbin|"
    finally:
        del os.environ["SECRET"]
    assert e.lancer("tableau", []).sortie.strip().startswith(f"{tmp_path}:/opt/homebrew/bin:")


def test_dossiers_modules(tmp_path: Path) -> None:
    d = dossiers_modules(tmp_path, "/a:/opt/homebrew/bin::/b")
    assert d[:3] == [str(tmp_path / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin"] and d[3:] == ["/a", "/b"]


# --- pont ------------------------------------------------------------------------------------------------------


def test_pont_ordres_fermes() -> None:
    assert valider("app.quitter", {"bundle": "com.spotify.client"}) == {"bundle": "com.spotify.client"}
    assert valider("app.quitter_tout", {}) == {}
    for ordre, params in [
        ("shell", {}), ("app.quitter", {}), ("app.quitter", {"bundle": "a b"}), ("app.quitter", {"bundle": "-x"}),
        ("app.quitter", {"bundle": "x", "script": "do shell script"}), ("musique.lecture", {"lecteur": "vlc"}),
        ("apparence.regler", {"sombre": "oui"}), ("notification", {"titre": "", "message": "x"}),
        ("notification", {"titre": "t", "message": "x" * 400}),
    ]:  # fmt: skip
        with pytest.raises(OrdreRefuse):
            valider(ordre, params)
    assert not PontAbsent().demander("ecran.verrouiller", {}).ok


# --- journal ---------------------------------------------------------------------------------------------------


def test_caviarder() -> None:
    assert caviarder("écris à paul@exemple.fr au 06 12 34 56 78") == "écris à [e-mail] au [nombre]"
    assert caviarder("volume à 30") == "volume à 30"


def test_journal_borne_desactivable_oubli(tmp_path: Path, mac: FauxMac) -> None:
    j = Journal(tmp_path / "journal.jsonl", taille=3)
    for i in range(5):
        j.ajouter(f"phrase {i}", "app.ouvrir", "fait", "✓", datetime(2026, 10, 13, 9, i))
    assert [e["texte"] for e in j.lire()] == ["phrase 2", "phrase 3", "phrase 4"]
    assert oct((tmp_path / "journal.jsonl").stat().st_mode & 0o777) == "0o600"
    assert j.oublier() and not j.oublier() and j.lire() == []
    off = Journal(tmp_path / "off.jsonl", actif=False)
    off.ajouter("x", None, "fait", "✓", datetime(2026, 1, 1))
    assert not (tmp_path / "off.jsonl").exists()
    (tmp_path / "abime.jsonl").write_text('pas du json\n["liste"]\n{"texte": "ok"}\n')
    assert Journal(tmp_path / "abime.jsonl").lire() == [{"texte": "ok"}]
    s = Session(mac.outils(), journal=Journal(tmp_path / "s.jsonl"))
    s.entendre("ouvre Notion")
    s.entendre("merci")  # rien d'exploitable : pas noté
    s.entendre("éteins le Mac")
    entrees = Journal(tmp_path / "s.jsonl").lire()
    assert [(e["texte"], e["intention"], e["statut"]) for e in entrees] == [
        ("ouvre Notion", "app.ouvrir", "fait"), ("éteins le Mac", "refus", "refus")]  # fmt: skip


# --- routines --------------------------------------------------------------------------------------------------


def _routine(etapes: str, sensible: bool = False) -> Routine:
    toml = f'[[routine]]\nnom = "r"\nphrases = ["lance r"]\nsensible = {str(sensible).lower()}\netapes = [{etapes}]\n'
    c = lire(toml, Path("/Users/exemple"))
    assert not c.erreurs, c.erreurs
    return c.routines[0]


def test_routine_preparee(mac: FauxMac) -> None:
    o = mac.outils()
    r = _routine('{ intention = "app.ouvrir", app = "Notion" },'
                 ' { intention = "dossier.ouvrir", dossier = "Documents" },'
                 ' { intention = "son.regler", niveau = 20 }, { intention = "concentration.activer" },'
                 ' { intention = "musique.playlist", playlist = "Révisions" },'
                 ' { intention = "minuteur.lancer", duree = "25 minutes" }')  # fmt: skip
    etapes = preparer(r, o.catalogue)
    assert [e.intention for e in etapes][:3] == ["app.ouvrir", "dossier.ouvrir", "son.regler"]
    assert etapes[0].params["objet"].ident == "notion.id" and etapes[5].params == {"duree_s": 1500}


@pytest.mark.parametrize(
    ("etapes", "sensible", "raison"),
    [
        ('{ intention = "systeme.veille" }', False, "sensible"),
        ('{ intention = "routine.lancer" }', False, "pas permise"),
        ('{ intention = "refus" }', False, "pas permise"),
        ('{ intention = "shell", commande = "rm -rf ~" }', False, "pas permise"),
        ('{ intention = "app.ouvrir", app = "Zorglub" }', False, "introuvable"),
        ('{ intention = "son.regler", niveau = 150 }', False, "entre 0 et 100"),
        ('{ intention = "son.regler", niveau = true }', False, "entre 0 et 100"),
        ('{ intention = "minuteur.lancer", duree = "bientôt" }', False, "incomprise"),
        ('{ intention = "app.ouvrir", app = "Notion", script = "x" }', False, "inconnu"),
        ('{ intention = "web.chercher_google", requete = "' + "x" * 300 + '" }', False, "invalide"),
    ],
)
def test_routine_refusee(mac: FauxMac, etapes: str, sensible: bool, raison: str) -> None:
    with pytest.raises(EtapeRefusee, match=raison):
        preparer(_routine(etapes, sensible), mac.outils().catalogue)


def test_routine_refusee_ne_lance_rien(mac: FauxMac) -> None:
    from voix.actions import routines

    o = mac.outils()
    r = _routine('{ intention = "app.ouvrir", app = "Notion" }, { intention = "son.regler", niveau = 900 }')
    rep = routines.lancer(r, o.catalogue, lambda c: pytest.fail("rien ne doit être lancé"))
    assert rep.statut == "erreur" and mac.appels() == []


def test_routine_sensible_confirmee_puis_executee(mac: FauxMac) -> None:
    s = Session(mac.outils())
    assert s.entendre("fin de journée").statut == "question"
    assert s.entendre("oui").texte == "✓ Routine « fin de journée » (1 étape)"
    assert mac.pont.ordres == [("app.quitter_tout", {})]


def test_routine_avec_un_echec(mac: FauxMac) -> None:
    from voix.actions import routines
    from voix.actions.base import Etat
    from voix.actions.minuteur import Minuteurs
    from voix.actions.registre import Execution, executer

    o = mac.outils()
    mac.regler(codes={"open": 1})
    x = Execution(o, Etat(), Minuteurs(o.chemins.minuteurs))
    r = _routine('{ intention = "app.ouvrir", app = "Notion" }, { intention = "son.regler", niveau = 20 }')
    rep = routines.lancer(r, o.catalogue, lambda c: executer(c, x))
    assert rep.statut == "erreur" and rep.texte.startswith("Routine « r » : 1/2 étapes faites.")
