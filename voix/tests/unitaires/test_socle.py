"""Le socle : raccourci global (sans voler ceux du système), réglages, choix automatiques."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from voix import cli, config
from voix.raccourcis_systeme import (
    CANDIDATS,
    Combinaison,
    CombinaisonInvalide,
    choisir,
    conflit,
    lire_export,
    pris,
)

CTRL, OPTION, CMD, SHIFT = 1 << 18, 1 << 19, 1 << 20, 1 << 17


def export(entrees: dict[int, tuple[bool, int, int]], binaire: bool = False) -> bytes:
    """Un export de com.apple.symbolichotkeys : {id: (actif, touche, masque)}."""
    racine = {
        "AppleSymbolicHotKeys": {
            str(i): {"enabled": actif, "value": {"parameters": [32, touche, masque], "type": "standard"}}
            for i, (actif, touche, masque) in entrees.items()
        }
    }
    return plistlib.dumps(racine, fmt=plistlib.FMT_BINARY if binaire else plistlib.FMT_XML)


# --- combinaisons ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texte", "attendu", "symboles", "carbon"),
    [
        ("ctrl+option+espace", "ctrl+option+espace", "⌃⌥Espace", 4096 + 2048),
        ("⌃⌥Espace", "ctrl+option+espace", "⌃⌥Espace", 4096 + 2048),
        ("Control-Alt-Space", "ctrl+option+espace", "⌃⌥Espace", 4096 + 2048),
        ("cmd+ctrl+option+espace", "ctrl+option+cmd+espace", "⌃⌥⌘Espace", 4096 + 2048 + 256),
        ("maj+ctrl+v", "ctrl+shift+v", "⌃⇧V", 4096 + 512),
        ("⌥⌘F5", "option+cmd+f5", "⌥⌘F5", 2048 + 256),
    ],
)
def test_lire_une_combinaison(texte: str, attendu: str, symboles: str, carbon: int) -> None:
    c = Combinaison.lire(texte)
    assert c.texte() == attendu and c.symboles() == symboles and c.masque_carbon() == carbon
    assert Combinaison.lire(c.texte()) == c


@pytest.mark.parametrize(
    ("texte", "motif"),
    [
        ("", "vide"),
        ("ctrl+option+a", "touche inconnue"),  # A n'est pas au même endroit en AZERTY : refusée
        ("ctrl+hyper+espace", "modificateur inconnu"),
        ("shift+v", "au moins"),
        ("espace", "au moins"),
    ],
)
def test_combinaisons_refusees(texte: str, motif: str) -> None:
    with pytest.raises(CombinaisonInvalide, match=motif):
        Combinaison.lire(texte)


def test_les_candidats_sont_tous_valides_et_distincts() -> None:
    combis = [Combinaison.lire(c) for c in CANDIDATS]
    assert len(set(combis)) == len(CANDIDATS) and combis[0].symboles() == "⌃⌥Espace"


# --- export des raccourcis du système -----------------------------------------------------------------------------


def test_export_vide_les_valeurs_d_usine_comptent_comme_prises() -> None:
    systeme = lire_export(export({}))
    occupes = pris(systeme)
    assert Combinaison.lire("ctrl+option+espace") in occupes  # source de saisie suivante, active d'usine
    assert Combinaison.lire("cmd+espace") in occupes  # Spotlight
    combi, ecartes = choisir(systeme)
    assert combi.symboles() == "⌃⌥⌘Espace"
    assert ecartes == ["⌃⌥Espace est pris par macOS (sélectionner la source de saisie suivante)"]


def test_export_ou_la_source_suivante_est_desactivee() -> None:
    systeme = lire_export(export({61: (False, 49, CTRL | OPTION)}))
    combi, ecartes = choisir(systeme)
    assert combi.symboles() == "⌃⌥Espace" and ecartes == []
    assert conflit(combi, systeme) is None


def test_export_binaire_et_raccourci_deplace_par_toi() -> None:
    # Tu as mis Spotlight sur ⌃⌥⌘Espace et désactivé la source suivante : le candidat 3 est choisi.
    donnees = export({61: (False, 49, CTRL | OPTION), 64: (True, 49, CTRL | OPTION | CMD)}, binaire=True)
    systeme = lire_export(donnees)
    assert conflit(Combinaison.lire("ctrl+option+cmd+espace"), systeme) == "Spotlight"
    combi, _ = choisir(systeme, ["ctrl+option+cmd+espace", "ctrl+shift+espace"])
    assert combi.symboles() == "⌃⇧Espace"


def test_bit_fn_ignore_et_entrees_etranges_tolerees() -> None:
    racine = {
        "AppleSymbolicHotKeys": {
            "36": {"enabled": True, "value": {"parameters": [65535, 103, (1 << 23)], "type": "standard"}},
            "pas-un-nombre": {"enabled": True},
            "70": "pas un dictionnaire",
            "71": {"enabled": True, "value": {"parameters": ["x"]}},
            "61": {"enabled": True},  # sans valeur : celle d'usine
        }
    }
    systeme = lire_export(plistlib.dumps(racine))
    f11 = Combinaison(103, frozenset())
    assert any(r.combinaison == f11 and r.ident == 36 for r in systeme)
    assert Combinaison.lire("ctrl+option+espace") in pris(systeme)


def test_export_illisible() -> None:
    with pytest.raises(ValueError, match="illisible"):
        lire_export(b"ceci n'est pas un plist")
    with pytest.raises(ValueError, match="illisible"):
        lire_export(plistlib.dumps(["liste"]))
    assert len(lire_export(plistlib.dumps({"AppleSymbolicHotKeys": "x"}))) == 4  # usine seulement


def test_aucun_candidat_libre() -> None:
    tout_pris = {
        100 + i: (True, Combinaison.lire(c).touche, sum({"ctrl": CTRL, "option": OPTION, "cmd": CMD, "shift": SHIFT}[m]
                                                         for m in Combinaison.lire(c).modificateurs))
        for i, c in enumerate(CANDIDATS)
    }  # fmt: skip
    with pytest.raises(CombinaisonInvalide, match="aucun"):
        choisir(lire_export(export(tout_pris)))


# --- réglages ------------------------------------------------------------------------------------------------------


def test_reglages_par_defaut_et_choix_automatiques(tmp_path: Path) -> None:
    c = config.Chemins(tmp_path)
    r = config.charger(c)
    assert r.erreurs == [] and r.raccourci() == "ctrl+option+espace" and r.moteur() == "whisper"
    assert r.whisper() == ("small", "mlx")
    config.ecrire_choix(c, raccourci="ctrl+option+cmd+espace", moteur="apple")
    config.ecrire_choix(c, whisper_modele="base")
    r = config.charger(c)
    assert r.raccourci() == "ctrl+option+cmd+espace" and r.moteur() == "apple" and r.whisper() == ("base", "mlx")
    assert oct(c.choix.stat().st_mode & 0o777) == "0o600" and oct(c.support.stat().st_mode & 0o777) == "0o700"
    # Ce que tu écris toi-même passe devant les choix automatiques.
    c.reglages.write_text('[raccourci]\ncombinaison = "ctrl+option+v"\n[moteur]\nchoix = "whisper"\n'
                          'whisper_backend = "onnx"\n', encoding="utf-8")  # fmt: skip
    r = config.charger(c)
    assert r.raccourci() == "ctrl+option+v" and r.moteur() == "whisper" and r.whisper() == ("base", "onnx")


def test_reglages_tolerants(tmp_path: Path) -> None:
    c = config.Chemins(tmp_path)
    c.preparer()
    c.reglages.write_text(
        '[inconnue]\nx = 1\n[ecoute]\nsilence_fin_ms = 50\nduree_max_s = "huit"\ninventee = 3\n'
        '[eveil]\nactif = 1\nseuil = 0.7\n[moteur]\nchoix = "siri"\n[retour]\nvoix = 3\n[journal]\nactif = false\n'
        "[ia]\nplafond_usd_mois = 5\nactif = true\nmodele = 'x'\nretour = 2\n[confirmation]\ndelai_s = true\n"
        "racine = 1\n",
        encoding="utf-8",
    )
    r = config.charger(c)
    texte = " | ".join(r.erreurs)
    for attendu in ("[inconnue]", "silence_fin_ms = 50", "duree_max_s doit être un nombre", "ecoute.inventee",
                    "eveil.actif doit valoir", "moteur.choix = 'siri'", "retour.voix doit être un texte",
                    "plafond_usd_mois = 5", "ia.retour", "confirmation.delai_s doit être un nombre",
                    "confirmation.racine"):  # fmt: skip
        assert attendu in texte, attendu
    assert r["eveil"]["seuil"] == 0.7 and r["journal"]["actif"] is False and r["ia"]["plafond_usd_mois"] == 0.5
    assert r["ecoute"]["silence_fin_ms"] == 500  # valeur hors bornes refusée : défaut gardé
    c.reglages.write_text("[[[", encoding="utf-8")
    c.choix.write_text("{pas du json", encoding="utf-8")
    r = config.charger(c)
    assert any("illisible" in e for e in r.erreurs) and len(r.erreurs) == 2 and r.raccourci() == "ctrl+option+espace"
    assert config.ecrire_choix(c, moteur="apple") == {"moteur": "apple"}  # un choix.json cassé est remplacé
    c.choix.write_text("[1, 2]", encoding="utf-8")
    assert config.charger(c).choix == {} and config.ecrire_choix(c, moteur="apple") == {"moteur": "apple"}


def test_labels_et_chemins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.getpass, "getuser", lambda: "jean.dupont")
    c = config.Chemins(tmp_path)
    r = config.charger(c)
    assert r.label_moteur() == "com.jeandupont.voix" and r.label_app() == "com.jeandupont.voix.app"
    c.preparer()
    c.reglages.write_text('[installation]\nprefixe_label = "../x y"\n', encoding="utf-8")
    assert config.charger(c).prefixe() == "xy"
    c.reglages.write_text('[installation]\nprefixe_label = "///"\n', encoding="utf-8")
    assert config.charger(c).prefixe() == "utilisateur"
    assert c.socket.name == "voix.sock" and c.socket.parent == c.support and c.app.name == "Commandes Vocales.app"
    assert len(str(config.Chemins(Path("/Users/un-prenom-assez-long")).socket).encode()) < 104  # limite AF_UNIX macOS
    for nom in ("logs", "etat", "minuteurs", "verrou", "aide_memoire", "launch_agents", "bin", "commandes",
                "journal"):  # fmt: skip
        assert isinstance(getattr(c, nom), Path)
    monkeypatch.setenv("VOIX_MAISON", str(tmp_path / "ailleurs"))
    assert config.chemins_par_defaut().maison == tmp_path / "ailleurs"


def test_le_modele_de_reglages_est_valide_et_ne_change_rien(tmp_path: Path) -> None:
    c = config.Chemins(tmp_path)
    c.preparer()
    c.reglages.write_text(config.MODELE_REGLAGES, encoding="utf-8")
    r = config.charger(c)
    assert r.erreurs == [] and r.valeurs == config.DEFAUTS


# --- la commande ---------------------------------------------------------------------------------------------------


def test_cli_version_et_aide(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["version"]) == 0 and "Voix 1.0.0" in capsys.readouterr().out
    assert cli.main([]) == 0 and "raccourci" in capsys.readouterr().out


def test_cli_raccourci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("VOIX_MAISON", str(tmp_path))
    libre = tmp_path / "libre.plist"
    libre.write_bytes(export({61: (False, 49, CTRL | OPTION)}))
    assert cli.main(["raccourci", "--export", str(libre)]) == 0
    assert "✅ Raccourci de Voix : ⌃⌥Espace" in capsys.readouterr().out
    usine = tmp_path / "usine.plist"
    usine.write_bytes(export({}))
    assert cli.main(["raccourci", "--export", str(usine)]) == 1
    sortie = capsys.readouterr().out
    assert "⌃⌥Espace est pris par macOS" in sortie and "Premier raccourci libre : ⌃⌥⌘Espace" in sortie
    casse = tmp_path / "casse.plist"
    casse.write_bytes(b"x")
    assert cli.main(["raccourci", "--export", str(casse)]) == 1 and "illisible" in capsys.readouterr().out
    c = config.Chemins(tmp_path)
    c.preparer()
    c.reglages.write_text('[raccourci]\ncombinaison = "ctrl+q"\n', encoding="utf-8")
    assert cli.main(["raccourci", "--export", str(libre)]) == 1 and "refusé" in capsys.readouterr().out


def test_cli_raccourci_sans_mac(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("VOIX_MAISON", str(tmp_path))

    def absent(*_a: object, **_k: object) -> object:
        raise FileNotFoundError("defaults")

    monkeypatch.setattr(cli.subprocess, "run", absent)
    assert cli.main(["raccourci"]) == 0 and "indisponible" in capsys.readouterr().out

    class Proc:
        returncode = 0
        stdout = export({61: (False, 49, CTRL | OPTION)})

    monkeypatch.setattr(cli.subprocess, "run", lambda *_a, **_k: Proc())
    assert cli.main(["raccourci"]) == 0 and "⌃⌥Espace" in capsys.readouterr().out
