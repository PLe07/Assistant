"""Le catalogue : formes parlées, apps installées (lecture seule), raccourcis Apple, dossiers, alias, routines."""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

import pytest

from voix.nlu import alias, catalogue_apps
from voix.nlu.catalogue import Catalogue, Objet, dossiers, formes_parlees, objet_app, sites


def test_formes_parlees() -> None:
    assert formes_parlees("GarageBand")[:2] == ["garageband", "garage band"]
    assert "ve elle ce" in formes_parlees("VLC")
    assert "un password" in formes_parlees("1Password")
    assert "zoom" in formes_parlees("zoom.us")
    assert "sublime text" in formes_parlees("Sublime Text 4")
    assert "word" in formes_parlees("Microsoft Word") and "chrome" in formes_parlees("Google Chrome")
    assert formes_parlees("") == []


def test_objet_app_nom_francais_et_formes_connues() -> None:
    o = objet_app("com.apple.calculator", "Calculator", "/System/Applications/Calculator.app")
    assert o.nom == "Calculette" and "calculatrice" in o.formes and "calculator" in o.formes
    inconnue = objet_app("com.x.y", "Grapheur Pro 3", "/Applications/Grapheur Pro 3.app")
    assert inconnue.nom == "Grapheur Pro 3" and "grapheur pro" in inconnue.formes


def test_chercher_un_seul_candidat_par_objet_et_genres() -> None:
    c = Catalogue([
        Objet("app", "Notes", "/a/Notes.app", "n", ("notes", "note", "bloc notes")),
        Objet("app", "Notion", "/a/Notion.app", "no", ("notion",)),
        Objet("site", "YouTube", "https://y", "y", ("youtube",)),
    ])  # fmt: skip
    trouves = c.chercher("note")
    assert [x.objet.nom for x in trouves][0] == "Notes" and len({x.objet.ident for x in trouves}) == len(trouves)
    assert (
        all(x.score < 0.8 for x in c.chercher("youtube", ["app"])) and c.chercher("youtube", ["site"])[0].score == 1.0
    )
    assert c.chercher("youtube", ["app"], plancher=0.9) == []
    assert c.chercher("") == [] and c.du_genre("site")[0].nom == "YouTube"
    c.ajouter([Objet("dossier", "Bureau", "/b", "~/Desktop", ("bureau",))])
    assert c.chercher("bureau")[0].objet.genre == "dossier"


def test_dossiers_et_classes_seulement_s_il_existe(tmp_path: Path) -> None:
    sans = {o.nom for o in dossiers(tmp_path)}
    assert "Téléchargements" in sans and "Classés" not in sans
    (tmp_path / "Documents" / "Classés").mkdir(parents=True)
    avec = {o.nom: o for o in dossiers(tmp_path)}
    assert avec["Classés"].cible == str(tmp_path / "Documents" / "Classés")
    assert avec["Bureau"].cible == str(tmp_path / "Desktop") and avec["Applications"].cible == "/Applications"


def test_sites() -> None:
    s = sites()
    assert len(s) >= 50 and all(o.cible.startswith("https://") for o in s)
    youtube = next(o for o in s if o.nom == "YouTube")
    assert "youtube" in youtube.formes
    assert len({o.ident for o in s}) == len(s)


# --- apps installées, lues sans rien toucher ---------------------------------------------------------------------


def faire_app(dossier: Path, nom: str, info: dict | bytes, fr: dict | None = None, loctable: dict | None = None,
              strings_texte: str | None = None) -> Path:  # fmt: skip
    app = dossier / f"{nom}.app"
    (app / "Contents" / "Resources").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(info if isinstance(info, bytes) else plistlib.dumps(info))
    if fr is not None:
        (app / "Contents" / "Resources" / "fr.lproj").mkdir()
        (app / "Contents" / "Resources" / "fr.lproj" / "InfoPlist.strings").write_bytes(
            plistlib.dumps(fr, fmt=plistlib.FMT_BINARY)
        )
    if strings_texte is not None:
        (app / "Contents" / "Resources" / "fr.lproj").mkdir()
        (app / "Contents" / "Resources" / "fr.lproj" / "InfoPlist.strings").write_text(strings_texte, encoding="utf-16")
    if loctable is not None:
        (app / "Contents" / "Resources" / "InfoPlist.loctable").write_bytes(plistlib.dumps(loctable))
    return app


def test_apps_installees(tmp_path: Path) -> None:
    applis = tmp_path / "Applications"
    (applis / "Utilities").mkdir(parents=True)
    faire_app(applis, "Notion", {"CFBundleIdentifier": "notion.id", "CFBundleName": "Notion"})
    faire_app(
        applis, "Calculator", {"CFBundleIdentifier": "com.apple.calculator"}, fr={"CFBundleDisplayName": "Calculette"}
    )
    faire_app(
        applis / "Utilities",
        "Terminal",
        {"CFBundleIdentifier": "com.apple.Terminal"},
        loctable={"fr": {"CFBundleDisplayName": "Terminal"}, "en": {"CFBundleDisplayName": "Terminal"}},
    )
    faire_app(applis, "Ancien", {"CFBundleIdentifier": "com.x.ancien"}, strings_texte='"CFBundleName" = "Vieil Outil";')
    faire_app(applis, "Agent", {"CFBundleIdentifier": "com.x.agent", "LSUIElement": True})
    faire_app(applis, "Casse", b"pas un plist")
    faire_app(applis, "SansId", {"CFBundleName": "x"})
    faire_app(applis, "Doublon", {"CFBundleIdentifier": "notion.id"})
    ailleurs = tmp_path / "Ailleurs"
    ailleurs.mkdir()
    spot = faire_app(ailleurs, "Spot", {"CFBundleIdentifier": "com.x.spot"})
    imbriquee = faire_app(applis / "Notion.app" / "Contents", "Aide", {"CFBundleIdentifier": "com.x.aide"})
    hors = faire_app(tmp_path, "Hors", {"CFBundleIdentifier": "com.x.hors"})

    def faux(args: list[str], delai: float) -> tuple[int, str]:
        assert args[0] == "mdfind" and delai <= 30
        return 0, "\n".join(str(p) for p in (applis / "Notion.app", imbriquee, hors, spot)) + "\n"

    objets = catalogue_apps.apps_installees(tmp_path, faux, dossiers=[applis, ailleurs])
    noms = {o.ident: o.nom for o in objets}
    assert noms == {"notion.id": "Notion", "com.apple.calculator": "Calculette", "com.apple.Terminal": "Terminal",
                    "com.x.ancien": "Vieil Outil", "com.x.spot": "Spot"}  # fmt: skip
    # Sans mdfind (ou en panne), les dossiers suffisent.
    assert {o.ident for o in catalogue_apps.apps_installees(tmp_path, lambda a, d: (1, ""), dossiers=[applis])} == {
        "notion.id", "com.apple.calculator", "com.apple.Terminal", "com.x.ancien"}  # fmt: skip
    assert catalogue_apps.apps_installees(tmp_path, lambda a, d: (1, ""), dossiers=[tmp_path / "absent"]) == []
    assert catalogue_apps.racines(tmp_path)[1] == tmp_path / "Applications"


def test_noms_francais_tolerants(tmp_path: Path) -> None:
    app = faire_app(tmp_path, "X", {"CFBundleIdentifier": "x"}, loctable={"fr": "pas un dict"})
    assert catalogue_apps.nom_francais(app) is None
    (app / "Contents" / "Resources" / "InfoPlist.loctable").write_bytes(b"casse")
    assert catalogue_apps.nom_francais(app) is None
    app2 = faire_app(tmp_path, "Y", {"CFBundleIdentifier": "y"}, strings_texte="rien d'utile")
    assert catalogue_apps.nom_francais(app2) is None
    (app2 / "Contents" / "Resources" / "fr.lproj" / "InfoPlist.strings").write_bytes(plistlib.dumps(["liste"]))
    assert catalogue_apps.nom_francais(app2) is None
    assert catalogue_apps.lire_app(tmp_path / "absente.app") is None
    liste = faire_app(tmp_path, "L", b"")
    (liste / "Contents" / "Info.plist").write_bytes(plistlib.dumps(["pas", "un", "dict"]))
    assert catalogue_apps.lire_app(liste) is None


def test_raccourcis_installes_et_commande_de_lecture() -> None:
    def faux(args: list[str], delai: float) -> tuple[int, str]:
        assert args == ["shortcuts", "list"]
        return 0, "Envoyer au Mac\n\nActiver concentration\nEnvoyer au Mac\n" + "x" * 90 + "\n"

    r = catalogue_apps.raccourcis_installes(faux)
    assert [o.nom for o in r] == ["Envoyer au Mac", "Activer concentration"] and r[0].genre == "raccourci"
    assert catalogue_apps.raccourcis_installes(lambda a, d: (1, "")) == []
    # Lecture par l'exécuteur de la liste blanche : un programme hors liste n'est jamais lancé.
    assert catalogue_apps.executer(["true"], 5) == (127, "")
    assert catalogue_apps.executer(["/chemin/qui/n/existe/pas"], 5) == (127, "")
    assert catalogue_apps.executer(["sleep", "5"], 0.2) == (127, "")


# --- alias, playlists, routines ------------------------------------------------------------------------------------


def test_cibles_d_alias(tmp_path: Path) -> None:
    maison = tmp_path / "maison"
    (maison / "Documents").mkdir(parents=True)
    (maison / "Documents" / "Compta.numbers").write_text("x")
    v = alias.verifier_cible
    assert v("~/Documents/Compta.numbers", maison) == str((maison / "Documents" / "Compta.numbers").resolve())
    assert v("https://exemple.fr/x", maison) == "https://exemple.fr/x" and v("app:Notion", maison) == "app:Notion"
    for mauvaise, motif in [
        ("http://exemple.fr", "https"), ("file:///etc/hosts", "https"), ("javascript:alert(1)", "https"),
        ("/etc/hosts", "maison"), ("~/../../etc/passwd", "maison"), ("~/Documents/absent.txt", "introuvable"),
        ("https://exemple.fr/a b", "invalide"), ("app:", "invalide"), ("app:../x", "invalide"),
        ("data:text/html,x", "https"),
    ]:  # fmt: skip
        with pytest.raises(alias.CibleRefusee, match=motif):
            v(mauvaise, maison)
    os.symlink("/etc", maison / "lien")
    with pytest.raises(alias.CibleRefusee, match="maison"):
        v("~/lien/hosts", maison)  # un lien qui sort de ta maison est refusé


def test_lire_commandes(tmp_path: Path) -> None:
    texte = """
[[alias]]
nom = "la compta"
cible = "~/Documents/Compta.numbers"
formes = ["ma compta", 3, ""]
[[alias]]
nom = "dehors"
cible = "/etc/hosts"
[[alias]]
cible = "x"
[[playlist]]
nom = "Révisions"
[[playlist]]
nom = "Jazz"
lecteur = "spotify"
uri = "pas une uri"
[[playlist]]
nom = "Rock"
lecteur = "winamp"
[[playlist]]
lecteur = "musique"
[[routine]]
nom = "révision"
phrases = ["Lance ma révision"]
etapes = [{ intention = "app.ouvrir", app = "Notion" }]
[[routine]]
nom = "vide"
phrases = []
etapes = [{ intention = "x" }]
[[routine]]
nom = "sans étapes"
phrases = ["x"]
[[routine]]
nom = "étape sans intention"
phrases = ["y"]
etapes = [{ app = "Notion" }]
[[routine]]
nom = "sensible bizarre"
phrases = ["z"]
etapes = [{ intention = "app.fermer_tout" }]
sensible = "oui"
[[routine]]
phrases = ["sans nom"]
"""
    c = alias.lire(texte, tmp_path)
    assert [a.nom for a in c.alias] == ["la compta"] and c.alias[0].formes == ("la compta", "ma compta")
    assert [p.nom for p in c.playlists] == ["Révisions"] and c.playlists[0].cible == "Révisions"
    assert [r.nom for r in c.routines] == ["révision"] and c.routines[0].phrases == ("lance ma revision",)
    assert c.routine("révision") is not None and c.routine("absente") is None
    erreurs = " | ".join(c.erreurs)
    for attendu in ("« dehors » refusé", "alias n°3", "spotify:playlist", "« musique » ou « spotify »", "playlist n°4",
                    "« vide » : il faut au moins une phrase", "« sans étapes »", "« étape sans intention »",
                    "sensible = true ou false", "routine n°6"):  # fmt: skip
        assert attendu in erreurs, attendu
    assert {o.genre for o in c.objets()} == {"alias", "playlist", "routine"}
    assert alias.lire("[[[", tmp_path).erreurs[0].startswith("commandes.toml illisible")
    assert alias.lire('alias = "x"\nplaylist = 3\nroutine = {}', tmp_path).objets() == []


def test_charger_et_apprendre(tmp_path: Path) -> None:
    maison = tmp_path
    (maison / "Documents").mkdir()
    (maison / "Documents" / "Compta.numbers").write_text("x")
    f = maison / "support" / "commandes.toml"
    assert alias.charger(f, maison).objets() == []
    retenue = alias.apprendre(f, maison, '  la  "compta"  ', "~/Documents/Compta.numbers")
    assert retenue.endswith("Compta.numbers") and oct(f.stat().st_mode & 0o777) == "0o600"
    c = alias.charger(f, maison)
    assert c.alias[0].nom == 'la "compta"' and c.erreurs == []
    with pytest.raises(alias.CibleRefusee, match="existe déjà"):
        alias.apprendre(f, maison, 'la "compta"', "~/Documents/Compta.numbers")
    with pytest.raises(alias.CibleRefusee, match="vide"):
        alias.apprendre(f, maison, "   ", "~/Documents/Compta.numbers")
    with pytest.raises(alias.CibleRefusee, match="maison"):
        alias.apprendre(f, maison, "hosts", "/etc/hosts")
    avant = f.read_text()
    alias.apprendre(f, maison, "le site", "https://exemple.fr")
    assert f.read_text().startswith(avant), "le reste du fichier n'est pas touché"
    f.write_bytes(b"\xff\xfe\x00")
    assert "illisible" in alias.charger(f, maison).erreurs[0]
