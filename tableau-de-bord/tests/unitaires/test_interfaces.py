"""La barre des menus (modèle et actions) et l'instantané iPhone (seulement états, compteurs et crédits ; bloqué
au moindre motif sensible)."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import pytest

from tableau import barre_menus, caviardage, instantane_icloud
from tableau.module import EtatModule, Pastille
from tests import fabrique_web


def test_point_de_l_icone() -> None:
    def e(p: Pastille) -> EtatModule:
        return EtatModule("x", "X", "", p, "")

    assert barre_menus.point([]) == "🟢"
    assert barre_menus.point([e(Pastille.VERT), e(Pastille.GRIS)]) == "🟢"
    assert barre_menus.point([e(Pastille.VERT), e(Pastille.JAUNE)]) == "🟠"
    assert barre_menus.point([e(Pastille.JAUNE), e(Pastille.ROUGE)]) == "🔴"


def test_modele_du_menu() -> None:
    etats = fabrique_web.etats()
    etats[0].phrase = "Une phrase beaucoup trop longue pour tenir dans une ligne de menu, vraiment"
    titre, elements = barre_menus.modele(etats, None)
    assert titre == "🔴"
    assert [e.titre for e in elements] == [
        "🟢 Bouclier — Une phrase beaucoup trop longue pour tenir dans…",
        "🔴 Trieur — Trieur s'est arrêté 5 fois aujourd'hui",
        "🟡 Quotidien — « brief » : pas fait (attendu vers 7h15)",
        "⚪ Corvées — Éteint : en pause",
        "-",
        "Ouvrir le tableau de bord",
        "Mettre les alertes en sourdine 1 h",
        "Rapport de la semaine",
    ]
    assert [e.action for e in elements][:4] == [
        "module:bouclier",
        "module:trieur",
        "module:quotidien",
        "module:corvees",
    ]
    _, elements = barre_menus.modele([], fabrique_web.MAINTENANT + 3600)
    assert elements[0].titre == "Aucun module observé pour l'instant" and elements[0].action is None
    assert ("Lever la sourdine (jusqu'à 11h00)", "lever") in [(e.titre, e.action) for e in elements]


def test_actions_du_menu(site: Any) -> None:
    ouverts: list[list[str]] = []

    def ouvrir(args: list[str]) -> Any:
        from tableau import systeme

        systeme.verifier(args)  # la liste blanche les accepte
        ouverts.append(args)
        return systeme.Resultat(0, "")

    adresse = barre_menus.adresse_page(site.port, fabrique_web.JETON)
    a = barre_menus.Actions(site.source, adresse, ouvrir)
    assert a.faire("ouvrir") == "Tableau de bord ouvert."
    assert a.faire("module:trieur") == "Page de trieur ouverte."
    assert ouverts[:2] == [["open", adresse], ["open", adresse.replace("/?", "/module/trieur?")]]
    assert a.faire("sourdine").startswith("Alertes en sourdine jusqu'à")
    assert a.faire("lever") == "Sourdine levée."
    message = a.faire("rapport")
    chemin = Path(ouverts[-1][1])
    assert message.startswith("Rapport ouvert (semaine-") and chemin.exists() and "a-la-demande" in str(chemin)
    assert "Rapport de la semaine" in chemin.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="action inconnue"):
        a.faire("supprimer")


def test_instantane_seulement_etats_compteurs_credits(tmp_path: Path) -> None:
    icloud = tmp_path / "CloudDocs"
    icloud.mkdir()
    i = instantane_icloud.Instantane(icloud / "Tableau", fabrique_web.JETON)
    etats = fabrique_web.etats()
    credits = {"total_usd": 1.75, "plafonds_usd": 3.0, "projection_usd": 7.5}
    r = i.ecrire_si_utile(etats, credits, fabrique_web.MAINTENANT)
    assert r.ecrit and r.chemin == icloud / "Tableau" / "Etat.html"
    assert stat.S_IMODE(r.chemin.stat().st_mode) == 0o600
    texte = r.chemin.read_text(encoding="utf-8")
    assert caviardage.contient_sensible(texte, (fabrique_web.JETON,)) == []
    for attendu in ("2 choses à regarder", "Trieur</span> · 🔴 problème", "14 erreurs sur 24 h",
                    "2 documents en attente", "0,95 $ sur 1,00 $ ce mois-ci",
                    "Crédits Claude ce mois-ci : 1,75 $ sur 3,00 $ · projection 7,50 $"):  # fmt: skip
        assert attendu in texte, attendu
    # Ni phrase venue d'un module, ni lien, ni ressource.
    assert "arrêté 5 fois" not in texte and "brief" not in texte and "href" not in texte and "src=" not in texte
    d = instantane_icloud.donnees(etats, credits)
    assert set(d["modules"][0]) == {"nom", "emoji", "pastille", "problemes", "erreurs_24h", "file", "credits_mois",
                                    "plafond_usd"}  # fmt: skip
    # Rien de neuf : pas réécrit avant 15 min ; forcé ou après 15 min : réécrit.
    assert i.ecrire_si_utile(etats, credits, fabrique_web.MAINTENANT + 60).motif == "rien de neuf"
    assert i.ecrire_si_utile(etats, credits, fabrique_web.MAINTENANT + 60, forcer=True).ecrit
    assert i.ecrire_si_utile(etats, credits, fabrique_web.MAINTENANT + 1000).ecrit
    etats[0].pastille = Pastille.ROUGE
    assert i.ecrire_si_utile(etats, credits, fabrique_web.MAINTENANT + 1010).ecrit  # un changement : tout de suite


def test_instantane_bloque_au_moindre_motif_sensible(tmp_path: Path) -> None:
    icloud = tmp_path / "CloudDocs"
    icloud.mkdir()
    i = instantane_icloud.Instantane(icloud / "Tableau", fabrique_web.JETON)
    pieges = [
        ("alice@example.com", "e-mail"),
        ("/Users/quelquun", "chemin personnel"),
        (fabrique_web.JETON, "jeton du tableau de bord"),
        ("sk-ant-abcdefghijkl", "clé Anthropic"),
    ]
    for nom, motif in pieges:
        e = EtatModule("x", nom, "🧩", Pastille.VERT, "")
        r = i.ecrire_si_utile([e], {}, fabrique_web.MAINTENANT, forcer=True)
        assert not r.ecrit and r.motif.startswith("bloqué") and motif in r.motif, nom
    assert not (icloud / "Tableau" / "Etat.html").exists()


def test_instantane_sans_icloud_ou_en_lecture_seule(tmp_path: Path) -> None:
    sans = instantane_icloud.Instantane(tmp_path / "absent" / "Tableau")
    assert sans.ecrire_si_utile([], {}, 0.0).motif == "iCloud Drive introuvable sur ce Mac"
    icloud = tmp_path / "CloudDocs"
    icloud.mkdir()
    (icloud / "Tableau").write_text("un fichier à la place du dossier")  # l'écriture échoue, même en root
    r = instantane_icloud.Instantane(icloud / "Tableau").ecrire_si_utile([], {}, 0.0)
    assert not r.ecrit and r.motif == "écriture impossible (FileExistsError)"
    vide = instantane_icloud.page(instantane_icloud.donnees([], {}), fabrique_web.MAINTENANT)
    assert "✅ Tout va bien" in vide and "inconnu" in vide
