"""Les descriptions faites sur place (sans Claude) : au bon format, et des scripts qui marchent vraiment."""

import os
import shutil
import subprocess

import pytest

from modules.corvees import ia, propositions
from modules.corvees.descriptions import alias, dossier_reel, etape, locale, script_conversion, titre

COQUILLE = shutil.which("zsh") or shutil.which("bash")


def candidat(tokens, type_="fichiers", **details):
    return {
        "id": "abc123",
        "signature": "s" * 40,
        "type": type_,
        "tokens": tokens,
        "occurrences": 12,
        "jours_distincts": 10,
        "duree_moyenne_s": 40.0,
        "regularite": 0.5,
        "lift": 50.0,
        "frequence_mois": 12.9,
        "minutes_mois": 8.6,
        "score": 50.0,
        "premiere": 1.0,
        "derniere": 2.0,
        "details": details,
    }


def lancer(script, maison, tmp_path, chemin_en_plus=None):
    fichier = tmp_path / "script.sh"
    fichier.write_text(script)
    env = {**os.environ, "HOME": str(maison)}
    if chemin_en_plus:
        env["PATH"] = f"{chemin_en_plus}:{env['PATH']}"
    return subprocess.run([COQUILLE, str(fichier)], env=env, capture_output=True, text=True, timeout=30)


CAS = [
    candidat(["fmove:Downloads→Documents/Factures [pdf, Facture_*]"]),
    candidat(["fren:Downloads [pdf, releve_*→Releve_Compte_*]", "fmove:Downloads→Documents/Releves [pdf, Releve_*]"]),
    candidat(["fren:Desktop [png, Capture d’écran * à *→screen_*]", "fmove:Desktop→Documents [png, screen_*]"]),
    candidat(["fconv:Downloads [heic→jpg, IMG_*]"]),
    candidat(["fconv:Documents [docx→pdf, Lettre_*]"]),
    candidat(["fdel:Downloads [dmg, Installeur_*]"]),
    candidat(["cmd:cd ~/Projets/x && git pull"], "shell"),
    candidat(["cmd:git add .", "cmd:git commit -m '*'", "cmd:git push"], "shell"),
    candidat(["cmd:kill *"], "shell"),
    candidat(["app:Safari", "url:mail.google.com/mail", "app:Notes"], "routine", creneau="08:30"),
    candidat(["app:Safari", "url:mail.google.com/mail"], "sequence"),
    candidat(["clip:Safari→Numbers"], "pont"),
    candidat(["fen:Word:Rapport *", "fen:Excel:Budget"], "sequence"),
]


@pytest.mark.parametrize("c", CAS, ids=lambda c: c["tokens"][0][:30])
def test_chaque_description_locale_respecte_le_schema_et_son_script_passe_le_controle(c):
    d = locale(c)
    trouvees, erreurs = ia.valider({"corvees": [d]}, {c["id"]})
    assert erreurs == [] and trouvees[c["id"]]["solution"]["type"] in ia.TYPES_SOLUTION
    assert len(d["titre_court"]) <= 60
    verification = propositions.verifier(d["solution"]["script"], d["solution"]["type"])
    assert verification["ok"], verification
    assert d["gain_minutes_mois"] <= c["minutes_mois"]


def test_les_bonnes_solutions():
    types = [locale(c)["solution"]["type"] for c in CAS]
    assert types == [
        "tache_launchd",  # rangement
        "tache_launchd",  # renommage (une partie variable) puis rangement
        "regle_dossier",  # deux parties variables : pas de script deviné
        "tache_launchd",  # conversion d'image (sips)
        "regle_dossier",  # docx → pdf : sips ne sait pas
        "regle_dossier",  # suppression : jamais de script
        "alias_zsh",
        "alias_zsh",  # une fonction, le message de commit en argument
        "autre",  # une partie variable hors guillemets
        "tache_launchd",  # à heure fixe
        "app_raccourcis",  # sans heure fixe
        "autre",
        "autre",
    ]


def test_etapes_et_titres_en_francais():
    assert etape("fmove:Downloads→Documents/Factures [pdf, Facture_*]") == (
        "déplacer les fichiers « Facture_*.pdf » de ~/Downloads vers ~/Documents/Factures"
    )
    assert etape("url:notion.so") == "aller sur notion.so"
    assert etape("fen:Word:Rapport") == "passer à la fenêtre « Rapport » de Word"
    assert etape("fdel:~ [tmp, x_*]") == "supprimer les fichiers « x_*.tmp » dans ton dossier personnel"
    assert etape("fcreate:/Volumes/Cle [pdf, Scan_*]").startswith("recevoir les fichiers « Scan_*.pdf » dans /Volumes")
    assert etape("bizarre") == "bizarre"
    long = candidat(["cmd:" + "tres_longue_commande " * 10], "shell")
    assert len(titre(long)) <= 60 and titre(long).endswith("…")
    assert (
        titre(candidat(["app:A", "app:B", "app:C", "app:D"], "routine", creneau="09:00")) == "Ouvrir A, B, C… à 09:00"
    )


def test_dossiers_reels():
    assert dossier_reel("Documents/Factures") == "\"$HOME\"/'Documents/Factures'"
    assert dossier_reel("~") == "$HOME"
    assert dossier_reel("/Volumes/Cle") == "'/Volumes/Cle'"
    assert dossier_reel("Documents/*") is None


def test_alias_et_fonctions():
    assert alias(["make"], "x") == "alias corvee_x='make'\n"
    assert alias(['echo "*"', "git commit -m '*'"], "x") == 'corvee_x() { echo "$1" && git commit -m "$2"; }\n'
    assert alias(["rm *.log"], "x") is None
    assert alias(["echo [secret]"], "x") is None
    assert alias(["echo 'l'\\''été'"], "x") is not None  # une apostrophe dans la commande


@pytest.mark.skipif(COQUILLE is None, reason="ni zsh ni bash")
def test_le_script_de_rangement_range_vraiment_sans_jamais_ecraser(tmp_path):
    maison = tmp_path / "maison"
    (maison / "Downloads").mkdir(parents=True)
    (maison / "Documents" / "Factures").mkdir(parents=True)
    for nom in ("Facture_1.pdf", "Facture_2.pdf", "Autre.pdf", "Facture_3.txt"):
        (maison / "Downloads" / nom).write_text(nom)
    (maison / "Documents" / "Factures" / "Facture_2.pdf").write_text("déjà là")
    script = locale(CAS[0])["solution"]["script"]
    sortie = lancer(script, maison, tmp_path)
    assert sortie.returncode == 0, sortie.stderr
    rangees = sorted(p.name for p in (maison / "Documents" / "Factures").iterdir())
    assert rangees == ["Facture_1.pdf", "Facture_2.pdf"]
    assert (maison / "Documents" / "Factures" / "Facture_2.pdf").read_text() == "déjà là"
    assert sorted(p.name for p in (maison / "Downloads").iterdir()) == ["Autre.pdf", "Facture_2.pdf", "Facture_3.txt"]
    assert lancer(script, maison, tmp_path).returncode == 0  # rien à faire : rien ne casse


@pytest.mark.skipif(COQUILLE is None, reason="ni zsh ni bash")
def test_le_script_de_renommage_puis_rangement(tmp_path):
    maison = tmp_path / "maison"
    (maison / "Downloads").mkdir(parents=True)
    (maison / "Downloads" / "releve_2026-09.pdf").write_text("r")
    (maison / "Downloads" / "l'été_1.pdf").write_text("apostrophe")
    script = locale(CAS[1])["solution"]["script"]
    sortie = lancer(script, maison, tmp_path)
    assert sortie.returncode == 0, sortie.stderr
    assert (maison / "Documents" / "Releves" / "Releve_Compte_2026-09.pdf").read_text() == "r"
    assert (maison / "Downloads" / "l'été_1.pdf").exists()


@pytest.mark.skipif(COQUILLE is None, reason="ni zsh ni bash")
def test_le_script_de_conversion_appelle_sips_une_fois_par_fichier(tmp_path):
    maison = tmp_path / "maison"
    (maison / "Downloads").mkdir(parents=True)
    for nom in ("IMG_1.heic", "IMG_2.heic", "IMG_2.jpg", "Photo.heic"):
        (maison / "Downloads" / nom).write_text(nom)
    faux = tmp_path / "bin"
    faux.mkdir()
    (faux / "sips").write_text('#!/bin/sh\necho "$@" >> "$HOME/appels"\nfor a; do s="$a"; done\n: > "$s"\n')
    (faux / "sips").chmod(0o755)
    script = script_conversion("fconv:Downloads [heic→jpg, IMG_*]")
    sortie = lancer(script, maison, tmp_path, faux)
    assert sortie.returncode == 0, sortie.stderr
    appels = (maison / "appels").read_text().splitlines()
    assert len(appels) == 1 and appels[0].startswith("-s format jpeg") and "IMG_1.heic" in appels[0]
    assert (maison / "Downloads" / "IMG_1.jpg").exists() and (maison / "Downloads" / "IMG_1.heic").exists()
    assert script_conversion("fconv:Documents/* [heic→jpg, IMG_*]") is None
    assert script_conversion("pas une conversion") is None


def test_ce_qui_a_ete_observe():
    from modules.corvees.descriptions import observe

    c = CAS[0]  # 12 fois, du 1 au 2 (une seconde d'écart)
    assert observe(c) == (
        "Tu déplaces les fichiers « Facture_*.pdf » de ~/Downloads vers ~/Documents/Factures : 12 fois en 1 jour."
    )
    c = dict(CAS[9], premiere=1.0, derniere=1.0 + 20 * 86400)
    assert observe(c) == (
        "Tu ouvres Safari, puis vas sur mail.google.com/mail, puis ouvres Notes vers 08:30 : 12 fois en 3 semaines."
    )
    c = candidat(
        ["app:A", "app:B", "url:x.fr", "url:y.fr", "cmd:a", "cmd:b"], "sequence", creneau="09:00", jour_semaine="lundi"
    )
    c["premiere"] = c["derniere"] = None
    assert observe(c) == (
        "Tu ouvres A et B, puis vas sur x.fr et y.fr, puis tapes « a » et « b » dans le terminal vers 09:00 "
        "le lundi : 12 fois en 10 jours."
    )


def test_le_titre_garde_toujours_l_heure():
    longs = candidat(
        ["app:Microsoft Teams", "app:Google Chrome", "url:outlook.office.com/mail"], "routine", creneau="09:12"
    )
    assert titre(longs) == "Ouvrir Microsoft Teams, Google Chrome… à 09:12"  # le 3e nom ne tient plus


def test_le_titre_d_un_rangement_garde_le_dossier_d_arrivee():
    c = candidat(["fmove:CorveesSandbox/Telechargements→CorveesSandbox/Documents/Devis [pdf, Devis_*]"])
    assert titre(c) == "Ranger les « Devis_*.pdf » dans Devis"
